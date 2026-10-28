import json
import threading
import time
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import frappe


def safe_numeric(value: Any) -> Optional[int | float]:
    """Safely convert a value to int or float. Returns None if conversion fails."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return int(value)
    except (ValueError, TypeError):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


# ---------- Types ----------

@dataclass(frozen=True)
class Event:
    """Simple event representation.
    - `event_type`: string identifying the type of event (e.g., "GAZE_AWAY")
    - `payload`: arbitrary mapping containing whatever data the rule needs. For
      threshold rules, a `value` key is expected. For duration rules, a
      `duration_ms` key is expected. For frequency rules, no extra data is needed
      beyond the occurrence timestamp (handled internally).
    """
    event_type: str
    payload: Dict[str, Any]
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))


@dataclass
class Condition:
    type: str  # "threshold", "duration", "frequency", "pattern"
    threshold: Optional[int] = None  # used for threshold & duration
    window_ms: Optional[int] = None  # used for duration, frequency, pattern
    count: Optional[int] = None  # used for frequency (events required)
    pattern_expression: Optional[str] = None  # used for pattern (comma separated prior events)


@dataclass
class Rule:
    rule_id: str
    event_type: str
    enabled: bool
    condition: Condition
    severity: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL" — legacy field
    penalty_points: int
    cooldown_ms: int

    # ── Severity Engine fields (Phase 1 / new) ────────────────────────────────
    # severity_tier: input anchor tier for the severity engine.
    #   Values: "Low", "Medium", "High", "Critical" (Title-case, from DocType Select)
    severity_tier: str = ""
    # threshold_type: how raw ML signals are gated before reaching the severity engine.
    #   Values: "Instant", "Duration", "Frequency"
    #   Falls back to condition_type (legacy) if not set.
    threshold_type: str = ""
    # duration_ms: cumulative signal ms required to fire (Duration rules only)
    duration_ms: Optional[int] = None
    # frequency_count: occurrences within window required to fire (Frequency rules only)
    frequency_count: Optional[int] = None
    # frequency_window_ms: sliding window for frequency counting (Frequency rules only)
    frequency_window_ms: Optional[int] = None
    # reset_on_clear: if True, the accumulator resets after a violation fires.
    #   Set False for cumulative rules like lookingAway.
    reset_on_clear: bool = True
    # correlation_window_ms: override for per-rule correlation window (0 = use engine default)
    correlation_window_ms: int = 0

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Rule":
        """Create a Rule instance from a dictionary.

        Handles three input shapes:
        1. Nested ``condition`` dict (original JSON schema)
        2. Flat ERPNext API shape (legacy fields: condition_type, threshold_ms, etc.)
        3. Flat ERPNext API shape with new severity engine fields (threshold_type, etc.)

        New fields fall back gracefully when absent so existing DB records continue
        to work without migration.
        """
        # frappe.logger().info(f"[Rule.from_dict] Received dict: {d}")

        # --- Legacy Condition handling (backward compat) ----------------------
        if "condition" in d and isinstance(d["condition"], dict):
            cond_data = d["condition"]
        else:
            cond_data = {
                "type": d.get("condition_type", "threshold"),
                "threshold": d.get("threshold_ms") or d.get("threshold"),
                "windowMs": d.get("window_ms") or d.get("windowMs"),
                "count": d.get("count"),
                "pattern_expression": d.get("pattern_expression"),
            }
        # frappe.logger().info(f"[Rule.from_dict] cond_data: {cond_data}")
        condition = Condition(
            type=cond_data.get("type"),
            threshold=safe_numeric(cond_data.get("threshold")),
            window_ms=safe_numeric(cond_data.get("windowMs")),
            count=safe_numeric(cond_data.get("count")),
            pattern_expression=cond_data.get("pattern_expression"),
        )
        # frappe.logger().info(
        #     f"[Rule.from_dict] Created condition: type={condition.type}, "
        #     f"threshold={condition.threshold}, window_ms={condition.window_ms}, "
        #     f"count={condition.count}, pattern_expression={condition.pattern_expression}"
        # )

        # --- New severity engine fields (with safe defaults) ------------------
        # threshold_type: prefer new field, fall back to capitalised condition_type
        raw_threshold_type = d.get("threshold_type") or ""
        if not raw_threshold_type or raw_threshold_type == "Select an option":
            # Map legacy condition_type → threshold_type
            _legacy_map = {
                "threshold": "Instant",
                "duration": "Duration",
                "frequency": "Frequency",
                "pattern": "Frequency",  # closest semantic equivalent
            }
            raw_threshold_type = _legacy_map.get(
                (d.get("condition_type") or "").lower(), ""
            )

        severity_tier = d.get("severity_tier") or ""
        if severity_tier == "Select an option":
            severity_tier = ""

        # reset_on_clear: DB stores as 0/1 (Check field)
        reset_val = d.get("reset_on_clear")
        if reset_val is None:
            reset_on_clear = True  # safe default
        else:
            reset_on_clear = bool(reset_val)

        # correlation_window_ms: rule-level override; 0 means use engine default
        correlation_window_ms = safe_numeric(d.get("correlation_window_ms")) or 0

        # --- Core rule fields -------------------------------------------------
        return Rule(
            rule_id=d.get("ruleId") or d.get("rule_id") or d.get("rule_name"),
            event_type=d.get("eventType") or d.get("event_type") or d.get("rule_name") or d.get("condition_type") or "UNKNOWN",
            enabled=d.get("enabled", True),
            condition=condition,
            severity=(d.get("severity") or "LOW").upper(),
            penalty_points=safe_numeric(d.get("penaltyPoints") or d.get("penalty_points")) or 0,
            cooldown_ms=safe_numeric(d.get("cooldownMs") or d.get("cooldown_ms")) or 0,
            # new severity engine fields
            severity_tier=severity_tier,
            threshold_type=raw_threshold_type,
            duration_ms=safe_numeric(d.get("duration_ms")),
            frequency_count=safe_numeric(d.get("frequency_count")),
            frequency_window_ms=safe_numeric(d.get("frequency_window_ms")),
            reset_on_clear=reset_on_clear,
            correlation_window_ms=int(correlation_window_ms),
        )


@dataclass
class Violation:
    rule_id: str
    severity: str
    penalty: float
    timestamp_ms: int
    ui_mode: str = "toast"
    message: str = ""
    requires_acknowledgement: bool = False
    # optional extra info for callers
    details: Dict[str, Any] = field(default_factory=dict)

# ---------- Session State ----------

class SessionStore:
    """Redis‑backed store for per‑session rule state, violations, and scores using frappe.cache()."""

    def __init__(self):
        self._lock = threading.RLock()
        self._local_scores = {}

    def _key(self, session_id: str, suffix: str) -> str:
        return f"proctor:{session_id}:{suffix}"

    # ---------- Raw Events ----------
    def record_event(self, session_id: str, event_type: str, timestamp_ms: int) -> None:
        with self._lock:
            key = self._key(session_id, "recent_events")
            lst = frappe.cache().get_value(key) or []
            lst.append({"event_type": event_type, "timestamp_ms": timestamp_ms})
            # keep events for up to 10 minutes (600,000 ms) to support patterns
            cutoff = timestamp_ms - 600000
            lst = [e for e in lst if e["timestamp_ms"] >= cutoff]
            frappe.cache().set_value(key, lst, expires_in_sec=86400)

    def get_recent_events(self, session_id: str, window_ms: int, now_ms: int) -> List[Dict[str, Any]]:
        with self._lock:
            key = self._key(session_id, "recent_events")
            lst = frappe.cache().get_value(key) or []
            cutoff = now_ms - window_ms
            return [e for e in lst if e["timestamp_ms"] >= cutoff]

    # ---------- Rule state ----------
    def get_rule_state(self, session_id: str, rule_id: str) -> Dict[str, Any]:
        with self._lock:
            key = self._key(session_id, f"rule:{rule_id}")
            state = frappe.cache().get_value(key)
            if not state:
                state = {"last_fired_at": 0, "accumulated_ms": 0, "occurrence_count": 0, "timestamps": []}
                frappe.cache().set_value(key, state, expires_in_sec=86400)
            return state

    def save_rule_state(self, session_id: str, rule_id: str, state: Dict[str, Any]) -> None:
        with self._lock:
            key = self._key(session_id, f"rule:{rule_id}")
            frappe.cache().set_value(key, state, expires_in_sec=86400)

    # ---------- Violations ----------
    def record_violation(self, session_id: str, violation: Violation) -> None:
        with self._lock:
            v_key = self._key(session_id, "violations")
            lst = frappe.cache().get_value(v_key) or []
            lst.append(violation.__dict__)
            frappe.cache().set_value(v_key, lst, expires_in_sec=86400)
            
            # update score
            score_key = self._key(session_id, "score")
            last_v_key = self._key(session_id, "last_violation_ms")
            
            # Current score includes any pending recovery
            current_score = self.get_score(session_id, current_time_ms=violation.timestamp_ms)
            new_score = max(0.0, current_score - violation.penalty)
            
            frappe.cache().set_value(score_key, new_score, expires_in_sec=86400)
            frappe.cache().set_value(last_v_key, violation.timestamp_ms, expires_in_sec=86400)
            self._local_scores[session_id] = new_score

    def recent_violations(self, session_id: str, within_ms: int, now_ms: int) -> List[Violation]:
        with self._lock:
            v_key = self._key(session_id, "violations")
            lst = frappe.cache().get_value(v_key) or []
            violations = [Violation(**v) for v in lst]
            return [v for v in violations if now_ms - v.timestamp_ms <= within_ms]

    # ---------- Scoring ----------
    def get_score(self, session_id: str, current_time_ms: int = None) -> float:
        if current_time_ms is None:
            current_time_ms = int(time.time() * 1000)
        with self._lock:
            score_key = self._key(session_id, "score")
            last_v_key = self._key(session_id, "last_violation_ms")
            
            score = frappe.cache().get_value(score_key)
            last_v_ms = frappe.cache().get_value(last_v_key)
            
            if score is None:
                # Reconstruct score from DB violations if cache has expired or was cleared
                parent_name = frappe.db.get_value("Proctor Event", {"session": session_id}, "name")
                last_v_ms = current_time_ms
                if parent_name:
                    events_data = frappe.get_all(
                        "Proctor Session Event",
                        filters={"parent": parent_name},
                        fields=["penalty_points", "event_type", "occurred_at"],
                        order_by="occurred_at asc"
                    )
                    violations = [e for e in events_data if e.get("event_type") not in ("SESSION_START", "SESSION_END")]
                    total_penalty = sum(e.get("penalty_points") or 0 for e in violations)
                    score = max(0.0, 100.0 - total_penalty)
                    if violations:
                        last_v_time = violations[-1].get("occurred_at")
                        if last_v_time:
                            last_v_ms = int(frappe.utils.get_datetime(last_v_time).timestamp() * 1000)
                else:
                    score = 100.0
                frappe.cache().set_value(score_key, score, expires_in_sec=86400)
                frappe.cache().set_value(last_v_key, last_v_ms, expires_in_sec=86400)
            
            if last_v_ms is None:
                last_v_ms = current_time_ms
                
            # Apply recovery (+1 point per 3 minutes of clean behavior)
            clean_ms = max(0, current_time_ms - last_v_ms)
            clean_minutes = clean_ms // 60000
            recovered = clean_minutes // 3
            
            current_score = min(100.0, score + recovered)
            self._local_scores[session_id] = current_score
            return current_score

    def reset(self, session_id: str) -> None:
        with self._lock:
            # delete all keys for the session
            prefixes = ["rule", "violations", "score", "last_violation_ms"]
            for suffix in prefixes:
                frappe.cache().delete_key(self._key(session_id, suffix))
            self._local_scores.pop(session_id, None)
# ---------- Rule Engine ----------

class RuleEngine:
    """Pure-Python rule engine with thread-safe in-memory state.

    Usage:
        engine = RuleEngine()
        engine.load_rules("rules.json")
        violations = engine.process_event(session_id, Event(...))
    """

    SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

    def __init__(self, correlation_window_ms: int = 30_000):
        self._rules: List[Rule] = []
        self._store = SessionStore()
        self.correlation_window_ms = correlation_window_ms
        self._global_lock = threading.RLock()  # protects rule list modifications

    # ---------- Rule loading ----------
    
    def load_rules(self, path: str | None = None, force_reload: bool = False) -> None:
        """Load rules from a local JSON file if provided, otherwise fetch from the Proctor Rule DocType via Frappe ORM.
        Caches rules in memory after first load; subsequent calls are no-ops unless force_reload is True or a path is given.
        """
        if not force_reload and self._rules:
            # Rules already loaded; skip reloading to avoid per-request DB hits.
            return
        if path and os.path.isfile(path):
            with self._global_lock:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                self._rules = [Rule.from_dict(item) for item in raw]
            return
        # Fetch from Frappe DocType
        raw = frappe.get_all("Proctor Rule", fields=["*"])
        with self._global_lock:
            self._rules = [Rule.from_dict(item) for item in raw]

    def reset_rules(self) -> None:
        """Reset the cached rules and force reload on next load_rules call"""
        with self._global_lock:
            self._rules = []

    def get_risk_band(self, score: float) -> str:
        """Map a trust score to a risk band based on industry default thresholds.
        Thresholds: >85 Low, >65 Medium, >40 High, else Critical.
        """
        if score > 85:
            return "LOW"
        if score > 65:
            return "MEDIUM"
        if score > 40:
            return "HIGH"
        return "CRITICAL"
        
    def get_escalation_state(self, session_id: str) -> str:
        """Get the current escalation state for a session based on trust score."""
        score = self.get_current_score(session_id)
        if score >= 90:
            return "NORMAL"
        elif score >= 75:
            return "WATCHING"
        elif score >= 50:
            return "WARNING"
        elif score >= 30:
            return "ESCALATED"
        else:
            return "CRITICAL_REVIEW"

    # ---------- Event processing ----------
    def process_event(self, session_id: str, event: Event) -> List[Violation]:
        """Process a single event and return any violations generated.
        Thread‑safe – internal locks protect shared state.
        """
        now_ms = event.timestamp_ms
        self._store.record_event(session_id, event.event_type, now_ms)
        
        violations: List[Violation] = []
        for rule in self._rules:
            if not rule.enabled:
                continue
            if rule.event_type != event.event_type:
                continue

            state = self._store.get_rule_state(session_id, rule.rule_id)

            # ----- Pre‑condition: cooldown -----
            if now_ms - state["last_fired_at"] < rule.cooldown_ms:
                continue

            # ----- Condition evaluation -----
            if not self._evaluate_condition(rule, event, state):
                continue

            # ----- Post‑condition: correlation -----
            severity = rule.severity
            penalty = self._calculate_penalty(rule, state)

            # correlation check – look for any other violation within window
            recent = self._store.recent_violations(session_id, self.correlation_window_ms, now_ms)
            if any(v.rule_id != rule.rule_id for v in recent):
                # elevate severity by one level if possible
                cur_idx = self.SEVERITY_ORDER.index(severity)
                if cur_idx < len(self.SEVERITY_ORDER) - 1:
                    severity = self.SEVERITY_ORDER[cur_idx + 1]
                    # increase penalty proportionally (simple approach: +50%)
                    penalty *= 1.5

            ui_mode, msg, req_ack = self._determine_ui_mode_and_message(rule, state)

            violation = Violation(
                rule_id=rule.rule_id,
                severity=severity,
                penalty=penalty,
                timestamp_ms=now_ms,
                ui_mode=ui_mode,
                message=msg,
                requires_acknowledgement=req_ack,
                details={"event": event.payload},
            )
            self._store.record_violation(session_id, violation)
            violations.append(violation)

            # update rule state for next evaluations
            state["last_fired_at"] = now_ms
            state["occurrence_count"] += 1
            # keep timestamps for frequency rules
            state.setdefault("timestamps", []).append(now_ms)
        return violations

    # ---------- Condition helpers ----------
    def _evaluate_condition(self, rule: Rule, event: Event, state: Dict[str, Any]) -> bool:
        cond = rule.condition
        if cond.type == "threshold":
            value = safe_numeric(event.payload.get("value"))
            threshold = safe_numeric(cond.threshold) or 0
            # frappe.logger().info(f"[RuleEngine _evaluate_condition] rule={rule.rule_id}, event_type={rule.event_type}, value={value!r} (type: {type(value)}), threshold={threshold!r} (type: {type(threshold)})")
            if value is None:
                return False
            # Special case: if threshold is -1, just check that value is present
            if threshold == -1:
                return True
            # For NO_FACE: if value is 0, treat it as a violation
            if rule.event_type == "NO_FACE" and value == 0:
                return True
            return value > threshold
        if cond.type == "duration":
            # duration rules store accumulated time in state
            inc = safe_numeric(event.payload.get("duration_ms")) or 0
            state["accumulated_ms"] += inc
            return state["accumulated_ms"] >= (safe_numeric(cond.threshold) or 0)
        if cond.type == "frequency":
            # keep a sliding window of timestamps in state["timestamps"]
            now = event.timestamp_ms
            timestamps = state.setdefault("timestamps", [])
            timestamps.append(now)
            # purge old entries outside the window
            window = safe_numeric(cond.window_ms) or 0
            while timestamps and now - timestamps[0] > window:
                timestamps.pop(0)
            required = safe_numeric(cond.count) or 0
            return len(timestamps) >= required
        if cond.type == "pattern":
            # A pattern can be a sequence of prior events (pattern_expression) 
            # AND/OR a frequency of the current event (count) within window_ms.
            window = safe_numeric(cond.window_ms) or 0
            now = event.timestamp_ms
            
            # 1. Sequence matching
            target_prev_events = [e.strip() for e in (cond.pattern_expression or "").split(",") if e.strip()]
            if target_prev_events:
                recent_events = self._store.get_recent_events(session_id, window, now)
                last_found_time = 0
                for target in target_prev_events:
                    found = False
                    for re in recent_events:
                        if re["event_type"] == target and re["timestamp_ms"] >= last_found_time and re["timestamp_ms"] < now:
                            last_found_time = re["timestamp_ms"]
                            found = True
                            break
                    if not found:
                        return False
            
            # 2. Frequency matching (count)
            required_count = safe_numeric(cond.count) or 0
            if required_count > 1:
                timestamps = state.setdefault("timestamps", [])
                timestamps.append(now)
                # purge old entries outside the window
                while timestamps and now - timestamps[0] > window:
                    timestamps.pop(0)
                if len(timestamps) < required_count:
                    return False
                    
            # If neither is specified (misconfigured rule with no expression and count < 2),
            # return False so we don't accidentally fire on every single event.
            if not target_prev_events and required_count < 2:
                return False
                
            return True
            
        # unknown condition type – fail safe
        return False

    def _determine_ui_mode_and_message(self, rule: Rule, state: Dict[str, Any]) -> tuple[str, str, bool]:
        """Determine Notification UI mode, message, and acknowledgement requirement."""
        count = state["occurrence_count"] + 1  # including this current firing
        
        # Default generic message based on rule event_type
        base_msgs = {
            "TAB_SWITCHED": "Your assessment tab became inactive. Please remain on the assessment screen.",
            "MULTIPLE_PEOPLE": "Multiple people detected in the frame.",
            "MULTIPLE_FACES": "Multiple faces detected in the frame.",
            "NO_FACE": "Please remain visible in the camera frame.",
            "GAZE_AWAY": "Please keep your eyes on the screen.",
            "MOBILE_PHONE": "Mobile phone usage detected.",
            "FACE_COVERED": "Your face appears to be partially covered.",
            "AUDIO_VAD": "Multiple voices or sustained background noise detected.",
            "NOISE": "Background noise detected.",
            "MULTIPLE_MONITORS": "Multiple monitors detected.",
            "CAMERA_DISABLED": "Webcam has been muted or disabled at the OS/hardware level.",
            "MIC_DISABLED": "Microphone has been muted or disabled at the OS/hardware level.",
            "FULLSCREEN_EXITED": "You exited fullscreen mode. Please remain in fullscreen mode during the test."
        }
        msg = base_msgs.get(rule.event_type, f"{rule.event_type} detected.")
        
        if rule.severity == "CRITICAL":
            ui_mode = "critical_modal"
            req_ack = True
            msg = "Critical assessment violation detected. " + msg
        elif count <= 1:
            ui_mode = "toast"
            req_ack = False
            # Elevate specific critical rules immediately to banner
            if rule.event_type in ["MOBILE_PHONE", "MULTIPLE_PEOPLE", "TAB_SWITCHED", "CAMERA_DISABLED", "MIC_DISABLED", "FULLSCREEN_EXITED"]:
                ui_mode = "warning_banner"
        elif count <= 3:
            ui_mode = "warning_banner"
            req_ack = False
            msg = "Warning: " + msg
        elif count <= 5:
            ui_mode = "serious_modal"
            req_ack = True
            msg = "Multiple assessment interruptions detected. Continued interruptions may require recruiter review. " + msg
        else:
            ui_mode = "critical_modal"
            req_ack = True
            msg = "Assessment integrity concerns have been recorded for recruiter review. " + msg
            
        return ui_mode, msg, req_ack

    # ---------- Scoring ----------
    def _calculate_penalty(self, rule: Rule, state: Dict[str, Any]) -> float:
        base = rule.penalty_points
        repeat = state["occurrence_count"]  # number of previous firings
        multiplier = min(1 + repeat * 0.25, 2.5)
        return base * multiplier

    # ---------- Utility ----------
    def reset_session(self, session_id: str) -> None:
        """Clear all stored state for a session – useful for tests."""
        self._store.reset(session_id)

    def get_current_score(self, session_id: str) -> float:
        return self._store.get_score(session_id)


@frappe.whitelist(allow_guest=True)
def get_trust_score(session_name: str):
    """Return trust score for a session using RuleEngine."""
    if not session_name:
        raise frappe.exceptions.ValidationError(frappe._("Session name is required"))
    engine = RuleEngine()
    try:
        engine.load_rules()
    except Exception:
        pass
    try:
        trust_score = engine.get_current_score(session_name)
        return {"session_id": session_name, "trust_score": trust_score}
    except Exception as exc:
        frappe.log_error(message=str(exc), title="Failed to get trust score")
        raise frappe.exceptions.ValidationError(frappe._("Unable to retrieve trust score"))


# End of rule_engine.py
