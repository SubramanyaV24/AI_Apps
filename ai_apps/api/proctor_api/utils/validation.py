import frappe
from datetime import datetime
from typing import Dict, Any

def validate_session_payload(data: Dict[str, Any]) -> None:
    """Validate Proctor Session payload fields."""
    if not isinstance(data, dict):
        raise frappe.ValidationError("Payload must be a valid JSON object")

    required = ["candidate_id", "exam_id"]
    for field in required:
        if not data.get(field):
            raise frappe.ValidationError(f"Missing required field: {field}")

    # Validate started_at if provided
    started_at = data.get("started_at")
    if started_at:
        try:
            # support standard ISO or YYYY-MM-DD HH:MM:SS format
            if "T" in started_at:
                datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            else:
                datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise frappe.ValidationError("Invalid started_at format. Use YYYY-MM-DD HH:MM:SS or ISO format")

    # Validate IP address format (simple check)
    ip = data.get("ip_address")
    if ip and not isinstance(ip, str):
        raise frappe.ValidationError("ip_address must be a string")

def validate_event_payload(data: Dict[str, Any]) -> None:
    """Validate Proctor Event payload fields."""
    if not isinstance(data, dict):
        raise frappe.ValidationError("Payload must be a valid JSON object")

    required = ["session", "event_type"]
    for field in required:
        if not data.get(field):
            raise frappe.ValidationError(f"Missing required field: {field}")

    # Check session exists in Frappe DB
    session_id = data["session"]
    if not frappe.db.exists("Proctor Session", session_id):
        raise frappe.ValidationError(f"Proctor Session {session_id} does not exist")

    # Check confidence score
    confidence = data.get("confidence_score")
    if confidence is not None:
        try:
            val = float(confidence)
            if not (0.0 <= val <= 1.0):
                raise frappe.ValidationError("confidence_score must be between 0.0 and 1.0")
        except ValueError:
            raise frappe.ValidationError("confidence_score must be a numeric value")
