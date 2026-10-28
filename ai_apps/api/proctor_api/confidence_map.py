"""confidence_map.py — Per-rule confidence resolution layer.

Maps raw ML context to a normalised confidence value (0.0–1.0) for each rule.

Rules that are already confirmed by ML-side frame smoothing (e.g. multipleFaces
smoothed over 4/5 frames) pass through at full confidence 1.0.  Rules whose
output is a direct ML score (e.g. YOLO confidence for phoneDetected) use that
score directly.

The ``resolve_confidence`` function is called by :mod:`threshold_engine` before
gating and by :mod:`severity_engine` when computing effective severity.

Context dict shape (``ctx``) is rule-dependent; keys are listed per rule below.
All callers that don't have a full context dict should pass ``{}``  — the
lambdas handle missing keys safely via ``dict.get`` with defaults.

SCREAMING_SNAKE naming is used for rule IDs to match the existing ``DEFAULT_RULES``
and ``Proctor Rule`` DocType names.  The mapping is explicit so new rules must be
registered here.
"""

from typing import Any, Dict

# ---------------------------------------------------------------------------
# Per-rule confidence resolvers
# ---------------------------------------------------------------------------

_CONFIDENCE_SOURCE: Dict[str, Any] = {
    # Deterministic browser events — always 1.0
    "TAB_SWITCHED":     lambda ctx: 1.0,
    "FULLSCREEN_EXIT":  lambda ctx: 1.0,
    "FULLSCREEN_EXITED": lambda ctx: 1.0,  # alias used in some rule names
    "NO_VIDEO":         lambda ctx: 1.0,
    "NO_AUDIO":         lambda ctx: 1.0,
    "MULTIPLE_MONITORS": lambda ctx: 1.0,
    "CAMERA_DISABLED":  lambda ctx: 1.0,
    "MIC_DISABLED":     lambda ctx: 1.0,

    # ML rules confirmed by frame smoothing on the ML side — treat as 1.0
    # (multipleFaces: 4/5 frames, multiplePeople: 3/5 frames by the time
    #  the signal reaches the backend, so it's already a filtered verdict)
    "MULTIPLE_FACES":   lambda ctx: 1.0,
    "MULTIPLE_PEOPLE":  lambda ctx: 1.0,
    "NO_FACE":          lambda ctx: 1.0,

    # ML rules that carry a real model confidence score
    "MOBILE_PHONE":     lambda ctx: float(ctx.get("yolo_confidence", ctx.get("confidence_score", 1.0))),
    "FACE_COVERED":     lambda ctx: float(ctx.get("face_detection_score", ctx.get("confidence_score", 1.0))),

    # lookingAway — EMA angle relative to threshold
    # ctx must contain: ema_angle (float), threshold (float)
    # Normalise to [0, 1] — capped at 1.0
    "GAZE_AWAY":        lambda ctx: min(
        (float(ctx.get("ema_angle", 0)) - float(ctx.get("threshold", 1))) /
        max(float(ctx.get("threshold", 1)), 1e-6),
        1.0,
    ) if ctx.get("ema_angle") is not None and ctx.get("threshold") else float(ctx.get("confidence_score", 1.0)),

    # multi-speaker VAD — use vad_confidence if present, else 1.0
    "AUDIO_VAD":        lambda ctx: float(ctx.get("vad_confidence", ctx.get("confidence_score", 1.0))),

    # NOISE — treat as confirmed if reached (already filtered upstream)
    "NOISE":            lambda ctx: 1.0,
}

# Default resolver for any rule not explicitly registered
_DEFAULT_RESOLVER = lambda ctx: float(ctx.get("confidence_score", 1.0))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_confidence(rule_id: str, raw_confidence: float, ctx: Dict[str, Any] = None) -> float:
    """Return a normalised confidence value for a given rule and context.

    Parameters
    ----------
    rule_id:
        The rule identifier (matches DocType rule_name/rule_id, SCREAMING_SNAKE).
    raw_confidence:
        The raw confidence value passed in the ML event (0.0–1.0).  Used as
        the ``confidence_score`` fallback for rules that read it from ``ctx``.
    ctx:
        Optional extra context dict.  If ``None``, an empty dict is used.
        Keys are rule-dependent (see module docstring).

    Returns
    -------
    float
        Resolved confidence clamped to [0.0, 1.0].
    """
    if ctx is None:
        ctx = {}
    # Inject raw_confidence as the generic fallback key so individual lambdas
    # can read it without the caller having to set it explicitly.
    ctx.setdefault("confidence_score", raw_confidence)

    resolver = _CONFIDENCE_SOURCE.get(rule_id, _DEFAULT_RESOLVER)
    try:
        result = resolver(ctx)
        # Clamp to [0.0, 1.0]
        return max(0.0, min(float(result), 1.0))
    except Exception:
        import frappe
        frappe.logger().warning(
            f"[confidence_map] Failed to resolve confidence for rule {rule_id}; "
            f"falling back to raw_confidence={raw_confidence}"
        )
        return max(0.0, min(float(raw_confidence), 1.0))


def register_resolver(rule_id: str, resolver) -> None:
    """Register a custom confidence resolver for a rule at runtime.

    Useful for tests and for new rules added without redeploying this module.

    Parameters
    ----------
    rule_id:
        Rule identifier (SCREAMING_SNAKE).
    resolver:
        Callable ``(ctx: dict) -> float``.
    """
    _CONFIDENCE_SOURCE[rule_id] = resolver
