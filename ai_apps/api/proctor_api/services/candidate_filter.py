"""Candidate filtering service for the Proctor API.

This module exposes whitelisted Frappe endpoints:

    ai_apps.api.proctor_api.services.candidate_filter.get_total_candidates
    ai_apps.api.proctor_api.services.candidate_filter.filter_sessions

It queries the **Proctor Session** doctype (and optionally joins event
violation counts from **Proctor Event** / **Proctor Session Event**) and
returns a paginated, filtered list of candidate sessions.

Supported filters
-----------------
* ``query``        – free-text match on user_name or user_email (LIKE)
* ``risk_levels``  – JSON array, e.g. ``["HIGH","MEDIUM"]``
  Maps to the ``risk_level`` field on Proctor Session.
* ``trust_min``    – minimum trust score (inclusive, default 0)
* ``trust_max``    – maximum trust score (inclusive, default 100)
* ``status``       – single status string or JSON array, e.g. ``"ENDED"``
* ``page``         – 1-based page number (default 1)
* ``limit``        – records per page, capped at 100 (default 25)

Security notes
--------------
* All string inputs are validated/sanitised before being passed to
  ``frappe.get_all``; no raw SQL interpolation is performed.
* Pagination bounds are enforced server-side.
* The endpoint is ``allow_guest=True`` to match the rest of the proctor API;
  tighten to ``allow_guest=False`` if authentication should be required.
"""

from __future__ import annotations

import json
from typing import List

import frappe
from frappe import _


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_RISK_LEVELS = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
VALID_STATUSES = {"STARTED", "IN_PROGRESS", "ENDED", "FAILED", "SUBMITTED"}
_MAX_LIMIT = 100
_DEFAULT_LIMIT = 25


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_list(value: str | list | None, valid_values: set) -> List[str]:
    """Parse a JSON string or list and filter to only valid enum members."""
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    else:
        try:
            raw = json.loads(value)
        except (ValueError, TypeError):
            raw = [value]  # treat bare string as single-element list
    return [str(v).upper() for v in raw if str(v).upper() in valid_values]


def _clamp_int(value, min_val: int, max_val: int, default: int) -> int:
    try:
        return max(min_val, min(int(value), max_val))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Main whitelisted endpoints
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def get_total_candidates():
    """Return the total number of analyzed candidates (Proctor Session records).

    This count is independent of search/filter state on the dashboard sidebar.

    Returns
    -------
    dict
        ``{success, total_candidates}``
    """
    try:
        total = frappe.db.count("Proctor Session")
        return {
            "success": True,
            "total_candidates": total,
        }
    except Exception:
        frappe.log_error(
            title="candidate_filter.get_total_candidates error",
            message=frappe.get_traceback(),
        )
        frappe.throw(_("Failed to fetch total candidates. Please try again."))


@frappe.whitelist(allow_guest=True)
def filter_sessions(
    query: str = "",
    risk_levels: str = "[]",
    trust_min: int = 0,
    trust_max: int = 100,
    status: str = "[]",
    page: int = 1,
    limit: int = _DEFAULT_LIMIT,
):
    """Return a filtered, paginated list of Proctor Session records.

    All parameters arrive as strings from the HTTP layer; this function
    coerces and validates them before touching the database.

    Returns
    -------
    dict
        ``{success, sessions, page, limit, total, total_pages}``
    """
    # --- Sanitise inputs ---------------------------------------------------
    page  = _clamp_int(page,  1, 10_000, 1)
    limit = _clamp_int(limit, 1, _MAX_LIMIT, _DEFAULT_LIMIT)
    trust_min = _clamp_int(trust_min, 0, 100, 0)
    trust_max = _clamp_int(trust_max, 0, 100, 100)
    if trust_min > trust_max:
        trust_min, trust_max = trust_max, trust_min

    risk_level_list = _parse_json_list(risk_levels, VALID_RISK_LEVELS)
    status_list     = _parse_json_list(status,      VALID_STATUSES)

    # Strip and limit free-text query to prevent abuse
    query = (query or "").strip()[:200]

    # --- Build Frappe filter list ------------------------------------------
    filters: list = []

    if risk_level_list:
        filters.append(["risk_level", "in", risk_level_list])

    if status_list:
        filters.append(["status", "in", status_list])

    # Trust score range
    if trust_min > 0:
        filters.append(["trust_score", ">=", trust_min])
    if trust_max < 100:
        filters.append(["trust_score", "<=", trust_max])

    # Free-text: OR across user_name and user_email using Frappe OR filters
    # We apply this as a post-filter below if frappe.get_all doesn't support
    # OR filters easily in all versions.
    text_filters = []
    if query:
        text_filters = [
            ["user_name",  "like", f"%{query}%"],
            ["user_email", "like", f"%{query}%"],
        ]

    # --- Fetch records -------------------------------------------------------
    fields = [
        "name",
        "user_name",
        "user_email",
        "user_id",
        "entity_id",
        "status",
        "trust_score",
        "risk_level",
        "total_events",
        "critical_events",
        "review_required",
        "creation",
        "modified",
    ]

    try:
        if text_filters:
            # Frappe supports OR filters via a list of filter lists when you
            # pass them as the top-level ``filters`` param combined with
            # ``or_filters``.
            name_records = frappe.get_all(
                "Proctor Session",
                filters=filters + [["user_name", "like", f"%{query}%"]],
                fields=fields,
                order_by="creation desc",
                limit_page_length=_MAX_LIMIT * 10,  # fetch enough to de-dup
            )
            email_records = frappe.get_all(
                "Proctor Session",
                filters=filters + [["user_email", "like", f"%{query}%"]],
                fields=fields,
                order_by="creation desc",
                limit_page_length=_MAX_LIMIT * 10,
            )
            # Merge and de-duplicate preserving order
            seen = set()
            merged = []
            for r in name_records + email_records:
                if r["name"] not in seen:
                    seen.add(r["name"])
                    merged.append(r)
            # Sort by creation desc
            merged.sort(key=lambda r: r.get("creation") or "", reverse=True)
            total = len(merged)
            offset = (page - 1) * limit
            records = merged[offset: offset + limit]
        else:
            total = frappe.db.count("Proctor Session", filters)
            offset = (page - 1) * limit
            records = frappe.get_all(
                "Proctor Session",
                filters=filters,
                fields=fields,
                order_by="creation desc",
                limit_page_length=limit,
                limit_start=offset,
            )

        # Enrich each record with a quick violation count from Proctor Event
        # (lightweight: one extra query per page, not per record)
        session_names = [r["name"] for r in records]
        if session_names:
            _attach_event_counts(records, session_names)

        return {
            "success": True,
            "sessions": records,
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": max(1, (total + limit - 1) // limit),
        }

    except Exception:
        frappe.log_error(
            title="candidate_filter.filter_sessions error",
            message=frappe.get_traceback(),
        )
        frappe.throw(_("Failed to filter sessions. Please try again."))


# ---------------------------------------------------------------------------
# Enrichment helper
# ---------------------------------------------------------------------------

def _attach_event_counts(records: list, session_names: list) -> None:
    """Attach ``violation_count`` to each record using a single DB query.

    Looks up the Proctor Event parent for each session, then counts child
    Proctor Session Event rows (excluding SESSION_START / SESSION_END).
    """
    try:
        # Map session name → proctor_event parent name
        event_parents = frappe.get_all(
            "Proctor Event",
            filters=[["session", "in", session_names]],
            fields=["name", "session"],
        )
        session_to_parent = {ep["session"]: ep["name"] for ep in event_parents}
        parent_names = list(session_to_parent.values())

        if not parent_names:
            for r in records:
                r.setdefault("violation_count", 0)
            return

        # Count events per parent (exclude lifecycle markers)
        event_rows = frappe.get_all(
            "Proctor Session Event",
            filters=[
                ["parent", "in", parent_names],
                ["event_type", "not in", ["SESSION_START", "SESSION_END"]],
            ],
            fields=["parent"],
        )
        counts: dict[str, int] = {}
        for row in event_rows:
            counts[row["parent"]] = counts.get(row["parent"], 0) + 1

        # Attach to records
        parent_to_session = {v: k for k, v in session_to_parent.items()}
        session_counts = {
            parent_to_session[parent]: count
            for parent, count in counts.items()
            if parent in parent_to_session
        }
        for r in records:
            r["violation_count"] = session_counts.get(r["name"], 0)

    except Exception:
        # Non-critical enrichment — log but don't fail the main response
        frappe.log_error(
            title="candidate_filter._attach_event_counts error",
            message=frappe.get_traceback(),
        )
        for r in records:
            r.setdefault("violation_count", 0)
