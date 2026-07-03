# evaluate_event.md

## Overview
`evaluate_event.py` provides the public endpoint that the machine‑learning server calls to evaluate a detection event. It validates the incoming payload, creates a Proctor Session if needed, runs the rule engine, stores the event, updates session metrics, and returns a detailed JSON response.

## Key Functions

| Function | Purpose |
|---|---|
| `_get_or_create_session(session_id: str \| None = None)` | Ensures a valid **Proctor Session** exists. Raises a `ValidationError` if the session ID is missing or does not correspond to an existing session.
| `evaluate_event(**kwargs)` | Main whitelisted endpoint (`allow_guest=True`). Parses request parameters, flattens nested payloads, runs the rule engine, records violations, stores the event via `create_event`, syncs session metrics, and returns a response containing success status, session ID, violations, engine score, risk band, and the stored event record.

## Request Payload
The endpoint expects the following fields (additional fields are ignored unless they match known keys):

- **session** *(str, required)* – Proctor Session identifier.
- **event_type** *(str, required)* – Type of detection (e.g., `MULTIPLE_PEOPLE`).
- **confidence_score** *(float, optional, default = 1.0)* – Model confidence.
- **value** *(int/float, optional)* – Numeric value for threshold rules.
- **duration_ms** *(int, optional)* – Accumulated duration for duration‑based rules.
- **metadata** *(dict | str, optional)* – Arbitrary extra data; stored as JSON.

The function also extracts a nested `payload` key if present and merges its contents into the top‑level payload.

## Processing Flow
1. **Validate & Parse** – Convert `kwargs` into a `frappe._dict`, drop the internal `cmd` argument, and deserialize any JSON strings.
2. **Session Retrieval** – Call `_get_or_create_session` to confirm the session exists.
3. **Event Construction** – Build a minimal event dict with optional fields (`value`, `duration_ms`, `confidence_score`).
4. **Rule Engine Execution** – Load cached rules via `RuleEngine`, process the event, and collect any `violations`.
5. **Metadata Handling** – Merge incoming metadata with a newly created `meta_dict`. If violations occur, add a `violations` list to the metadata.
6. **Penalty & Severity** – Compute total penalty points and the highest severity among violations, storing them in the payload.
7. **Event Persistence** – Forward the enriched payload to `create_event` (the same path used by manual event creation).
8. **Session Metrics Sync** – Call `sync_session_metrics` to update trust scores, risk band, and other aggregates on the `Proctor Session` document.
9. **Response Construction** – Return a JSON structure containing:
   - `success` – always `True` on the happy path.
   - `session` – the validated session ID.
   - `violations` – list of violation dictionaries.
   - `engine_score` – current risk score from the rule engine.
   - `risk_band` – textual risk band (e.g., `LOW`, `MEDIUM`, `HIGH`).
   - `event_record` – the result of `create_event` (the newly inserted child row).

## Security Considerations
- **Input Validation** – The function validates required fields and raises explicit `frappe.exceptions.ValidationError` for missing or malformed data.
- **JSON Deserialization** – All JSON parsing is wrapped in `try/except` blocks; malformed strings fall back to a safe representation (`{"raw_metadata": …}`) to avoid crashes.
- **Role‑Based Access** – The endpoint is currently `allow_guest=True`. In production, consider restricting it to authenticated internal services and adding role checks.
- **Metadata Sanitisation** – Metadata is stored as a JSON string after merging; ensure any downstream consumers handle it safely to prevent injection attacks.
- **Error Logging** – Errors during payload parsing or session sync are logged via `frappe.log_error` for auditability.

---
*Generated automatically for documentation purposes.*
