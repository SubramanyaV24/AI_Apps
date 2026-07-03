# evidence.md

## Overview
`evidence.py` contains utilities for handling **Proctor evidence** – base‑64 encoded media (screenshots, audio, video) generated during a proctoring session. The module provides functions to decode the data, upload it securely to SharePoint, create corresponding **Proctor Evidence** documents in Frappe, and replace the original base‑64 blob with a SharePoint URL.

## Key Functions

| Function | Description |
|----------|-------------|
| **`process_evidence(doc)`** | Scans the child table `proctor_session_event` of a given Proctor Session document, looks for a `metadata` field containing an `evidence` entry, decodes the base‑64 payload, uploads the file to SharePoint, creates a `Proctor Evidence` DocType record, and updates the child row metadata to reference the SharePoint URL instead of the raw data. |
| **`decode_base64_file(data_uri)`** | Accepts either a full data‑URI (`data:<mime>;base64,<data>`) or a raw base‑64 string. Returns a tuple of `(bytes, mime_type, extension)`. It includes a mime‑type → extension map covering common image, audio, and video formats. |
| **`upload_file_to_sharepoint_raw(client, full_folder_path, filename, file_content, mime_type)`** | Performs a raw byte upload to Microsoft Graph API. It normalises the folder path, ensures the folder exists via `_ensure_folder`, and sends a `PUT` request. Returns success flag, web URL, download URL, and the file ID. |
| **`_ensure_folder(client, full_folder_path)`** | Walks the folder hierarchy, creating any missing directories in SharePoint using the Graph API `POST /children`. Handles already‑existing folders gracefully. |
| **`store_evidence(**kwargs)`** (whitelisted) | Direct API endpoint for uploading a single evidence blob. It validates required fields (`session`, `evidence`), decodes the payload, enforces a 10 MB size limit, builds a safe filename, uploads to SharePoint, and returns the URL and filename.

## Workflow Summary (used by `process_evidence`)
1. **Retrieve session ID** from the parent document; abort if missing.
2. Iterate over each child row in `doc.proctor_session_event`.
3. Parse `metadata` JSON; locate the `evidence` key.
4. Skip if the evidence is already a URL.
5. Decode the base‑64 data via `decode_base64_file`.
6. Enforce a 10 MB maximum size (DoS mitigation).
7. Generate a unique, unpredictable filename using a timestamp and an 8‑character UUID.
8. Build a SharePoint folder path based on configuration `proctor_evidence_sharepoint_path` (default `Proctor/Evidence`).
9. Upload the file with `upload_file_to_sharepoint_raw`.
10. On success, create a `Proctor Evidence` document, storing metadata such as MIME type, file size, SharePoint path, and original message.
11. Update the child row’s `metadata` JSON to replace the raw `evidence` field with the SharePoint URL and save the document.

## Security Considerations (per SecureCoder rules)
- **Input Validation**: Checks for required `session` and `evidence` fields; raises explicit validation errors.
- **Size Limitation**: Enforces a 10 MB limit on uploaded files to mitigate DoS attacks.
- **Filename Safety**: Generates unpredictable filenames using a timestamp and UUID, avoiding path‑traversal or overwrite risks.
- **SharePoint Path Sanitisation**: Strips leading/trailing slashes and normalises each path segment before API calls.
- **Error Handling**: Logs detailed errors via `frappe.log_error` while preventing exception leakage to callers.
- **Permission Handling**: Uses `ignore_permissions=True` when creating `Proctor Evidence` documents, but the endpoint is exposed with `allow_guest=True` and should be protected by network-level access controls.

---
*Generated automatically for documentation purposes.*
