"""severity_engine.py — Violation → Risk score layer.

Consumes :func:`fire_violation` outputs from :mod:`threshold_engine` and
maintains an additive severity-anchor model per session.

Design invariants
-----------------
1. ``severity_anchor`` is monotonically non-decreasing within a session —
   it never decays with time.
2. Only the *live escalation state* (proctor UI display) uses ``last_event_ms``
   to soften urgency presentation — it never modifies ``risk_value``.
3. ``risk_value`` = ``severity_anchor`` + ``repeat_bonus`` + ``correlation_bonus``
   capped at 100.

Redis key namespace (non-colliding with legacy ``proctor:`` prefix):
    session:{id}:severity:anchor            float
    session:{id}:severity:anchor_rule       str (rule_id)
    session:{id}:severity:events            list[dict]  (append-only event log)
    session:{id}:severity:rule_counts       dict (rule_id -> int)
    session:{id}:severity:correlated_pairs  list[str]  (sorted(pair) joined)
    session:{id}:severity:last_event_ms     int
"""

import threading
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import frappe

if TYPE_CHECKING:
    from ai_apps.api.proctor_api.rule_engine import Rule

_lock = threading.RLock()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Anchor values for each severity tier.
SEVERITY_ANCHOR_VALUE: Dict[str, float] = {
    "Low": 20.0,
    "Medium": 45.0,
    "High": 70.0,
    "Critical": 95.0,
}

#: ``confidence_weight`` thresholds — shared with threshold_engine to stay DRY.
_CONFIDENCE_THRESHOLDS = [
    (0.85, 1.0),
    (0.60, 0.75),
    (0.40, 0.5),
]

#: Repeat bonus tier mapping.
REPEAT_BONUS_BY_TIER = {
    "CRITICAL": 50.0,
    "HIGH": 30.0,
    "MEDIUM": 20.0,
    "MODERATE": 20.0,
    "LOW": 5.0,
}

#: Rule specific total caps.
REPEAT_BONUS_CAPS = {
    "NOISE": 15.0,
    "GAZE_AWAY": 30.0,
}

#: Correlation bonus per unique pair, capped at MAX_CORRELATION_BONUS.
CORRELATION_BONUS_PER_PAIR = 8.0
MAX_CORRELATION_BONUS = 20.0

#: Default correlation window (ms) — rules may override via correlation_window_ms.
DEFAULT_CORRELATION_WINDOW_MS = 30_000


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

def _skey(session_id: str, suffix: str) -> str:
    return f"session:{session_id}:severity:{suffix}"


def _get(session_id: str, suffix: str, default=None):
    val = frappe.cache().get_value(_skey(session_id, suffix), expires=True)
    return val if val is not None else default


def _set(session_id: str, suffix: str, value) -> None:
    frappe.cache().set_value(_skey(session_id, suffix), value, expires_in_sec=86400)


# ---------------------------------------------------------------------------
# Confidence weighting
# ---------------------------------------------------------------------------

def confidence_weight(confidence: float) -> float:
    """Map a confidence score to a weight multiplier.

    Returns
    -------
    float
        1.0 for high confidence, 0.75 for medium, 0.5 for marginal,
        0.0 for signals below the minimum threshold (discarded).
    """
    for threshold, weight in _CONFIDENCE_THRESHOLDS:
        if confidence >= threshold:
            return weight
    return 0.0  # below minimum — discard


# ---------------------------------------------------------------------------
# Effective severity
# ---------------------------------------------------------------------------

def effective_severity(tier: str, confidence: float) -> Optional[float]:
    """Compute the effective severity value for a given tier and confidence.

    Returns ``None`` if the confidence weight is 0 (signal should be discarded).
    """
    weight = confidence_weight(confidence)
    if weight == 0.0:
        return None
    anchor_value = SEVERITY_ANCHOR_VALUE.get(tier)
    if anchor_value is None:
        # frappe.logger().warning(
        #     f"[severity_engine] Unknown severity_tier={tier!r}; skipping"
        # )
        return None
    return anchor_value * weight


# ---------------------------------------------------------------------------
# Anchor management
# ---------------------------------------------------------------------------

def update_severity_anchor(
    session_id: str,
    rule: "Rule",
    confidence: float,
    timestamp_ms: int,
) -> Optional[float]:
    """Process a violation and update the session's severity anchor if warranted.

    Parameters
    ----------
    session_id:
        Proctor session identifier.
    rule:
        The rule that fired the violation.
    confidence:
        The resolved confidence value (from confidence_map).
    timestamp_ms:
        Event timestamp in milliseconds.

    Returns
    -------
    Optional[float]
        The new effective severity if the anchor was updated, else ``None``
        (including when the signal was discarded).
    """
    tier = rule.severity_tier
    if not tier or tier in ("", "Select an option"):
        if rule.severity:
            tier = rule.severity.title()
        else:
            # frappe.logger().debug(
            #     f"[severity_engine] Rule {rule.rule_id} has no severity_tier or severity; skipping anchor update"
            # )
            return None

    eff = effective_severity(tier, confidence)
    if eff is None:
        _log_discarded_event(session_id, rule.rule_id, confidence)
        return None

    with _lock:
        _append_event(session_id, rule.rule_id, eff, confidence, timestamp_ms)
        _set(session_id, "last_event_ms", timestamp_ms)

        current_anchor = float(_get(session_id, "anchor", 0.0))
        if eff > current_anchor:
            _set(session_id, "anchor", eff)
            _set(session_id, "anchor_rule", rule.rule_id)
            # frappe.logger().info(
            #     f"[severity_engine] {session_id} anchor raised: {current_anchor:.1f} → {eff:.1f} "
            #     f"(rule={rule.rule_id}, tier={rule.severity_tier}, conf={confidence:.2f})"
            # )

    return eff


# ---------------------------------------------------------------------------
# Repeat bonus
# ---------------------------------------------------------------------------

def compute_repeat_bonus(session_id: str, rule: "Rule") -> None:
    """Increment the rule's penalized fire count."""
    with _lock:
        counts: Dict[str, int] = dict(_get(session_id, "penalized_rule_counts", {}))
        counts[rule.rule_id] = counts.get(rule.rule_id, 0) + 1
        _set(session_id, "penalized_rule_counts", counts)


def calculate_rule_repeat_bonus(rule_id: str, tier: str, penalized_count: int) -> float:
    """Calculates the total repeat bonus for a single rule instance."""
    repeats = max(0, penalized_count - 1)
    rate = REPEAT_BONUS_BY_TIER.get(tier.upper(), 0.0)
    uncapped_bonus = repeats * rate
    
    # Apply rule-specific cap if defined
    if rule_id in REPEAT_BONUS_CAPS:
        return min(uncapped_bonus, REPEAT_BONUS_CAPS[rule_id])
    
    return uncapped_bonus


def get_total_repeat_bonus(penalized_rule_counts: Dict[str, int], rule_tier_map: Dict[str, str]) -> float:
    """Calculates independent summation across all penalized rules."""
    total_bonus = 0.0
    for rule_id, count in penalized_rule_counts.items():
        tier = rule_tier_map.get(rule_id, "LOW")
        total_bonus += calculate_rule_repeat_bonus(rule_id, tier, count)
        
    return total_bonus


# ---------------------------------------------------------------------------
# Correlation bonus
# ---------------------------------------------------------------------------

def compute_correlation_bonus(
    session_id: str,
    rule_id: str,
    timestamp_ms: int,
    window_ms: int = DEFAULT_CORRELATION_WINDOW_MS,
) -> float:
    """Record cross-rule co-occurrence and return the cumulative correlation bonus.

    Capped at :data:`MAX_CORRELATION_BONUS`.
    """
    with _lock:
        events: List[Dict[str, Any]] = list(_get(session_id, "events", []))
        cutoff = timestamp_ms - window_ms

        # Rules active within the correlation window
        recent_rule_ids = {
            e["rule_id"] for e in events
            if e.get("timestamp_ms", 0) >= cutoff and e["rule_id"] != rule_id
        }

        # Record new pairs
        existing_pairs: List[str] = list(_get(session_id, "correlated_pairs", []))
        existing_set = set(existing_pairs)
        for other in recent_rule_ids:
            pair_key = "|".join(sorted([rule_id, other]))
            if pair_key not in existing_set:
                existing_pairs.append(pair_key)
                existing_set.add(pair_key)

        _set(session_id, "correlated_pairs", existing_pairs)
        pair_count = len(existing_pairs)

    return min(pair_count * CORRELATION_BONUS_PER_PAIR, MAX_CORRELATION_BONUS)


def get_correlation_bonus(session_id: str) -> float:
    """Return the current correlation bonus for the session."""
    pairs = list(_get(session_id, "correlated_pairs", []))
    return min(len(pairs) * CORRELATION_BONUS_PER_PAIR, MAX_CORRELATION_BONUS)


# ---------------------------------------------------------------------------
# Redis Rehydration
# ---------------------------------------------------------------------------

def rehydrate_severity_state(session_id: str) -> None:
    """Reconstruct the Redis severity state for a session from its DB events.

    Useful if Redis key expired or cleared but the session is requested or synchronized.
    """
    import json
    # 1. Clear current Redis state to start clean and prevent recursion loops by initializing events key
    reset_session(session_id)
    _set(session_id, "events", [])

    # 2. Retrieve all Proctor Session Events from the DB
    parent_name = frappe.db.get_value("Proctor Event", {"session": session_id}, "name")
    if not parent_name:
        return

    db_events = frappe.get_all(
        "Proctor Session Event",
        filters={"parent": parent_name},
        fields=["event_type", "occurred_at", "creation", "metadata"],
        order_by="occurred_at asc, creation asc",
    )

    # 3. Load the rule list from the engine
    from ai_apps.api.proctor_api.rule_engine import RuleEngine
    engine = RuleEngine()
    engine.load_rules()

    # 4. Process each event through the severity pipeline
    for ev in db_events:
        event_type = ev.get("event_type")
        if event_type in ("SESSION_START", "SESSION_END"):
            continue

        # Find the matching rule
        matching_rule = None
        for rule in engine._rules:
            if rule.event_type == event_type or rule.rule_id == event_type:
                matching_rule = rule
                break

        if not matching_rule:
            continue

        # Determine timestamp and confidence
        import datetime
        dt = ev.get("occurred_at") or ev.get("creation")
        if isinstance(dt, datetime.datetime):
            ts_ms = int(dt.timestamp() * 1000)
        elif dt:
            try:
                from frappe.utils import get_datetime
                ts_ms = int(get_datetime(dt).timestamp() * 1000)
            except Exception:
                ts_ms = int(time.time() * 1000)
        else:
            ts_ms = int(time.time() * 1000)

        # Parse confidence and duration from metadata if present
        confidence = 1.0
        dur_ms = 0
        meta_str = ev.get("metadata")
        if meta_str:
            try:
                meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
                confidence = float(meta.get("confidence") or meta.get("confidence_score") or 1.0)
                dur_ms = int(meta.get("duration_ms") or 0)
            except Exception:
                pass

        # Call process_violation
        process_violation(session_id, matching_rule, confidence, ts_ms, duration_ms=dur_ms)


# ---------------------------------------------------------------------------
# Risk value computation
# ---------------------------------------------------------------------------

def compute_risk_value(session_id: str) -> Dict[str, Any]:
    """Compute the full risk score payload for a session.

    Returns
    -------
    dict
        Keys: ``risk_value``, ``risk_band``, ``severity_anchor``,
        ``anchor_rule``, ``repeat_bonus``, ``correlation_bonus``,
        ``contributing_events``.
    """
    with _lock:
        if _get(session_id, "events") is None:
            # Redis cache expired/missing — check if there are database events to rehydrate
            parent_name = frappe.db.get_value("Proctor Event", {"session": session_id}, "name")
            if parent_name:
                has_db_events = frappe.db.exists("Proctor Session Event", {"parent": parent_name})
                if has_db_events:
                    rehydrate_severity_state(session_id)

        anchor = float(_get(session_id, "anchor", 0.0))
        anchor_rule = _get(session_id, "anchor_rule", "")
        corr_bonus = get_correlation_bonus(session_id)
        events = list(_get(session_id, "events", []))
        penalized_counts = dict(_get(session_id, "penalized_rule_counts", {}))

    from ai_apps.api.proctor_api.rule_engine import RuleEngine
    engine = RuleEngine()
    engine.load_rules()
    rule_tier_map = {
        r.rule_id: (r.severity_tier or r.severity or "LOW").upper()
        for r in engine._rules
    }
    
    rep_bonus = get_total_repeat_bonus(penalized_counts, rule_tier_map)

    risk = min(anchor + rep_bonus + corr_bonus, 100.0)

    return {
        "risk_value": round(risk, 2),
        "risk_band": risk_band(risk),
        "severity_anchor": round(anchor, 2),
        "anchor_rule": anchor_rule,
        "repeat_bonus": round(rep_bonus, 2),
        "correlation_bonus": round(corr_bonus, 2),
        "contributing_events": events,
    }


def risk_band(value: float) -> str:
    """Map a risk value to its named band."""
    if value <= 20:
        return "LOW"
    if value <= 45:
        return "MEDIUM"
    if value <= 70:
        return "HIGH"
    return "CRITICAL"


# ---------------------------------------------------------------------------
# Live escalation state (display only — never affects risk_value)
# ---------------------------------------------------------------------------

def get_escalation_state(session_id: str) -> str:
    """Return a live escalation state for the proctor UI.

    Uses the current ``risk_band`` as the baseline, optionally softened
    if the last event was long ago (display only — does NOT modify risk_value).
    """
    payload = compute_risk_value(session_id)
    band = payload["risk_band"]
    # Map band directly to escalation state
    return {
        "LOW": "NORMAL",
        "MEDIUM": "WATCHING",
        "HIGH": "WARNING",
        "CRITICAL": "CRITICAL_REVIEW",
    }.get(band, "NORMAL")


# ---------------------------------------------------------------------------
# Full pipeline convenience function
# ---------------------------------------------------------------------------

def process_violation(
    session_id: str,
    rule: "Rule",
    confidence: float,
    timestamp_ms: int,
    duration_ms: int = 0,
) -> Dict[str, Any]:
    """Update anchor, repeat bonus, and correlation bonus for a single violation.

    This is the single call :mod:`threshold_engine`'s ``on_violation`` callback
    should make into the severity engine.

    Returns
    -------
    dict
        Full risk payload from :func:`compute_risk_value`.
    """
    with _lock:
        counts = dict(_get(session_id, "rule_counts", {}))
        is_first = (counts.get(rule.rule_id, 0) == 0)

    apply_penalty = True
    if is_first:
        if rule.rule_id in ("NOISE", "GAZE_AWAY"):
            apply_penalty = False
            frappe.logger().info(f"[severity_engine] First {rule.rule_id} for session {session_id} - applying NO penalty.")
        elif rule.rule_id in ("TAB_SWITCHED", "FULLSCREEN_EXITED", "FULLSCREEN_EXIT"):
            if duration_ms <= 3000:
                apply_penalty = False
                frappe.logger().info(f"[severity_engine] First {rule.rule_id} for session {session_id} (duration {duration_ms}ms <= 3000ms) - applying NO penalty.")

    if apply_penalty:
        # 1. Update anchor
        update_severity_anchor(session_id, rule, confidence, timestamp_ms)

        # 2. Repeat bonus (increments internal penalized count)
        compute_repeat_bonus(session_id, rule)

        # 3. Correlation bonus
        corr_window = rule.correlation_window_ms or DEFAULT_CORRELATION_WINDOW_MS
        compute_correlation_bonus(session_id, rule.rule_id, timestamp_ms, window_ms=corr_window)
    else:
        # Manually increment count so next occurrence applies penalty
        with _lock:
            counts[rule.rule_id] = counts.get(rule.rule_id, 0) + 1
            _set(session_id, "rule_counts", counts)
            _append_event(session_id, rule.rule_id, 0.0, confidence, timestamp_ms)
            _set(session_id, "last_event_ms", timestamp_ms)

    # 4. Return full payload
    payload = compute_risk_value(session_id)
    payload["apply_penalty"] = apply_penalty
    return payload

# ---------------------------------------------------------------------------
# Session reset
# ---------------------------------------------------------------------------

def reset_session(session_id: str) -> None:
    """Clear all severity engine state for a session."""
    for suffix in ("anchor", "anchor_rule", "events", "rule_counts", "penalized_rule_counts", "correlated_pairs", "last_event_ms"):
        frappe.cache().delete_key(_skey(session_id, suffix))


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _append_event(
    session_id: str,
    rule_id: str,
    effective_sev: float,
    confidence: float,
    timestamp_ms: int,
) -> None:
    events: List[Dict[str, Any]] = list(_get(session_id, "events", []))
    events.append({
        "rule_id": rule_id,
        "effective_severity": round(effective_sev, 2),
        "confidence": round(confidence, 3),
        "timestamp_ms": timestamp_ms,
    })
    _set(session_id, "events", events)


def _log_discarded_event(session_id: str, rule_id: str, confidence: float) -> None:
    pass
    # frappe.logger().debug(
    #     f"[severity_engine] {session_id}/{rule_id} discarded — "
    #     f"confidence {confidence:.2f} below minimum weight threshold"
    # )
