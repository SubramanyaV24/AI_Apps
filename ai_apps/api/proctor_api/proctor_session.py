import frappe
from frappe import _

# Import RuleEngine for trust score
from ai_apps.api.proctor_api.rule_engine import RuleEngine

# -------------------------------------------------
# Proctor Session CRUD API
# -------------------------------------------------

# stray @frappe.whitelist() removed – kept for clarity

@frappe.whitelist(allow_guest=True)
def get_session(session_name: str):
    """Retrieve a Proctor Session document by name.

    Args:
        session_name (str): Name (ID) of the Proctor Session.
    Returns:
        dict: Document fields as a dictionary.
    """
    if not session_name:
        raise frappe.exceptions.ValidationError(_("Session name is required"))
    try:
        doc = frappe.get_doc("Proctor Session", session_name)
        return doc.as_dict()
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Failed to get Proctor Session")
        raise frappe.exceptions.ValidationError(_("Session not found or access denied"))

@frappe.whitelist(allow_guest=True)
def start_session(**kwargs):
    """Create a new Proctor Session."""
    try:
        payload = frappe._dict(kwargs)
        payload.pop("cmd", None)
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Invalid JSON for start_session")
        raise frappe.exceptions.ValidationError(_("Invalid JSON payload"))

    required = ["entity_id", "entity_type", "user_id"]
    missing = [f for f in required if f not in payload]
    if missing:
        raise frappe.exceptions.ValidationError(_(f"Missing required fields: {', '.join(missing)}"))

    # Optional custom session identifier (e.g., UUID from ML backend)
    custom_name = payload.get("session_id") or payload.get("name")

    # Check if a session already exists for the same entity and user
    existing_sessions = frappe.get_all(
        "Proctor Session",
        filters=[
            ["entity_id", "=", payload.get("entity_id")],
            ["entity_type", "=", payload.get("entity_type")],
            ["user_id", "=", payload.get("user_id")],
            ["status", "in", ["STARTED", "IN_PROGRESS"]],
        ],
        limit=1,
        fields=["name"],
    )
    if existing_sessions:
        # Reuse the first matching session
        return {"success": True, "session_id": existing_sessions[0]["name"]}

    # No existing session, create a new one
    try:
        doc = frappe.new_doc("Proctor Session")
        # Set default values
        doc.status = "STARTED"
        doc.trust_score = 100.0
        from frappe.utils import now_datetime
        doc.started_at = now_datetime()
        
        # Populate candidate metadata
        for fieldname in ["entity_id", "entity_type", "user_id", "user_name", "user_email"]:
            if payload.get(fieldname):
                doc.set(fieldname, payload.get(fieldname))
                
        doc.insert(ignore_permissions=True)
        return {"success": True, "session_id": doc.name}
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Failed to start Proctor Session")
        raise frappe.exceptions.ValidationError(_("Unable to create Proctor Session"))

@frappe.whitelist(allow_guest=True)
def update_session(session_name: str, **kwargs):
    """Update an existing Proctor Session."""
    if not session_name:
        raise frappe.exceptions.ValidationError(_("Session name is required"))
    try:
        payload = frappe._dict(kwargs)
        payload.pop("cmd", None)
        payload.pop("session_name", None)
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Invalid JSON for update_session")
        raise frappe.exceptions.ValidationError(_("Invalid JSON payload"))

    try:
        doc = frappe.get_doc("Proctor Session", session_name)
        for key, value in payload.items():
            if hasattr(doc, key) and key not in ("owner", "creation", "modified", "modified_by", "docstatus", "idx", "name"):
                setattr(doc, key, value)
                
        # Automatically set ended_at when status is updated to ENDED
        if payload.get("status") == "ENDED" and not doc.ended_at:
            from frappe.utils import now_datetime
            doc.ended_at = now_datetime()
            
        doc.save(ignore_permissions=True)

        # Sync metrics when session is updated
        sync_session_metrics(session_name)

        return {"success": True}
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Failed to update Proctor Session")
        raise frappe.exceptions.ValidationError(_("Unable to update Proctor Session"))


def sync_session_metrics(session_id: str):
    """Calculate and update analytical metrics on the Proctor Session document."""
    if not session_id or not frappe.db.exists("Proctor Session", session_id):
        return

    # 1. Get statistics from child events in Proctor Event
    parent_name = frappe.db.get_value("Proctor Event", {"session": session_id}, "name")
    total_events = 0
    critical_events = 0
    total_penalty_points = 0
    review_required = 0

    if parent_name:
        events_data = frappe.get_all(
            "Proctor Session Event",
            filters={"parent": parent_name},
            fields=["severity", "penalty_points", "event_type"]
        )
        # Count actual violations (exclude start and end markers)
        violations = [e for e in events_data if e.get("event_type") not in ("SESSION_START", "SESSION_END")]
        total_events = len(violations)
        total_penalty_points = sum(e.get("penalty_points") or 0 for e in violations)
        critical_events = sum(1 for e in violations if e.get("severity") == "HIGH")

    # 2. Determine trust score, risk band, and escalation state
    engine = RuleEngine()
    engine_score = engine.get_current_score(session_id)
    risk_level = engine.get_risk_band(engine_score)
    escalation_state = engine.get_escalation_state(session_id)
    
    # Review required if score is below 70, or there are any HIGH/CRITICAL violations
    if engine_score < 70 or critical_events > 0:
        review_required = 1

    # 3. Update Proctor Session fields
    update_dict = {
        "trust_score": engine_score,
        "risk_level": risk_level,
        "total_events": total_events,
        "critical_events": critical_events,
        "total_penalty_points": total_penalty_points,
        "review_required": review_required
    }
    
    # Safely add escalation_state in case the field exists on the DocType
    try:
        if frappe.get_meta("Proctor Session").has_field("escalation_state"):
            update_dict["escalation_state"] = escalation_state
    except Exception:
        pass

    frappe.db.set_value("Proctor Session", session_id, update_dict, update_modified=True)

@frappe.whitelist(allow_guest=True)
def delete_session(session_name: str):
    """Delete a Proctor Session document.

    Args:
        session_name (str): Name of the session to delete.
    Returns:
        dict: Success flag.
    """
    if not session_name:
        raise frappe.exceptions.ValidationError(_("Session name is required"))
    try:
        doc = frappe.get_doc("Proctor Session", session_name)
        doc.delete()
        return {"success": True}
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Failed to delete Proctor Session")
        raise frappe.exceptions.ValidationError(_("Unable to delete Proctor Session"))

@frappe.whitelist(allow_guest=True)
def delete_candidate_data(session_name: str):
    """Delete all candidate proctoring data and IQ Test Response in sequence.
    Order of deletion:
    1. Proctor Evidence
    2. Proctor Event
    3. Proctor Session
    4. IQ Test Response
    """
    if not session_name:
        raise frappe.exceptions.ValidationError(_("Session name is required"))
    try:
        session_doc = frappe.get_doc("Proctor Session", session_name)
    except Exception as exc:
        raise frappe.exceptions.ValidationError(_("Session not found"))
    
    # 1. Delete Proctor Evidence
    frappe.db.delete("Proctor Evidence", {"session": session_name})
        
    # 2. Delete Proctor Event (Proctor Session Event is deleted by cascade)
    event_parent = frappe.db.get_value("Proctor Event", {"session": session_name}, "name")
    if event_parent:
        frappe.db.delete("Proctor Session Event", {"parent": event_parent})
        frappe.db.delete("Proctor Event", {"name": event_parent})
        
    # 3. Delete the session
    frappe.db.delete("Proctor Session", {"name": session_name})
    
    # 4. Delete the IQ Test Response
    if session_doc.entity_id:
        frappe.db.delete("IQ Test Response", {
            "ats_id": session_doc.entity_id,
            "email": session_doc.user_email
        })
            
    # Commit to ensure locks are released
    frappe.db.commit()
    
    return {"success": True}

@frappe.whitelist(allow_guest=True)
def list_sessions(filters: str = "{}", page: int = 1, limit: int = 20):
    """List Proctor Session documents with optional filters and pagination.

    Args:
        filters (str): JSON string of filter dict (e.g., {"status": "Open"}).
        page (int): 1‑based page number.
        limit (int): Number of records per page.
    Returns:
        dict: Paginated list of sessions and metadata.
    """
    try:
        filter_dict = frappe.parse_json(filters) if isinstance(filters, str) else filters
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Invalid JSON for list_sessions filters")
        raise frappe.exceptions.ValidationError(_("Invalid filters JSON"))

    page = int(page) if page else 1
    limit = int(limit) if limit else 20
    offset = (page - 1) * limit

    try:
        total = frappe.db.count("Proctor Session", filter_dict)
        records = frappe.get_all(
            "Proctor Session",
            fields="*",
            filters=filter_dict,
            limit_page_length=limit,
            limit_start=offset,
            order_by="creation desc",
        )
        return {
            "success": True,
            "sessions": records,
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit if total else 0,
        }
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Failed to list Proctor Sessions")
        raise frappe.exceptions.ValidationError(_("Unable to list sessions"))



@frappe.whitelist(allow_guest=True)
def get_session_details(session_id: str):
    """Retrieve detailed analytics for a single session.

    Returns session header, event list, evidence list, and violation summary.
    """
    if not session_id:
        raise frappe.exceptions.ValidationError(_("session_id is required"))
    if not frappe.db.exists("Proctor Session", session_id):
        raise frappe.exceptions.ValidationError(_("Session not found"))
    # Header
    session = frappe.get_doc("Proctor Session", session_id).as_dict()
    # Events
    event_parent = frappe.db.get_value("Proctor Event", {"session": session_id}, "name")
    events = []
    if event_parent:
        events = frappe.get_all(
            "Proctor Session Event",
            filters={"parent": event_parent},
            fields=["name", "event_type", "severity", "occurred_at", "penalty_points", "metadata"],
            order_by="occurred_at asc",
        )
    # Evidence
    evidence = frappe.get_all(
        "Proctor Evidence",
        filters={"session": session_id},
        fields=["name", "evidence_type", "sharepoint_url", "thumbnail_url", "captured_at", "metadata"],
        order_by="captured_at asc",
    )
    # Map evidence URLs to dynamic proxy endpoint to prevent token expiration & allow browser media streaming
    host_url = ""
    if hasattr(frappe, "request") and frappe.request:
        host_url = getattr(frappe.request, "host_url", "")
    if not host_url:
        from frappe.utils import get_url
        host_url = get_url() or ""

    if host_url.endswith("/"):
        host_url = host_url[:-1]

    for ev in evidence:
        proxy_url = f"/api/method/ai_apps.api.proctor_api.proctor_session.get_evidence_file?evidence_id={ev['name']}"
        absolute_proxy_url = host_url + proxy_url
        ev["sharepoint_url"] = absolute_proxy_url
        if ev.get("evidence_type") == "screenshot":
            ev["thumbnail_url"] = absolute_proxy_url

    # Violation counts (exclude start/end markers)
    violations = [e for e in events if e.get("event_type") not in ("SESSION_START", "SESSION_END")]
    violation_counts = {
        "total": len(violations),
        "high": sum(1 for e in violations if e.get("severity") == "HIGH"),
        "medium": sum(1 for e in violations if e.get("severity") == "MEDIUM"),
        "low": sum(1 for e in violations if e.get("severity") == "LOW"),
    }
    return {
        "success": True,
        "session": session,
        "events": events,
        "evidence": evidence,
        "violation_counts": violation_counts,
    }


def _guess_evidence_mime(filename, evidence_type=None):
    name = (filename or "").lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".gif"):
        return "image/gif"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".wav"):
        return "audio/wav"
    if name.endswith(".mp3"):
        return "audio/mpeg"
    if name.endswith(".mp4") or name.endswith(".webm"):
        return "video/mp4"
    if (evidence_type or "").lower() == "audio":
        return "audio/wav"
    return "image/jpeg"


def _stream_file_response(filename, content, mime_type):
    """Return file bytes inline (for <img>/<audio> src), not a SharePoint redirect."""
    frappe.response["type"] = "download"
    frappe.response["filename"] = filename
    frappe.response["filecontent"] = content
    frappe.response["content_type"] = mime_type
    frappe.response["display_content_as"] = "inline"


@frappe.whitelist(allow_guest=True)
def get_evidence_file(evidence_id: str):
    """Stream a Proctor Evidence file from SharePoint through Frappe (no browser redirect)."""
    import json
    import mimetypes

    import requests
    from urllib.parse import quote

    if not evidence_id:
        frappe.throw(_("evidence_id is required"))

    if not frappe.db.exists("Proctor Evidence", evidence_id):
        frappe.throw(_("Evidence record not found"))

    evidence_doc = frappe.get_doc("Proctor Evidence", evidence_id)

    meta = {}
    if evidence_doc.metadata:
        try:
            meta = json.loads(evidence_doc.metadata) if isinstance(evidence_doc.metadata, str) else evidence_doc.metadata
        except Exception:
            pass

    sharepoint_path = meta.get("sharepoint_path")
    filename = (sharepoint_path or "").split("/")[-1] or f"{evidence_id}.jpg"
    mime_type = _guess_evidence_mime(filename, evidence_doc.evidence_type)

    def _redirect_fallback():
        fallback_url = evidence_doc.thumbnail_url or evidence_doc.sharepoint_url
        if fallback_url:
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = fallback_url
            return True
        return False

    if not sharepoint_path:
        if _redirect_fallback():
            return
        frappe.throw(_("SharePoint file path not found in evidence metadata"))

    try:
        from ai_apps.api.Sharepoint.sharepoint_auth import get_sharepoint_client

        client = get_sharepoint_client()
        site_id = client["site_id"]
        drive_id = client["drive_id"]
        graph_base_url = client["graph_base_url"]
        access_token = client["access_token"]

        encoded_segments = [quote(seg) for seg in sharepoint_path.split("/") if seg]
        encoded_path = "/".join(encoded_segments)
        meta_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}"

        headers = {"Authorization": f"Bearer {access_token}"}
        meta_resp = requests.get(meta_url, headers=headers, timeout=30)
        meta_resp.raise_for_status()
        meta_json = meta_resp.json()

        download_url = meta_json.get("@microsoft.graph.downloadUrl") or meta_json.get("webUrl")
        if not download_url:
            frappe.throw(_("Failed to retrieve direct download URL from Microsoft Graph"))

        file_resp = requests.get(download_url, timeout=60)
        file_resp.raise_for_status()
        content = file_resp.content
        if not content:
            frappe.throw(_("Evidence file is empty"))

        guessed = mimetypes.guess_type(filename)[0]
        if guessed:
            mime_type = guessed
        elif file_resp.headers.get("Content-Type"):
            mime_type = file_resp.headers["Content-Type"].split(";")[0]

        _stream_file_response(filename, content, mime_type)

    except Exception:
        frappe.log_error(
            title=f"Failed to fetch evidence file from SharePoint: {evidence_id}",
            message=frappe.get_traceback(),
        )
        if _redirect_fallback():
            return
        frappe.throw(_("Failed to load file from SharePoint"))


