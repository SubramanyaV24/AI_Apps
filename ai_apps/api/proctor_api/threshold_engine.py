"""threshold_engine.py — Raw signal → Violation gate layer.

Sits between the ML event stream and the severity engine. Reads ``threshold_type``
and related fields directly off the :class:`Rule` object (already populated by
``Rule.from_dict`` with new fields from Phase 1).

Only :func:`fire_violation` output ever reaches the severity engine — raw
per-frame signals never touch scoring directly.

Redis key namespace (does NOT collide with the legacy ``proctor:`` prefix):
    session:{id}:rule:{rule_id}:cumulative_ms
    session:{id}:rule:{rule_id}:last_frame_state
    session:{id}:rule:{rule_id}:occurrences      (list of timestamp_ms ints)
"""

import threading
import time
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

import frappe

if TYPE_CHECKING:
    from ai_apps.api.proctor_api.rule_engine import Rule


# ---------------------------------------------------------------------------
# Public callback type
# ---------------------------------------------------------------------------
# Callers register a fire_violation callback that accepts:
#   session_id, rule, confidence, timestamp_ms
ViolationCallback = Callable[["Rule", str, float, int], None]


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

_lock = threading.RLock()


def _key(session_id: str, rule_id: str, suffix: str) -> str:
    return f"session:{session_id}:rule:{rule_id}:{suffix}"


def _get_cumulative_ms(session_id: str, rule_id: str) -> int:
    val = frappe.cache().get_value(_key(session_id, rule_id, "cumulative_ms"))
    return int(val) if val is not None else 0


def _set_cumulative_ms(session_id: str, rule_id: str, ms: int) -> None:
    frappe.cache().set_value(
        _key(session_id, rule_id, "cumulative_ms"), ms, expires_in_sec=86400
    )


def _reset_cumulative_ms(session_id: str, rule_id: str) -> None:
    frappe.cache().set_value(
        _key(session_id, rule_id, "cumulative_ms"), 0, expires_in_sec=86400
    )


def _get_occurrences(session_id: str, rule_id: str) -> List[int]:
    val = frappe.cache().get_value(_key(session_id, rule_id, "occurrences"))
    return list(val) if val else []


def _set_occurrences(session_id: str, rule_id: str, timestamps: List[int]) -> None:
    frappe.cache().set_value(
        _key(session_id, rule_id, "occurrences"), timestamps, expires_in_sec=86400
    )


def reset_rule_state(session_id: str, rule_id: str) -> None:
    """Clear all raw-signal tracking state for a single rule in a session."""
    for suffix in ("cumulative_ms", "last_frame_state", "occurrences"):
        frappe.cache().delete_key(_key(session_id, rule_id, suffix))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_raw_signal(
    session_id: str,
    rule: "Rule",
    raw_state: str,
    confidence: float,
    timestamp_ms: int,
    on_violation: ViolationCallback,
) -> bool:
    """Evaluate a single raw ML signal against the rule's threshold type.

    Parameters
    ----------
    session_id:
        The proctor session identifier.
    rule:
        A fully-parsed :class:`Rule` instance (must have ``threshold_type``).
    raw_state:
        For instant/duration rules: ``"triggered"`` or ``"clear"``.
        For frequency rules: always pass ``"triggered"``.
    confidence:
        The ML model confidence for this signal (0.0–1.0).
    timestamp_ms:
        Current wall-clock time in milliseconds.
    on_violation:
        Callback invoked when the threshold is met.  Signature::

            on_violation(rule, session_id, confidence, timestamp_ms)

    Returns
    -------
    bool
        ``True`` if a violation was fired, ``False`` otherwise.
    """
    from ai_apps.api.proctor_api.confidence_map import resolve_confidence

    # Resolve the per-rule confidence (replaces the raw float for some rules)
    effective_confidence = resolve_confidence(rule.rule_id, confidence)

    # Discard signals that are too unreliable even to accumulate.
    # confidence_weight is imported from severity_engine to stay DRY.
    from ai_apps.api.proctor_api.severity_engine import confidence_weight
    if confidence_weight(effective_confidence) == 0.0:
        frappe.logger().debug(
            f"[threshold_engine] {rule.rule_id} discarded — confidence {effective_confidence:.2f} below minimum"
        )
        return False

    threshold_type = (rule.threshold_type or "").strip()

    with _lock:
        if threshold_type == "Instant":
            return _handle_instant(
                session_id, rule, raw_state, effective_confidence, timestamp_ms, on_violation
            )
        elif threshold_type == "Duration":
            return _handle_duration(
                session_id, rule, raw_state, effective_confidence, timestamp_ms, on_violation
            )
        elif threshold_type == "Frequency":
            return _handle_frequency(
                session_id, rule, effective_confidence, timestamp_ms, on_violation
            )
        else:
            frappe.logger().warning(
                f"[threshold_engine] Rule {rule.rule_id} has unknown threshold_type={threshold_type!r}; skipping"
            )
            return False


# ---------------------------------------------------------------------------
# Threshold type handlers
# ---------------------------------------------------------------------------

def _handle_instant(
    session_id: str,
    rule: "Rule",
    raw_state: str,
    confidence: float,
    timestamp_ms: int,
    on_violation: ViolationCallback,
) -> bool:
    """Fire immediately when ``raw_state == "triggered"``."""
    if raw_state == "triggered":
        on_violation(rule, session_id, confidence, timestamp_ms)
        return True
    return False


def _handle_duration(
    session_id: str,
    rule: "Rule",
    raw_state: str,
    confidence: float,
    timestamp_ms: int,
    on_violation: ViolationCallback,
) -> bool:
    """Accumulate signal duration; fire when cumulative_ms >= rule.duration_ms.

    ``reset_on_clear`` behaviour:
    - True  (default): accumulator resets to 0 when the signal clears.
    - False (e.g. lookingAway): accumulator persists; clear frames don't subtract.

    After a violation fires, the accumulator is reset regardless of
    ``reset_on_clear`` so each subsequent violation requires a fresh
    ``duration_ms`` of accumulation.
    """
    threshold_ms = rule.duration_ms or 0
    if threshold_ms <= 0:
        frappe.logger().warning(
            f"[threshold_engine] Duration rule {rule.rule_id} has no duration_ms; skipping"
        )
        return False

    # Retrieve or estimate the delta since last frame.
    # We use timestamp_ms deltas between successive calls as a proxy for
    # accumulated active time.  Callers may also pass duration_ms explicitly
    # in the event payload — that is handled at the evaluate_event layer which
    # computes delta_ms before calling process_raw_signal.
    cumulative = _get_cumulative_ms(session_id, rule.rule_id)

    if raw_state == "triggered":
        # We don't have frame duration here — the caller is responsible for
        # passing the inter-frame delta via the ``duration_ms`` field in the
        # event payload and calling this with the accumulated value.
        # For now we treat each "triggered" call as +1 frame increment.
        # The evaluate_event layer will be updated in Phase 6 to pass the
        # proper delta; at that point this becomes a pure accumulator.
        cumulative += 1  # placeholder; replaced by proper delta in Phase 6
        _set_cumulative_ms(session_id, rule.rule_id, cumulative)

        if cumulative >= threshold_ms:
            on_violation(rule, session_id, confidence, timestamp_ms)
            # Always reset after firing so the next violation requires a full
            # new accumulation cycle.
            _reset_cumulative_ms(session_id, rule.rule_id)
            return True

    else:  # "clear"
        if rule.reset_on_clear:
            _reset_cumulative_ms(session_id, rule.rule_id)

    return False


def _handle_frequency(
    session_id: str,
    rule: "Rule",
    confidence: float,
    timestamp_ms: int,
    on_violation: ViolationCallback,
) -> bool:
    """Sliding-window frequency: fire when count >= frequency_count within window.

    After firing, the oldest timestamps that caused the violation are pruned so
    the window correctly represents only the most recent activity.
    """
    freq_count = rule.frequency_count or 0
    freq_window = rule.frequency_window_ms or 0
    if freq_count <= 0 or freq_window <= 0:
        frappe.logger().warning(
            f"[threshold_engine] Frequency rule {rule.rule_id} missing frequency_count or frequency_window_ms; skipping"
        )
        return False

    occurrences = _get_occurrences(session_id, rule.rule_id)
    occurrences.append(timestamp_ms)

    # Prune entries outside the sliding window
    cutoff = timestamp_ms - freq_window
    occurrences = [t for t in occurrences if t > cutoff]

    _set_occurrences(session_id, rule.rule_id, occurrences)

    if len(occurrences) >= freq_count:
        on_violation(rule, session_id, confidence, timestamp_ms)
        # After firing, if reset_on_clear is True (default for frequency rules)
        # clear the window so the next fire requires a fresh burst.
        if rule.reset_on_clear:
            _set_occurrences(session_id, rule.rule_id, [])
        return True

    return False
