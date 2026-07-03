import frappe
import json
import base64
import os
import uuid
import requests
from urllib.parse import quote
from datetime import datetime
from frappe.utils import get_datetime, get_datetime_str, now_datetime, add_days
from ai_apps.api.Sharepoint.sharepoint_auth import get_sharepoint_client

def process_evidence(doc):
    """
    Scans child rows in doc.proctor_session_event for base64-encoded evidence,
    uploads them to SharePoint, creates Proctor Evidence documents,
    and replaces the base64 evidence in metadata with the SharePoint URL.
    """
    has_changes = False
    
    # Get SharePoint path setting if configured, else default
    sharepoint_base_path = frappe.conf.get("proctor_evidence_sharepoint_path") or "Proctor/Evidence"
    sharepoint_base_path = sharepoint_base_path.strip().strip("/")
    
    # Resolve the session name
    session_id = doc.session
    if not session_id:
        return
        
    for child in doc.proctor_session_event:
        if not child.metadata:
            continue
            
        try:
            # Parse metadata
            meta = json.loads(child.metadata) if isinstance(child.metadata, str) else child.metadata
            if not isinstance(meta, dict):
                continue
                
            evidence_data = meta.get("evidence")
            if not evidence_data or not isinstance(evidence_data, str):
                continue
                
            # If evidence is already a URL, skip processing
            if evidence_data.startswith("http://") or evidence_data.startswith("https://"):
                continue
                
            # Decode the base64 evidence
            file_bytes, mime_type, extension = decode_base64_file(evidence_data)
            if not file_bytes:
                continue
                
            # Enforce 10MB size limit to prevent Denial of Service (DoS)
            # TODO(security): File upload size limit check
            if len(file_bytes) > 10 * 1024 * 1024:
                frappe.logger().warning(f"Proctor evidence for session {session_id} skipped: file size exceeds 10MB limit")
                continue
                
            # Determine evidence type
            evidence_type = "screenshot" if "image" in mime_type else "audio" if "audio" in mime_type else "other"
            if "video" in mime_type:
                evidence_type = "video"
                
            # Prepare secure filename with unpredictable UUID component
            # TODO(security): Generate unique filename to prevent path traversal/overwrite
            timestamp_str = ""
            if child.occurred_at:
                try:
                    dt = get_datetime(child.occurred_at)
                    timestamp_str = dt.strftime("%Y%m%d_%H%M%S")
                except Exception:
                    pass
            if not timestamp_str:
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                
            unique_id = uuid.uuid4().hex[:8]
            filename = f"{child.event_type or 'EVIDENCE'}_{timestamp_str}_{unique_id}.{extension}"
            
            # Upload to SharePoint
            folder_path = f"{sharepoint_base_path}/{session_id}"
            full_folder_path = f"Real Estate - US/Novel One/{folder_path}"
            
            client = get_sharepoint_client()
            upload_result = upload_file_to_sharepoint_raw(client, full_folder_path, filename, file_bytes, mime_type)
            
            if upload_result and upload_result.get("success"):
                web_url = upload_result.get("web_url")
                download_url = upload_result.get("download_url") or web_url
                
                # Create Proctor Evidence document
                evidence_doc = frappe.new_doc("Proctor Evidence")
                evidence_doc.session = session_id
                evidence_doc.event = child.name  # Link to the child row (e.g. child table row name)
                evidence_doc.evidence_type = evidence_type
                evidence_doc.sharepoint_url = web_url
                evidence_doc.thumbnail_url = download_url if evidence_type == "screenshot" else None
                evidence_doc.captured_at = child.occurred_at or now_datetime()
                evidence_doc.retention_until = add_days(now_datetime(), 90)  # 90‑day retention
                
                # Save metadata
                evidence_doc.metadata = json.dumps({
                    "mime_type": mime_type,
                    "filename": filename,
                    "file_size": len(file_bytes),
                    "sharepoint_path": f"{full_folder_path}/{filename}",
                    "original_message": meta.get("message")
                })
                
                evidence_doc.insert(ignore_permissions=True)
                
                # Update event's metadata to point to SharePoint URL instead of raw base64
                meta["evidence"] = web_url
                meta["evidence_sharepoint_path"] = f"{full_folder_path}/{filename}"
                child.metadata = json.dumps(meta)
                child.evidence_link = web_url
                has_changes = True
                
                frappe.logger().info(f"✅ Uploaded proctor evidence to SharePoint and created Proctor Evidence: {filename}")
        except Exception as e:
            frappe.log_error(title="Failed to process proctor evidence", message=frappe.get_traceback())
            
    if has_changes:
        # Save modifications back to the document
        doc.save(ignore_permissions=True)
        frappe.db.commit()


def decode_base64_file(data_uri):
    """
    Decodes a base64 Data URI or raw base64 string into bytes, mime_type, and extension.
    """
    if not data_uri:
        return None, None, None
        
    mime_type = "image/jpeg"  # default
    extension = "jpg"        # default
    
    if data_uri.startswith("data:"):
        try:
            header, base64_data = data_uri.split(";base64,", 1)
            mime_type = header.split(":", 1)[1]
            
            # Map common mime-types to extensions (including extra audio formats)
            mime_map = {
                "image/jpeg": "jpg",
                "image/jpg": "jpg",
                "image/png": "png",
                "image/gif": "gif",
                "image/webp": "webp",
                "audio/wav": "wav",
                "audio/x-wav": "wav",
                "audio/webm": "webm",
                "audio/ogg": "ogg",
                "audio/mp3": "mp3",
                "audio/mpeg": "mp3",
                "audio/mp4": "mp4",
                "audio/flac": "flac"
            }
            extension = mime_map.get(mime_type, mime_type.split("/")[-1] if "/" in mime_type else "bin")
        except Exception:
            base64_data = data_uri
    else:
        base64_data = data_uri
        
    try:
        file_bytes = base64.b64decode(base64_data)
        return file_bytes, mime_type, extension
    except Exception as e:
        frappe.logger().error(f"Error decoding base64 data: {str(e)}")
        return None, None, None


def upload_file_to_sharepoint_raw(client, full_folder_path, filename, file_content, mime_type):
    """
    Upload raw bytes to a SharePoint folder using Microsoft Graph API.
    """
    # Existing implementation unchanged
    """
    Upload raw bytes to a SharePoint folder using Microsoft Graph API.
    Auto-creates the directory structure.
    """
    site_id = client['site_id']
    drive_id = client['drive_id']
    graph_base_url = client['graph_base_url']
    access_token = client['access_token']
    
    # Normalize folder path segments to strip leading/trailing spaces
    normalized_segments = [seg.strip() for seg in full_folder_path.split("/") if seg.strip()]
    normalized_folder_path = "/".join(normalized_segments)
    
    # Ensure folder structure exists
    _ensure_folder(client, normalized_folder_path)
    
    # Upload file
    encoded_folder_path = quote(normalized_folder_path)
    encoded_filename = quote(filename)
    
    upload_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{encoded_folder_path}/{encoded_filename}:/content"
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': mime_type or 'application/octet-stream'
    }
    
    try:
        response = requests.put(upload_url, headers=headers, data=file_content)
        response.raise_for_status()
        res_json = response.json()
        
        return {
            "success": True,
            "web_url": res_json.get("webUrl"),
            "download_url": res_json.get("@microsoft.graph.downloadUrl"),
            "id": res_json.get("id")
        }
    except Exception as e:
        frappe.log_error(title=f"SharePoint Upload Error for {filename}", message=str(e))
        return {
            "success": False,
            "error": str(e)
        }


def _ensure_folder(client: dict, full_folder_path: str) -> None:
    """
    Ensure that a full SharePoint folder path exists, creating any missing
    path segments from root downward.
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
@frappe.whitelist()
def store_evidence(**kwargs):
    """
    Directly upload a Base64‑encoded evidence blob (image or audio) to SharePoint.
    Returns a dict with the SharePoint URL and generated filename.
    """
    payload = frappe._dict(kwargs)
    session_id = payload.get('session')
    violation_type = payload.get('violation_type')
    evidence_data = payload.get('evidence')

    if not session_id:
        frappe.throw("Missing required field 'session' for evidence upload")
    if not evidence_data:
        frappe.throw("Missing required field 'evidence' for evidence upload")

    # Decode the Base64 payload
    file_bytes, mime_type, extension = decode_base64_file(evidence_data)
    if not file_bytes:
        frappe.throw("Failed to decode evidence data")

    # Enforce a 10 MB size limit to mitigate DoS risks
    if len(file_bytes) > 10 * 1024 * 1024:
        frappe.throw("Evidence exceeds 10 MB size limit")

    # Build a safe, unpredictable filename
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{violation_type or 'EVIDENCE'}_{timestamp_str}_{unique_id}.{extension}"

    # Resolve SharePoint folder (same logic as process_evidence)
    sharepoint_base_path = frappe.conf.get('proctor_evidence_sharepoint_path') or 'Proctor/Evidence'
    sharepoint_base_path = sharepoint_base_path.strip().strip('/')
    folder_path = f"{sharepoint_base_path}/{session_id}"
    full_folder_path = f"Real Estate - US/Novel One/{folder_path}"

    client = get_sharepoint_client()
    upload_res = upload_file_to_sharepoint_raw(client, full_folder_path, filename, file_bytes, mime_type)
    if not upload_res.get('success'):
        frappe.throw(f"SharePoint upload failed: {upload_res.get('error')}")

    web_url = upload_res.get('web_url')
    download_url = upload_res.get('download_url') or web_url

    evidence_type_cat = "screenshot" if "image" in mime_type else "audio" if "audio" in mime_type else "other"
    if "video" in mime_type:
        evidence_type_cat = "video"

    evidence_doc = frappe.new_doc("Proctor Evidence")
    evidence_doc.session = session_id
    evidence_doc.evidence_type = evidence_type_cat
    evidence_doc.sharepoint_url = web_url
    evidence_doc.thumbnail_url = download_url if evidence_type_cat == "screenshot" else None
    from frappe.utils import now_datetime, add_days
    evidence_doc.captured_at = now_datetime()
    evidence_doc.retention_until = add_days(now_datetime(), 90)  # 90‑day retention

    evidence_doc.metadata = json.dumps({
        "mime_type": mime_type,
        "filename": filename,
        "file_size": len(file_bytes),
        "sharepoint_path": f"{full_folder_path}/{filename}",
        "uploaded_via": "store_evidence"
    })

    evidence_doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {'url': web_url, 'filename': filename}
