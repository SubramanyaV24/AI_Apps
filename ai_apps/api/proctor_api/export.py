import frappe
from frappe.utils.pdf import get_pdf
from ai_apps.api.proctor_api.proctor_session import get_session_details
from frappe.utils import format_datetime

@frappe.whitelist()
def generate_pdf(session_id):
    if not session_id:
        frappe.throw("Session ID is required")
        
    raw_details = get_session_details(session_id)
    
    # Merge session dict so top-level keys like 'status', 'user_name' work in Jinja
    details = {}
    details.update(raw_details.get("session", {}))
    details.update(raw_details)
    
    # Enrich events with evidence URLs
    events = details.get("events", [])
    evidence_list = details.get("evidence", [])
    
    # Create a map of event name to evidence URLs
    evidence_map = {}
    candidate_photo = None
    for ev in evidence_list:
        if ev.get("event"):
            url = ev.get("original_sharepoint_url") or ev.get("sharepoint_url")
            # just take the first one
            if url and ev["event"] not in evidence_map:
                evidence_map[ev["event"]] = {
                    "thumbnail": ev.get("thumbnail_url"),
                    "url": url
                }
                
    browser_info = "Unknown"
    for evt in events:
        if evt.get("event_type") in ("SESSION_START", "SYSTEM_INFO"):
            if evt.get("metadata"):
                try:
                    import json
                    meta = json.loads(evt.get("metadata", "{}"))
                    if meta.get("browser") or meta.get("userAgent"):
                        browser_info = meta.get("browser") or meta.get("userAgent")
                except Exception:
                    pass
            if not candidate_photo and evt.get("name") in evidence_map:
                candidate_photo = evidence_map[evt["name"]]["thumbnail"]
                candidate_photo_url = evidence_map[evt["name"]]["url"]
                
    if not candidate_photo:
        for ev in evidence_list:
            if ev.get("evidence_type") == "screenshot":
                try:
                    import json
                    meta = json.loads(ev.get("metadata", "{}"))
                    if str(meta.get("filename", "")).startswith("SESSION_START_"):
                        candidate_photo = ev.get("thumbnail_url")
                        candidate_photo_url = ev.get("original_sharepoint_url") or ev.get("sharepoint_url")
                        break
                except Exception:
                    pass

    details["candidate_photo"] = candidate_photo
    details["candidate_photo_url"] = candidate_photo_url if 'candidate_photo_url' in locals() else None
    details["browser"] = browser_info
                
    for event in events:
        event["timestamp_formatted"] = format_datetime(event.get("occurred_at"), "HH:mm:ss") if event.get("occurred_at") else ""
        if event.get("name") in evidence_map:
            event["image_url"] = evidence_map[event.get("name")]["url"]
            
    # Calculate stats
    violations = [e for e in events if e.get("event_type") not in ("SESSION_START", "SESSION_END")]
    
    violation_counts = {}
    for v in violations:
        evt_type = v.get("event_type")
        if evt_type not in violation_counts:
            violation_counts[evt_type] = {
                "label": evt_type,
                "count": 0,
                "severity": v.get("severity")
            }
        violation_counts[evt_type]["count"] += 1
        
    expected = ["GAZE_AWAY", "MULTIPLE_PEOPLE", "NO_FACE", "TAB_SWITCHED", "FULLSCREEN_EXITED", "COPY_PASTE", "RIGHT_CLICK"]
    for evt in expected:
        if evt not in violation_counts:
            violation_counts[evt] = {
                "label": evt,
                "count": 0,
                "severity": "LOW"
            }
            
    stats = sorted(violation_counts.values(), key=lambda x: x["count"], reverse=True)
    
    # Calculate severity counts
    severity_counts = {
        "critical": sum(1 for v in violations if v.get("severity") == "CRITICAL"),
        "high": sum(1 for v in violations if v.get("severity") == "HIGH"),
        "moderate": sum(1 for v in violations if v.get("severity") == "MEDIUM" or v.get("severity") == "MODERATE"),
        "low": sum(1 for v in violations if v.get("severity") == "LOW"),
    }
    
    # add to details
    details["stats"] = stats
    details["logs"] = violations
    details["severity_counts"] = severity_counts
    
    html = frappe.render_template(
        "ai_apps/api/proctor_api/templates/proctor_report.html",
        {"details": details, "frappe": frappe}
    )
    
    frappe.local.response.filename = f"Session_Report_{session_id}.pdf"
    frappe.local.response.filecontent = get_pdf(html)
    frappe.local.response.type = "download"
