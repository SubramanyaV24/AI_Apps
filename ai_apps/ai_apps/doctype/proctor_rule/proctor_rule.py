# Copyright (c) 2026, Varun CA and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ProctorRule(Document):
    """Frappe controller for the Proctor Rule DocType.

    Enforces required-field constraints for the new severity engine schema so
    that misconfigured rules (e.g. a Duration rule with no ``duration_ms``)
    raise a clear validation error at save time rather than silently misfiring
    at evaluation time.
    """

    def validate(self):
        self._validate_threshold_type_fields()
        self._validate_severity_tier()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_threshold_type_fields(self):
        threshold_type = self.threshold_type or ""

        if threshold_type == "Duration":
            if not self.duration_ms:
                frappe.throw(
                    _("Duration Threshold (ms) is required when Threshold Type is 'Duration'."),
                    title=_("Missing field: duration_ms"),
                )

        elif threshold_type == "Frequency":
            missing = []
            if not self.frequency_count:
                missing.append("Frequency Count")
            if not self.frequency_window_ms:
                missing.append("Frequency Window (ms)")
            if missing:
                frappe.throw(
                    _("{0} {1} required when Threshold Type is 'Frequency'.").format(
                        " and ".join(missing),
                        _("is") if len(missing) == 1 else _("are"),
                    ),
                    title=_("Missing frequency fields"),
                )

    def _validate_severity_tier(self):
        """Warn (not block) if severity_tier is unset while threshold_type is
        set — the rule is partially configured for the new engine."""
        if self.threshold_type and self.threshold_type not in ("", "Select an option"):
            if not self.severity_tier or self.severity_tier == "Select an option":
                frappe.msgprint(
                    _("Severity Tier is not set on rule '{0}'. The severity engine will skip "
                      "this rule until a tier is assigned.").format(self.rule_name or self.name),
                    title=_("Incomplete severity engine configuration"),
                    indicator="orange",
                )
