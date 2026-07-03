import frappe
from frappe import _
import json
from ai_apps.api.proctor_api.utils.auth import validate_token
from ai_apps.api.proctor_api.utils.logger import get_logger
_logger = get_logger(__name__)

# -------------------------------------------------
# Proctor Event CRUD API
# -------------------------------------------------

@frappe.whitelist()
def create_event(**kwargs):
    """Create a new Proctor Event document."""
    try:
        payload = frappe._dict(kwargs)
        payload.pop("cmd", None)
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Invalid JSON for create_event")
        raise frappe.exceptions.ValidationError(_("Invalid JSON payload"))

    event_type = payload.get("event_type") or payload.get("title")
    occurred_at_raw = payload.get("occurred_at") or payload.get("event_date") or payload.get("timestamp")
    session = payload.get("session")

    if not event_type:
        raise frappe.exceptions.ValidationError(_("Event type/title is required"))
    if not session:
        raise frappe.exceptions.ValidationError(_("Session is required"))

    from frappe.utils import get_datetime, get_datetime_str, now_datetime
    if occurred_at_raw:
        try:
            occurred_at = get_datetime_str(get_datetime(occurred_at_raw))
        except Exception:
            occurred_at = get_datetime_str(now_datetime())
    else:
        occurred_at = get_datetime_str(now_datetime())

    # Build metadata dictionary
    metadata_dict = {}
    if isinstance(payload.get("metadata"), dict):
        metadata_dict.update(payload["metadata"])
    elif isinstance(payload.get("metadata"), str):
        try:
            metadata_dict.update(frappe.parse_json(payload["metadata"]))
        except Exception:
            metadata_dict["raw_metadata"] = payload["metadata"]
    if "description" in payload:
        metadata_dict["description"] = payload["description"]
    if "evidence" in payload:
        metadata_dict["evidence_length"] = len(payload["evidence"]) if payload["evidence"] else 0

    # PRE-UPLOAD EVIDENCE BEFORE LOCKING PARENT
    evidence_data = payload.get("evidence") or metadata_dict.get("evidence")
    if evidence_data and not str(evidence_data).startswith("http"):
        try:
            from ai_apps.api.proctor_api.evidence import store_evidence
            res = store_evidence(
                session=session,
                violation_type=event_type,
                evidence=evidence_data
            )
            if res and res.get("url"):
                metadata_dict["evidence"] = res["url"]
                metadata_dict["evidence_sharepoint_path"] = res.get("filename")
                payload["evidence"] = None  # Remove massive base64 to keep DB light
        except Exception as e:
            frappe.log_error(title="Failed to pre-upload evidence in create_event", message=str(e))

    import time
    lock_name = f"proctor_event_{session}"[:64]
    for attempt in range(8):
        try:
            frappe.db.sql("SELECT GET_LOCK(%s, 10)", lock_name)
            try:
                # Always reload fresh from DB inside the lock — this is the key fix.
                # A stale in-memory doc causes TimestampMismatchError when another
                # request saved it between our load and our save.
                parent_name = frappe.db.get_value(
                    "Proctor Event", {"session": session}, "name", cache=False
                )
                if parent_name:
                    doc = frappe.get_doc("Proctor Event", parent_name)  # fresh load
                else:
                    try:
                        doc = frappe.new_doc("Proctor Event")
                        doc.session = session
                        doc.insert(ignore_permissions=True, ignore_links=True)
                    except (frappe.DuplicateEntryError, frappe.exceptions.UniqueValidationError):
                        # The row was inserted by another transaction. Rollback to get a fresh read view.
                        frappe.db.rollback()
                        parent_name = frappe.db.get_value(
                            "Proctor Event", {"session": session}, "name", cache=False
                        )
                        if not parent_name:
                            # If still not found, sleep and let the outer retry loop handle it
                            raise frappe.exceptions.TimestampMismatchError("Retry")
                        doc = frappe.get_doc("Proctor Event", parent_name)  # fresh load

                child_data = {
                    "session": session,
                    "event_type": event_type,
                    "occurred_at": occurred_at,
                }
                for key in ["severity", "penalty_points", "duration_ms", "confidence_score", "trust_score_delta", "source", "detector"]:
                    if key in payload:
                        child_data[key] = payload[key]
                if metadata_dict:
                    child_data["metadata"] = frappe.as_json(metadata_dict)

                doc.append("proctor_session_event", child_data)
                doc.save(ignore_permissions=True)
                return {"success": True, "name": doc.name}
            finally:
                frappe.db.sql("SELECT RELEASE_LOCK(%s)", lock_name)

        except frappe.exceptions.TimestampMismatchError:
            frappe.db.rollback()
            time.sleep(0.05 * (attempt + 1))
        except Exception as exc:
            if "Deadlock" in str(exc) or "Lock wait timeout" in str(exc):
                frappe.db.rollback()
                time.sleep(0.05 * (attempt + 1))
                continue
            frappe.log_error(message=str(exc), title="Failed to create Proctor Event")
            raise frappe.exceptions.ValidationError(_("Unable to create Proctor Event"))

    raise frappe.exceptions.ValidationError(_("Unable to create Proctor Event due to concurrent modification limits"))

@frappe.whitelist()
def create_start_event(**kwargs):
    """Create a SESSION_START proctor event linked to a session."""
    try:
        payload = frappe._dict(kwargs)
        payload.pop("cmd", None)
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Invalid JSON for create_start_event")
        raise frappe.exceptions.ValidationError(_("Invalid JSON payload"))

    session_id = payload.get("session_id")
    if not session_id:
        raise frappe.exceptions.ValidationError(_("session_id is required"))

    # Verify session exists
    if not frappe.db.exists("Proctor Session", session_id):
        raise frappe.exceptions.ValidationError(_("Proctor Session not found"))

    import time
    for attempt in range(5):
        try:
            doc = None
            # Direct parent lookup by session (cache=False)
            parent_name = frappe.db.get_value("Proctor Event", {"session": session_id}, "name", cache=False)
            _logger.info(f"create_start_event attempt={attempt} session_id={session_id} parent_name={parent_name}")
            if parent_name:
                doc = frappe.get_doc("Proctor Event", parent_name)
            else:
                # No parent exists – create a new Proctor Event and insert it immediately
                try:
                    doc = frappe.new_doc("Proctor Event")
                    doc.session = session_id
                    doc.insert(ignore_permissions=True)
                    _logger.info(f"New parent created: {doc.name}, child count before append: {len(doc.proctor_session_event)}")
                except (frappe.DuplicateEntryError, frappe.exceptions.UniqueValidationError):
                    # Another concurrent request already created the parent — just fetch it
                    parent_name = frappe.db.get_value("Proctor Event", {"session": session_id}, "name", cache=False)
                    doc = frappe.get_doc("Proctor Event", parent_name)

            # Prepare child row data for SESSION_START
            child_data = {
                "session": session_id,
                "event_type": "SESSION_START",
                "severity": "LOW",
                "penalty_points": 0,
                "occurred_at": frappe.utils.now_datetime(),
                "source": "ML",
                "detector": "start_session",
            }
            extra_meta = payload.get("extra_meta") or {}
            meta = {
                "source": "ML",
                "detector": "start_session",
                "message": "Session started via ML server",
                "extra": extra_meta,
            }
            child_data["metadata"] = frappe.as_json(meta)

            child_row = doc.append("proctor_session_event", child_data)

            doc.save(ignore_permissions=True)

            # Diagnostic: verify child was actually persisted
            count = frappe.db.sql(
                "SELECT COUNT(*) FROM `tabProctor Session Event` WHERE parent = %s",
                doc.name
            )[0][0]
            _logger.info(f"Child rows in DB after save for {doc.name}: {count}")

            return {"success": True, "event_id": doc.name}
        except frappe.exceptions.TimestampMismatchError:
            time.sleep(0.05 * (attempt + 1))
        except Exception as exc:
            if "Deadlock" in str(exc) or "Lock wait timeout" in str(exc):
                time.sleep(0.05 * (attempt + 1))
                continue
            frappe.log_error(message=str(exc), title="Failed to create SESSION_START event")
            raise frappe.exceptions.ValidationError(_("Unable to create start event"))

    raise frappe.exceptions.ValidationError(_("Unable to create start event due to concurrent modification limits"))

@frappe.whitelist()
def create_full_session_event(**kwargs):
    """Create both SESSION_START and SESSION_END events for a session in one call."""
    try:
        payload = frappe._dict(kwargs)
        payload.pop("cmd", None)
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Invalid JSON for create_full_session_event")
        raise frappe.exceptions.ValidationError(_("Invalid JSON payload"))

    session_id = payload.get("session_id")
    if not session_id:
        raise frappe.exceptions.ValidationError(_("session_id is required"))

    if not frappe.db.exists("Proctor Session", session_id):
        raise frappe.exceptions.ValidationError(_("Proctor Session not found"))

    start_payload = payload.get("start_payload") or {}
    end_payload = payload.get("end_payload") or {}

    if isinstance(start_payload, str):
        try:
            start_payload = frappe.parse_json(start_payload)
        except Exception:
            start_payload = {}
    if isinstance(end_payload, str):
        try:
            end_payload = frappe.parse_json(end_payload)
        except Exception:
            end_payload = {}

    if start_payload and isinstance(start_payload.get("metadata"), str):
        try:
            start_payload["metadata"] = frappe.parse_json(start_payload["metadata"])
        except Exception:
            pass
    if end_payload and isinstance(end_payload.get("metadata"), str):
        try:
            end_payload["metadata"] = frappe.parse_json(end_payload["metadata"])
        except Exception:
            pass

    events_list = []
    if isinstance(end_payload.get("metadata"), dict):
        events_list = end_payload["metadata"].get("events", []) or []
        
    # PRE-UPLOAD EVIDENCE BEFORE LOCKING PARENT
    for ev in events_list:
        ev_meta = ev.get("metadata") or {}
        evidence_data = ev.get("evidence") or ev_meta.get("evidence")
        if evidence_data and not str(evidence_data).startswith("http"):
            try:
                from ai_apps.api.proctor_api.evidence import store_evidence
                ev_type = ev.get("violationType") or ev.get("type") or "VIOLATION"
                res = store_evidence(session=session_id, violation_type=ev_type, evidence=evidence_data)
                if res and res.get("url"):
                    ev["evidence"] = res["url"]
                    ev_meta["evidence"] = res["url"]
                    ev_meta["evidence_sharepoint_path"] = res.get("filename")
            except Exception as e:
                frappe.log_error("Evidence pre-upload failed in full session", str(e))

    import time
    for attempt in range(5):
        try:
            doc = None
            parent_name = frappe.db.get_value("Proctor Event", {"session": session_id}, "name", cache=False)
            if parent_name:
                doc = frappe.get_doc("Proctor Event", parent_name)
            else:
                try:
                    doc = frappe.new_doc("Proctor Event")
                    doc.session = session_id
                    doc.insert(ignore_permissions=True)
                except (frappe.DuplicateEntryError, frappe.exceptions.UniqueValidationError):
                    parent_name = frappe.db.get_value("Proctor Event", {"session": session_id}, "name", cache=False)
                    doc = frappe.get_doc("Proctor Event", parent_name)

            def build_child(event_type, extra):
                child = {"session": session_id, "event_type": event_type}
                for key in ["severity", "penalty_points", "duration_ms", "confidence_score", "trust_score_delta", "source", "detector", "metadata"]:
                    if key in extra:
                        child[key] = extra[key]

                from frappe.utils import get_datetime, get_datetime_str, now_datetime
                occurred_at_raw = extra.get("occurred_at") or extra.get("timestamp") or extra.get("event_date") or extra.get("occurredAt")
                if occurred_at_raw:
                    try:
                        child["occurred_at"] = get_datetime_str(get_datetime(occurred_at_raw))
                    except Exception:
                        child["occurred_at"] = get_datetime_str(now_datetime())
                else:
                    child["occurred_at"] = get_datetime_str(now_datetime())

                if isinstance(child.get("metadata"), dict):
                    child["metadata"] = frappe.as_json(child["metadata"])
                return child

            if start_payload:
                start_child = build_child(start_payload.get("event_type", "SESSION_START"), start_payload)
                doc.append("proctor_session_event", start_child)

            if end_payload:
                if isinstance(end_payload.get("metadata"), dict) and "events" in end_payload["metadata"]:
                    del end_payload["metadata"]["events"]
                end_child = build_child(end_payload.get("event_type", "SESSION_END"), end_payload)
                doc.append("proctor_session_event", end_child)
                
                for ev in events_list:
                    ev_type = ev.get("violationType") or ev.get("type") or "VIOLATION"
                    ev_meta = {
                        "message": ev.get("message"),
                        "evidence": ev.get("evidence")
                    }
                    child = build_child(ev_type, {
                        "metadata": ev_meta,
                        "occurred_at": ev.get("timestamp") or ev.get("occurredAt")
                    })
                    doc.append("proctor_session_event", child)

            doc.save(ignore_permissions=True)

            try:
                from ai_apps.api.proctor_api.proctor_session import sync_session_metrics
                sync_session_metrics(session_id)
            except Exception as e:
                frappe.log_error(title="Failed to sync metrics in create_full_session_event", message=str(e))

            return {"success": True, "event_id": doc.name}
        except frappe.exceptions.TimestampMismatchError:
            time.sleep(0.05 * (attempt + 1))
        except Exception as exc:
            if "Deadlock" in str(exc) or "Lock wait timeout" in str(exc):
                time.sleep(0.05 * (attempt + 1))
                continue
            frappe.log_error(message=str(exc), title="Failed to create full session event")
            raise frappe.exceptions.ValidationError(_("Unable to create full session event"))
    raise frappe.exceptions.ValidationError(_("Unable to create full session event due to concurrent modification limits"))


@frappe.whitelist()
def get_event(event_name: str):
    """Retrieve a single Proctor Event by name.

    Args:
        event_name (str): Name (ID) of the Proctor Event document.
    Returns:
        dict: Document fields.
    """
    if not event_name:
        raise frappe.exceptions.ValidationError(_("Event name is required"))
    try:
        doc = frappe.get_doc("Proctor Event", event_name)
        return doc.as_dict()
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Failed to get Proctor Event")
        raise frappe.exceptions.ValidationError(_("Event not found or access denied"))

@frappe.whitelist()
def update_event(event_name: str, data: str):
    """Update an existing Proctor Event.

    Args:
        event_name (str): Name of the document to update.
        data (str): JSON string with fields to modify.
    Returns:
        dict: Success flag.
    """
    if not event_name:
        raise frappe.exceptions.ValidationError(_("Event name is required"))
    try:
        payload = frappe.parse_json(data)
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Invalid JSON for update_event")
        raise frappe.exceptions.ValidationError(_("Invalid JSON payload"))

    try:
        doc = frappe.get_doc("Proctor Event", event_name)
        for key, value in payload.items():
            if hasattr(doc, key):
                setattr(doc, key, value)
        doc.save(ignore_permissions=False)
        return {"success": True}
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Failed to update Proctor Event")
        raise frappe.exceptions.ValidationError(_("Unable to update Proctor Event"))


@frappe.whitelist()
def delete_event(event_name: str):
    """Delete a Proctor Event document.

    Args:
        event_name (str): Name of the document to delete.
    Returns:
        dict: Success flag.
    """
    if not event_name:
        raise frappe.exceptions.ValidationError(_("Event name is required"))
    try:
        doc = frappe.get_doc("Proctor Event", event_name)
        doc.delete()
        return {"success": True}
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Failed to delete Proctor Event")
        raise frappe.exceptions.ValidationError(_("Unable to delete Proctor Event"))

@frappe.whitelist()
def list_events(filters: str = "{}", page: int = 1, limit: int = 20):
    """List Proctor Event documents with optional filters and pagination.

    Args:
        filters (str): JSON string of filter dict (e.g., {"status": "Open"}).
        page (int): 1‑based page number.
        limit (int): Number of records per page.
    Returns:
        dict: Paginated list of events and metadata.
    """
    try:
        filter_dict = frappe.parse_json(filters) if isinstance(filters, str) else filters
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Invalid JSON for list_events filters")
        raise frappe.exceptions.ValidationError(_("Invalid filters JSON"))

    page = int(page) if page else 1
    limit = int(limit) if limit else 20
    offset = (page - 1) * limit

    try:
        total = frappe.db.count("Proctor Event", filter_dict)
        records = frappe.get_all(
            "Proctor Event",
            fields="*",
            filters=filter_dict,
            limit_page_length=limit,
            limit_start=offset,
            order_by="creation desc",
        )
        return {
            "success": True,
            "events": records,
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit if total else 0,
        }
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Failed to list Proctor Events")
        raise frappe.exceptions.ValidationError(_("Unable to list events"))
