import frappe
import json
import time

DEFAULT_RULES = [
    # ── Pattern/unconfirmed rules (disabled until pattern_expression defined) ──────
    {
        "rule_name": "NO_AUDIO",
        "rule_id": "NO_AUDIO",
        "enabled": 1,  # monitor.js emits on getUserMedia (audio) failure
        "condition_type": "threshold",
        "threshold_ms": 0,
        "window_ms": 0,
        "cooldown_ms": 30000,
        "severity": "HIGH",
        "penalty_points": 20,
        "description": "Microphone access denied or audio stream unavailable",
        "system_rule": 0,
    },

    # ── monitor.js emits via Autoproctor 'violation' event → reportAlert → value:1 ─
    {
        "rule_name": "NO_VIDEO",
        "rule_id": "NO_VIDEO",
        "enabled": 1,  # monitor.js emits on getUserMedia failure
        "condition_type": "threshold",
        "threshold_ms": 0,
        "window_ms": 0,
        "cooldown_ms": 30000,
        "severity": "CRITICAL",
        "penalty_points": 50,
        "description": "Camera access denied or video stream unavailable",
        "system_rule": 0,
    },
    {
        "rule_name": "FULLSCREEN_EXIT",
        "rule_id": "FULLSCREEN_EXIT",
        "enabled": 1,  # monitor.js fullscreenchange listener is live
        "condition_type": "threshold",
        "threshold_ms": 0,
        "window_ms": 0,
        "cooldown_ms": 5000,
        "severity": "MEDIUM",
        "penalty_points": 10,
        "description": "Candidate exited fullscreen mode",
        "system_rule": 0,
    },

    # ── Threshold rules: reportAlert sends value:1 (default) ─────────────────────
    {
        "rule_name": "NOISE",
        "rule_id": "NOISE",
        "enabled": 1,  # reportAlert default payload value:1
        "condition_type": "threshold",
        "threshold_ms": 0,
        "window_ms": 0,
        "cooldown_ms": 10000,
        "severity": "MEDIUM",
        "penalty_points": 5,
        "description": "Background noise detected",
        "system_rule": 1,
    },
    {
        "rule_name": "NO_FACE",
        "rule_id": "NO_FACE",
        "enabled": 1,  # reportAlert sends value:0 → engine special-cases value==0
        "condition_type": "threshold",
        "threshold_ms": 0,
        "window_ms": 0,
        "cooldown_ms": 1000,
        "severity": "MEDIUM",
        "penalty_points": 5,
        "description": "No face detected",
        "system_rule": 1,
    },
    {
        "rule_name": "MULTIPLE_PEOPLE",
        "rule_id": "MULTIPLE_PEOPLE",
        "enabled": 1,  # reportAlert sends value:faceCount (>=2)
        "condition_type": "threshold",
        "threshold_ms": 0,
        "window_ms": 0,
        "cooldown_ms": 1000,
        "severity": "HIGH",
        "penalty_points": 15,
        "description": "Multiple people detected",
        "system_rule": 1,
    },
    {
        "rule_name": "MULTIPLE_FACES",
        "rule_id": "MULTIPLE_FACES",
        "enabled": 1,
        "condition_type": "threshold",
        "threshold_ms": 0,
        "window_ms": 0,
        "cooldown_ms": 1000,
        "severity": "HIGH",
        "penalty_points": 15,
        "description": "Multiple faces detected",
        "system_rule": 1,
    },
    {
        "rule_name": "GAZE_AWAY",
        "rule_id": "GAZE_AWAY",
        "enabled": 1,  # reportAlert will send value:1 after frontend fix below
        "condition_type": "threshold",
        "threshold_ms": 0,
        "window_ms": 0,
        "cooldown_ms": 1000,
        "severity": "LOW",
        "penalty_points": 2,
        "description": "Gaze away detected",
        "system_rule": 1,
    },
    {
        "rule_name": "MOBILE_PHONE",
        "rule_id": "MOBILE_PHONE",
        "enabled": 1,  # reportAlert sends value:1
        "condition_type": "threshold",
        "threshold_ms": 0,
        "window_ms": 0,
        "cooldown_ms": 1000,
        "severity": "HIGH",
        "penalty_points": 30,
        "description": "Mobile phone detected",
        "system_rule": 1,
    },
    {
        "rule_name": "OBJECT_DETECTED",
        "rule_id": "OBJECT_DETECTED",
        "enabled": 1,  # reportAlert default payload value:1
        "condition_type": "threshold",
        "threshold_ms": 0,
        "window_ms": 0,
        "cooldown_ms": 1000,
        "severity": "HIGH",
        "penalty_points": 25,
        "description": "Restricted object detected (e.g. book, phone, device)",
        "system_rule": 1,
    },
    {
        "rule_name": "FACE_COVERED",
        "rule_id": "FACE_COVERED",
        "enabled": 1,  # reportAlert will send value:1 after frontend fix below
        "condition_type": "threshold",
        "threshold_ms": 0,
        "window_ms": 0,
        "cooldown_ms": 1000,
        "severity": "LOW",
        "penalty_points": 3,
        "description": "Face covered detected",
        "system_rule": 1,
    },
    {
        # AUDIO_VAD sends duration_ms, not value — use duration condition type.
        # Engine reads event.payload.get('duration_ms') and accumulates it.
        "rule_name": "AUDIO_VAD",
        "rule_id": "AUDIO_VAD",
        "enabled": 1,
        "condition_type": "duration",
        "threshold_ms": 5000,  # cumulative ms of multi-speaker audio before firing
        "window_ms": 0,
        "cooldown_ms": 10000,
        "severity": "MEDIUM",
        "penalty_points": 10,
        "description": "Cumulative overlapping-speech duration exceeded threshold",
        "system_rule": 1,
    },
    {
        "rule_name": "TAB_SWITCHED",
        "rule_id": "TAB_SWITCHED",
        "enabled": 1,  # reportAlert default payload value:1
        "condition_type": "threshold",
        "threshold_ms": 0,
        "window_ms": 0,
        "cooldown_ms": 1000,
        "severity": "HIGH",
        "penalty_points": 10,
        "description": "Tab switched detected",
        "system_rule": 1,
    },
    {
        "rule_name": "MULTIPLE_MONITORS",
        "rule_id": "MULTIPLE_MONITORS",
        "enabled": 1,  # reportAlert default payload value:1
        "condition_type": "threshold",
        "threshold_ms": 0,
        "window_ms": 0,
        "cooldown_ms": 1000,
        "severity": "HIGH",
        "penalty_points": 20,
        "description": "Multiple monitors detected",
        "system_rule": 1,
    },
]

@frappe.whitelist(allow_guest=True)
def check_proctor_data():
    # Get all Proctor Rules
    rules = frappe.get_all("Proctor Rule", fields=["*"])
    # Get last 20 Proctor Events
    events = frappe.get_all("Proctor Event", fields=["*"], limit=20, order_by="creation desc")
    # Get all Proctor Session Events
    session_events = []
    for event in events:
        doc = frappe.get_doc("Proctor Event", event.name)
        session_events.extend([d.as_dict() for d in doc.proctor_session_event])
    return {
        "rules": rules,
        "events": events,
        "session_events": session_events
    }

@frappe.whitelist(allow_guest=True)
def create_default_rules(force_update: bool = False):
    """
    Seed / sync production Proctor Rules.

    - If a rule doesn't exist, it's created.
    - If it exists and force_update=True, every field (condition_type,
      threshold_ms, window_ms, cooldown_ms, severity, penalty_points,
      pattern_expression, description) is overwritten to match DEFAULT_RULES.
    - If it exists and force_update=False (default), it's left untouched —
      useful if you've since hand-tuned a rule in the UI and don't want
      this endpoint to clobber it.
    """
    created, updated, skipped = [], [], []

    for rule_data in DEFAULT_RULES:
        existing_name = frappe.db.exists("Proctor Rule", rule_data["rule_name"])

        if not existing_name:
            doc = frappe.new_doc("Proctor Rule")
            doc.update(rule_data)
            doc.insert(ignore_permissions=True)
            created.append(rule_data["rule_name"])
            continue

        if force_update:
            doc = frappe.get_doc("Proctor Rule", existing_name)
            doc.update(rule_data)
            doc.save(ignore_permissions=True)
            updated.append(rule_data["rule_name"])
        else:
            skipped.append(rule_data["rule_name"])

    frappe.db.commit()
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "message": f"Created {len(created)}, updated {len(updated)}, skipped {len(skipped)}"
    }

@frappe.whitelist(allow_guest=True)
def run_proctor_test():
    """Run a complete test of the proctoring flow"""
    results_log = []
    
    # 1. Create test session
    results_log.append("--- STEP 1: Creating Test Session ---")
    try:
        from ai_apps.api.proctor_api.proctor_session import start_session
        session_result = start_session(
            user_id="test_user_2",
            entity_id="test_entity_2",
            entity_type="quiz"
        )
        results_log.append(f"Session creation result: {json.dumps(session_result)}")
        session_name = session_result.get("session_id")
        if not session_name:
            session_list = frappe.get_all("Proctor Session", filters={"user_id": "test_user_2"}, limit=1, order_by="creation desc")
            if session_list:
                session_name = session_list[0].name
        results_log.append(f"Using session: {session_name}")
    except Exception as e:
        results_log.append(f"❌ Session creation failed: {str(e)}")
        import traceback
        results_log.append(traceback.format_exc())
        return {"log": results_log}
    
    # 2. Check rules
    results_log.append("\n--- STEP 2: Checking Rules ---")
    rules = frappe.get_all("Proctor Rule", fields=["*"], order_by="rule_name")
    results_log.append(f"Found {len(rules)} rules: {[r.rule_name for r in rules]}")
    
    # 3. Define test events
    test_events = [
        {
            "name": "NO_FACE",
            "payload": {
                "session": session_name,
                "event_type": "NO_FACE",
                "value": 0,
                "metadata": json.dumps({"message": "No face detected"})
            }
        },
        {
            "name": "MULTIPLE_PEOPLE",
            "payload": {
                "session": session_name,
                "event_type": "MULTIPLE_PEOPLE",
                "value": 2,
                "metadata": json.dumps({"message": "Multiple faces detected"})
            }
        },
        {
            "name": "GAZE_AWAY",
            "payload": {
                "session": session_name,
                "event_type": "GAZE_AWAY",
                "confidence_score": 0.95,
                "metadata": json.dumps({"message": "Gaze away detected"})
            }
        },
        {
            "name": "MOBILE_PHONE",
            "payload": {
                "session": session_name,
                "event_type": "MOBILE_PHONE",
                "value": 1,
                "metadata": json.dumps({"message": "Mobile phone detected"})
            }
        },
        {
            "name": "FACE_COVERED",
            "payload": {
                "session": session_name,
                "event_type": "FACE_COVERED",
                "confidence_score": 0.9,
                "metadata": json.dumps({"message": "Face covered detected"})
            }
        },
        {
            "name": "AUDIO_VAD",
            "payload": {
                "session": session_name,
                "event_type": "AUDIO_VAD",
                "duration_ms": 5000,
                "metadata": json.dumps({"message": "Audio VAD detected"})
            }
        },
        {
            "name": "TAB_SWITCHED",
            "payload": {
                "session": session_name,
                "event_type": "TAB_SWITCHED",
                "value": 1,
                "metadata": json.dumps({"message": "Tab switched detected"})
            }
        },
        {
            "name": "MULTIPLE_MONITORS",
            "payload": {
                "session": session_name,
                "event_type": "MULTIPLE_MONITORS",
                "value": 1,
                "metadata": json.dumps({"message": "Multiple monitors detected"})
            }
        }
    ]
    
    # 4. Process events
    from ai_apps.api.proctor_api.evaluate_event import evaluate_event
    results_table = []
    
    for event in test_events:
        results_log.append(f"\n--- Processing {event['name']} ---")
        row = {
            "Event": event['name'],
            "ML Detected": "Simulated",
            "reportAlert": "Simulated",
            "evaluateEvent": "No",
            "Rule Matched": "No",
            "Violation Created": "No",
            "Stored": "No"
        }
        
        try:
            results_log.append(f"Payload: {json.dumps(event['payload'])}")
            eval_result = evaluate_event(**event['payload'])
            results_log.append(f"evaluate_event result: {json.dumps(eval_result)}")
            row["evaluateEvent"] = "Yes"
            
            if eval_result.get("violations") and len(eval_result["violations"]) > 0:
                row["Rule Matched"] = "Yes"
                row["Violation Created"] = "Yes"
            
            if eval_result.get("event_record"):
                row["Stored"] = "Yes"
            
        except Exception as e:
            results_log.append(f"Error: {str(e)}")
            import traceback
            results_log.append(traceback.format_exc())
        
        results_table.append(row)
        time.sleep(0.5)
    
    # 5. Get stored events
    results_log.append("\n--- Stored Events ---")
    parent_event = frappe.get_all("Proctor Event", filters={"session": session_name}, limit=1, order_by="creation desc")
    if parent_event:
        child_events = frappe.get_all("Proctor Session Event", filters={"parent": parent_event[0].name}, fields=["*"], order_by="creation")
        results_log.append(f"Stored {len(child_events)} events: {[ce.event_type for ce in child_events]}")
    
    return {
        "log": results_log,
        "table": results_table
    }
