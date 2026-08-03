import frappe
import json
import time
from frappe import _
from ai_apps.api.proctor_api.rule_engine import RuleEngine, Event as EngineEvent, safe_numeric

# -------------------------------------------------------------------------
# Helper: ensure a Proctor Session exists for the given UUID.
# -------------------------------------------------------------------------
def _get_or_create_session(session_id: str | None = None):
    """
    Return a valid existing session identifier.

    * ``session_id`` **must** be provided. If it is ``None`` or empty, a
      ``frappe.exceptions.ValidationError`` is raised – callers should create a
      session via the ``start_session`` endpoint first.
    * If ``session_id`` is supplied but the corresponding ``Proctor Session`` does
      not exist, a ``frappe.exceptions.ValidationError`` is raised. No new session
      is created.
    """
    if not session_id:
        raise frappe.exceptions.ValidationError(_("session is required"))

    # Verify the supplied session exists
    if not frappe.db.exists("Proctor Session", session_id):
        raise frappe.exceptions.ValidationError(_(f"Session {session_id} does not exist. Use the Proctor Session document name (e.g., PS00054) returned by start_session"))

    # Session exists – return its identifier
    return session_id


@frappe.whitelist(allow_guest=True)
def evaluate_event(**kwargs):
    """Endpoint called by the ML server to evaluate a single detection event.

    Expected JSON payload (keys may be sent as form arguments):
        session (str):                 Proctor Session identifier (required)
        event_type (str):            Type of the detection (e.g. MULTIPLE_PEOPLE)
        confidence_score (float):     Model confidence (optional, default 1.0)
        value (int|float):            Value for threshold rules (optional)
        duration_ms (int):            Accumulated duration for duration rules (optional)
        metadata (dict|str):          Arbitrary extra data, will be stored with the child row
    """
    frappe.logger().info("[evaluate_event] CALLED! Incoming kwargs: {}".format(repr(kwargs)))
    try:
        payload = frappe._dict(kwargs)
        payload.pop("cmd", None)
    except Exception as exc:
        raise frappe.exceptions.ValidationError(_("Invalid JSON payload"))

    # Flatten nested payload dictionary if sent by client
    inner_payload = payload.get("payload")
    if inner_payload:
        if isinstance(inner_payload, str):
            try:
                inner_payload = json.loads(inner_payload)
            except Exception:
                inner_payload = {}
        if isinstance(inner_payload, dict):
            for k, v in inner_payload.items():
                if k not in payload:
                    payload[k] = v
            payload.pop("payload", None)

    session = payload.get("session")
    event_type = payload.get("event_type") or payload.get("title")
    if not session:
        raise frappe.exceptions.ValidationError(_("session is required"))
    if not event_type:
        raise frappe.exceptions.ValidationError(_("event_type is required"))

    session = _get_or_create_session(session)
    # Build Event object for the rule engine
    event_payload = {}
    # copy known optional fields if present
    for key in ["value", "duration_ms", "confidence_score"]:
        if key in payload:
            event_payload[key] = safe_numeric(payload[key])

    # Initialise and load rules
    engine = RuleEngine()
    engine.load_rules(force_reload=True)
    
    # We no longer run engine.process_event() since the legacy scoring engine is removed.
    # We simply process the raw signal through the severity pipeline later.
    # To keep the response format consistent, we assume no immediate synchronous violations 
    # (they are handled asynchronously or aggregated).
    violations = []

    # Record the event using existing proctor_event logic for consistency
    # Re‑use the same child insertion path as create_event
    from ai_apps.api.proctor_api.proctor_event import create_event
    # Forward all original payload plus a flag indicating this came from evaluation
    payload["source"] = "ML"
    payload["detector"] = "rule_engine"

    # Merge violations with any existing metadata (like evidence/message)
    meta_dict = {}
    existing_meta = payload.get("metadata")
    if existing_meta:
        if isinstance(existing_meta, str):
            try:
                meta_dict = json.loads(existing_meta)
            except Exception:
                meta_dict = {"raw_metadata": existing_meta}
        elif isinstance(existing_meta, dict):
            meta_dict = existing_meta

    # Extract top-level evidence (image/audio base64) sent directly in the WS event
    # WS events have shape: { event_type, session, payload: { value, metadata, ... }, evidence }
    # HTTP SDK events have shape: { event_type, session, evidence, metadata, value, ... }
    top_level_evidence = payload.get("evidence")
    frappe.logger().info(f"[evaluate_event] session={session} event_type={event_type} has_top_evidence={bool(top_level_evidence)}, top_evidence_length={len(str(top_level_evidence)) if top_level_evidence else 0}, payload_keys={list(payload.keys())}")

    # Also check inside the nested payload dict (WS path sometimes nests it there)
    if not top_level_evidence:
        inner = payload.get("payload")
        frappe.logger().info(f"[evaluate_event] checking inner payload: inner exists? {bool(inner)}, type: {type(inner)}")
        if isinstance(inner, dict):
            top_level_evidence = inner.get("evidence")
            frappe.logger().info(f"[evaluate_event] found inner evidence: {bool(top_level_evidence)}, length: {len(str(top_level_evidence)) if top_level_evidence else 0}")

    if top_level_evidence:
        meta_dict["evidence"] = top_level_evidence
        frappe.logger().info(f"[evaluate_event] added evidence to meta_dict, meta_dict now has keys: {list(meta_dict.keys())}")

    if violations:
        meta_dict["violations"] = [v for v in violations]
    
    payload["metadata"] = json.dumps(meta_dict)
    # Log what we're passing to create_event
    create_event_log_payload = {k: v for k, v in payload.items() if k != "evidence"}
    if "evidence" in payload:
        create_event_log_payload["evidence_length"] = len(str(payload["evidence"])) if payload["evidence"] else 0
        create_event_log_payload["evidence_present"] = bool(payload["evidence"])
    # Run the severity engine pipeline
    severity_payload = None
    triggered_violations = []
    try:
        severity_payload = _run_severity_pipeline(session, engine, triggered_violations, event_type, payload, event_payload)
    except Exception as _sev_exc:
        frappe.log_error(
            title="[severity_engine] Pipeline error",
            message=str(_sev_exc),
        )

    if triggered_violations:
        payload["severity"] = triggered_violations[0].get("severity", "LOW")
        meta_dict["violations"] = triggered_violations
        payload["metadata"] = json.dumps(meta_dict)

    # Call create_event to store the row
    result = create_event(**payload)

    # Calculate worst UI mode
    ui_modes = {"toast": 1, "warning_banner": 2, "serious_modal": 3, "critical_modal": 4}
    worst_ui_mode = "toast"
    worst_message = ""
    req_ack = False

    for v in triggered_violations:
        v_mode = v.get("ui_mode", "toast")
        if ui_modes.get(v_mode, 0) >= ui_modes.get(worst_ui_mode, 0):
            worst_ui_mode = v_mode
            worst_message = v.get("message", "")
            if v.get("requires_acknowledgement"):
                req_ack = True

    # Sync metrics (must run after severity pipeline updates Redis)
    try:
        from ai_apps.api.proctor_api.proctor_session import sync_session_metrics
        sync_session_metrics(session)
    except Exception as e:
        frappe.log_error(title="sync_session_metrics failed", message=str(e))

    response = {
        "success": True,
        "session": session,
        "violations": triggered_violations,
        "ui_mode": worst_ui_mode if triggered_violations else None,
        "message": worst_message if triggered_violations else None,
        "requires_acknowledgement": req_ack if triggered_violations else False,
        "event_record": result,
    }

    if severity_payload:
        response["severity_engine"] = severity_payload
        response["risk_band"] = severity_payload.get("risk_band")
        from ai_apps.api.proctor_api.severity_engine import get_escalation_state
        response["escalation_state"] = get_escalation_state(session)

    return response


def _run_severity_pipeline(session, engine, triggered_violations, event_type, payload, event_payload):
    """Run the threshold + severity engine pipeline.
    
    Returns the updated risk payload.
    """
    from ai_apps.api.proctor_api.threshold_engine import process_raw_signal
    from ai_apps.api.proctor_api.severity_engine import process_violation, compute_risk_value
    from ai_apps.api.proctor_api.confidence_map import resolve_confidence

    now_ms = int(time.time() * 1000)

    # Find the matching rule from the loaded rule list
    matching_rule = None
    for rule in engine._rules:
        if rule.event_type == event_type or rule.rule_id == event_type:
            matching_rule = rule
            break

    if matching_rule is None:
        return compute_risk_value(session)

    # Determine raw_state for threshold engine
    raw_state = "triggered"

    # Resolve confidence — use the raw float from payload if provided
    raw_conf = float(event_payload.get("confidence_score") or 1.0)
    confidence = resolve_confidence(matching_rule.rule_id, raw_conf)

    def _on_violation(rule, sid, conf, ts_ms):
        """Callback fired by threshold_engine when threshold is met."""
        process_violation(sid, rule, conf, ts_ms)
        triggered_violations.append({
            "rule_id": rule.rule_id,
            "severity": (rule.severity_tier or "LOW").upper(),
            "ui_mode": "toast",
            "message": f"Violation: {rule.rule_id}",
            "requires_acknowledgement": False,
        })

    # Process through the pipeline if the rule has new-style fields
    if matching_rule.threshold_type:
        process_raw_signal(
            session_id=session,
            rule=matching_rule,
            raw_state=raw_state,
            confidence=confidence,
            timestamp_ms=now_ms,
            on_violation=_on_violation,
        )

    return compute_risk_value(session)
