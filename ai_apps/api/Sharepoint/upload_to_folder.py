"""
SharePoint Project Folder Upload API

Provides a secure, project-scoped API for uploading files into
any project folder (default or custom) in SharePoint.

Fixes applied:
  - Full URL encoding of folder paths (handles spaces & special chars)
  - Folder existence check before upload (prevents rogue folder creation)
  - Filename sanitization (strips SharePoint-blocked characters)

Usage:
    POST /api/method/landwise.api-no.Sharepoint.upload_to_folder.upload_to_project_folder
    Form-data:
        project      : "PROJ-0001"
        folder_path  : "My Custom Folder"           (relative to project root)
                       or "My Folder/Sub Folder"    (for sub-folders)
        file         : <one or more files>
"""

import frappe
import requests
import os
import re
import uuid
from urllib.parse import quote
from .sharepoint_auth import get_sharepoint_client


# ---------------------------------------------------------------------------
# Path normalization
# ---------------------------------------------------------------------------

def _normalize_path(path: str) -> str:
    """
    Strip spaces from every segment of a SharePoint folder path.

    SharePoint sanitizes folder names on creation (strips leading/trailing
    spaces), so we must normalize paths consistently before building URLs.

    Example:
        "  My Folder  /  Sub Folder  " → "My Folder/Sub Folder"
    """
    if not path:
        return path
    segments = [seg.strip() for seg in path.strip("/").split("/")]
    return "/".join(seg for seg in segments if seg)


# ---------------------------------------------------------------------------
# SharePoint filename safety
# ---------------------------------------------------------------------------

# Characters blocked by SharePoint in file/folder names
_SHAREPOINT_BLOCKED = re.compile(r'[\"*:<>?/\\|]')


def _sanitize_filename(filename: str) -> str:
    """
    Remove/replace characters that SharePoint rejects in filenames.

    Blocked characters: " * : < > ? / \\ |
    Also strips leading/trailing spaces and dots.

    Args:
        filename: Original filename from the upload

    Returns:
        str: Safe filename for SharePoint
    """
    if not filename:
        return "file"

    name, ext = os.path.splitext(filename)

    # Replace blocked characters with underscore
    name = _SHAREPOINT_BLOCKED.sub("_", name)

    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name)

    # Strip leading/trailing spaces and dots
    name = name.strip(" .")

    if not name:
        name = "file"

    return f"{name}{ext}"


# ---------------------------------------------------------------------------
# Folder existence check
# ---------------------------------------------------------------------------

def _folder_exists(client: dict, full_folder_path: str) -> bool:
    """
    Check whether a folder path exists in SharePoint via Graph API.

    Args:
        client: SharePoint client dict from get_sharepoint_client()
        full_folder_path: Full path e.g. "Real Estate - US/Novel One/Projects/..."

    Returns:
        bool: True if folder exists, False if 404
    """
    site_id = client["site_id"]
    drive_id = client["drive_id"]
    graph_base_url = client["graph_base_url"]
    headers = client["headers"]

    encoded_path = quote(full_folder_path)
    check_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}"

    try:
        resp = requests.get(check_url, headers=headers)
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        data = resp.json()
        # Make sure it's a folder (not a file with the same name)
        return "folder" in data
    except Exception:
        return False


def _ensure_folder(client: dict, full_folder_path: str) -> None:
    """
    Ensure that a full SharePoint folder path exists, creating any missing
    path segments from root downward.

    For example, given:
      "Real Estate - US/Novel One/Projects/PROJ/Downloads/asdfgg"
    it will attempt to create each segment in turn, no-oping on segments
    that already exist (SharePoint returns 200/201 for both cases).

    Args:
        client: SharePoint client dict from get_sharepoint_client()
        full_folder_path: Full path to ensure exists
    """
    site_id = client["site_id"]
    drive_id = client["drive_id"]
    graph_base_url = client["graph_base_url"]
    access_token = client["access_token"]

    create_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    segments = [s for s in full_folder_path.split("/") if s]
    # Walk from root downward, building each level
    for i in range(1, len(segments) + 1):
        partial_path = "/".join(segments[:i])
        encoded_partial = quote(partial_path)
        parent_path = "/".join(segments[:i - 1])

        if i == 1:
            # Root segment — skip, always exists in SharePoint drive
            continue

        # POST to parent's children to create this segment
        parent_encoded = quote(parent_path)
        create_url = (
            f"{graph_base_url}/sites/{site_id}/drives/{drive_id}"
            f"/root:/{parent_encoded}:/children"
        )
        payload = {
            "name": segments[i - 1],
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail",  # 409 = already exists, that's fine
        }
        try:
            resp = requests.post(create_url, headers=create_headers, json=payload)
            # 201 = created, 409 = already exists — both are fine
            if resp.status_code not in (201, 409):
                frappe.logger().warning(
                    f"_ensure_folder: unexpected status {resp.status_code} creating {partial_path}"
                )
        except Exception as e:
            frappe.logger().error(f"_ensure_folder error at '{partial_path}': {e}")


# ---------------------------------------------------------------------------
# Main upload API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def upload_to_project_folder(project, folder_path):
    """
    Upload one or more files into a specific project folder on SharePoint.

    The files are placed at:
        Real Estate - US/Novel One/Projects/{project_name}/{folder_path}/

    Args:
        project     : Frappe Project name (e.g., "PROJ-0001")
        folder_path : Relative path inside the project folder
                      e.g., "My Custom Folder" or "My Folder/Sub Folder"

    Returns:
        dict: {
            "success": True,
            "uploaded": N,
            "failed": N,
            "results": [ { "filename", "web_url", "download_url", "size" }, ... ]
        }
    """
    try:
        if not project:
            frappe.throw("project parameter is required")
        if not folder_path:
            frappe.throw("folder_path parameter is required")

        # Validate project exists in Frappe
        if not frappe.db.exists("Project", project):
            frappe.throw(f"Project '{project}' not found")

        # Resolve human-readable project name for SharePoint path
        project_name = frappe.db.get_value("Project", project, "project_name") or project

        # Get files from the request (multipart form-data)
        files = frappe.request.files.getlist("file")
        if not files:
            files = frappe.request.files.getlist("files")
        if not files:
            frappe.throw("No files provided. Send files with key 'file' or 'files'")

        # Build the full SharePoint folder path (plain string for display/logs)
        # _normalize_path strips spaces from every segment so "My Folder  " → "My Folder"
        folder_path = _normalize_path(folder_path)

        full_folder_path = f"Real Estate - US/Novel One/Projects/{project_name}/{folder_path}"


        # Get SharePoint client
        client = get_sharepoint_client()
        site_id = client["site_id"]
        drive_id = client["drive_id"]
        graph_base_url = client["graph_base_url"]
        access_token = client["access_token"]

        # ── Ensure target folder exists; auto-create if missing ─────────────
        if not _folder_exists(client, full_folder_path):
            frappe.logger().info(f"upload_to_project_folder: folder missing, auto-creating: {full_folder_path}")
            _ensure_folder(client, full_folder_path)

        # ── Issue 1 fix: URL-encode the folder path for Graph API URLs ──────
        encoded_folder_path = quote(full_folder_path)

        upload_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/octet-stream",
        }

        results = []
        success_count = 0
        failed_count = 0

        SIMPLE_UPLOAD_MAX = 4 * 1024 * 1024  # 4 MB — use resumable session above this

        for uploaded_file in files:
            try:
                original_filename = uploaded_file.filename or "file"

                # ── Issue 3 fix: Sanitize filename before sending to SharePoint ──
                safe_base = _sanitize_filename(original_filename)
                name_part, ext = os.path.splitext(safe_base)
                unique_id = uuid.uuid4().hex[:8]
                filename = f"{name_part}_{unique_id}{ext}"

                # URL-encode the final filename too (handles accented chars, etc.)
                encoded_filename = quote(filename)

                # Determine file size without loading entirely into memory
                uploaded_file.stream.seek(0, 2)
                file_size = uploaded_file.stream.tell()
                uploaded_file.stream.seek(0)

                # ── Issue 1 fix: Use encoded paths in all Graph API URLs ────────
                upload_url = (
                    f"{graph_base_url}/sites/{site_id}/drives/{drive_id}"
                    f"/root:/{encoded_folder_path}/{encoded_filename}:/content"
                )

                if file_size <= SIMPLE_UPLOAD_MAX:
                    # Simple PUT for small files (≤ 4 MB)
                    file_content = uploaded_file.stream.read()
                    resp = requests.put(upload_url, headers=upload_headers, data=file_content)
                    resp.raise_for_status()
                    uploaded_data = resp.json()
                else:
                    # Resumable upload session for large files (> 4 MB)
                    # ── Issue 5 fix: encode path in session URL too ────────────
                    session_url = (
                        f"{graph_base_url}/sites/{site_id}/drives/{drive_id}"
                        f"/root:/{encoded_folder_path}/{encoded_filename}:/createUploadSession"
                    )
                    session_headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    }
                    session_body = {
                        "item": {
                            "@microsoft.graph.conflictBehavior": "replace",
                            "name": filename,
                        }
                    }
                    session_resp = requests.post(session_url, headers=session_headers, json=session_body)
                    session_resp.raise_for_status()
                    resumable_url = session_resp.json().get("uploadUrl")

                    if not resumable_url:
                        raise Exception("Failed to create upload session")

                    uploaded_data = _upload_large_file(resumable_url, uploaded_file.stream, file_size)

                results.append({
                    "success": True,
                    "original_filename": original_filename,
                    "filename": filename,
                    "web_url": uploaded_data.get("webUrl") if uploaded_data else None,
                    "download_url": uploaded_data.get("@microsoft.graph.downloadUrl") if uploaded_data else None,
                    "id": uploaded_data.get("id") if uploaded_data else None,
                    "size": file_size,
                })
                success_count += 1
                frappe.logger().info(
                    f"✅ Uploaded to SharePoint: {original_filename} → {full_folder_path}/{filename}"
                )

            except Exception as file_err:
                results.append({
                    "success": False,
                    "filename": getattr(uploaded_file, "filename", "unknown"),
                    "error": str(file_err),
                })
                failed_count += 1
                frappe.logger().warning(
                    f"❌ Failed to upload {getattr(uploaded_file, 'filename', '?')}: {file_err}"
                )

        http_status = 200 if failed_count == 0 else 207
        frappe.local.response["http_status_code"] = http_status

        return {
            "success": failed_count == 0,
            "message": f"Uploaded {success_count} file(s). Failed: {failed_count}.",
            "project": project,
            "folder_path": full_folder_path,
            "total": len(files),
            "uploaded": success_count,
            "failed": failed_count,
            "results": results,
        }

    except Exception as e:
        frappe.local.response["http_status_code"] = 500
        frappe.log_error(frappe.get_traceback(), "Upload To Project Folder Error")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# 20 MB = exactly 64 × 320 KB — Graph API requires multiples of 320 KB
CHUNK_SIZE = 64 * 320 * 1024  # = 20,971,520 bytes


def _upload_large_file(upload_url: str, file_stream, file_size: int):
    """
    Stream-upload a large file in 20 MB chunks using a Microsoft Graph
    resumable upload session. Auto-resumes from last byte on failure.

    Args:
        upload_url  : The resumable session URL from Microsoft Graph
        file_stream : The file stream object (open in binary mode)
        file_size   : Total file size in bytes

    Returns:
        dict: Uploaded file metadata from Microsoft Graph (or None on failure)
    """
    # Resume check — ask the server where to start
    try:
        status = requests.get(upload_url).json()
        if status.get("nextExpectedRanges"):
            offset = int(status["nextExpectedRanges"][0].split("-")[0])
            file_stream.seek(offset)
        else:
            offset = 0
    except Exception:
        offset = 0
        file_stream.seek(0)

    uploaded_data = None

    while offset < file_size:
        chunk = file_stream.read(CHUNK_SIZE)
        length = len(chunk)
        end = offset + length - 1

        headers = {
            "Content-Length": str(length),
            "Content-Range": f"bytes {offset}-{end}/{file_size}",
        }

        resp = requests.put(upload_url, headers=headers, data=chunk)
        if resp.status_code in (200, 201):
            uploaded_data = resp.json()
            break
        elif resp.status_code != 202:
            resp.raise_for_status()

        offset += length

    return uploaded_data


