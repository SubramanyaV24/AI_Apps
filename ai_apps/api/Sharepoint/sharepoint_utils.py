"""
SharePoint Generic Utilities API

This module provides GENERIC SharePoint functions that can be used by ANY doctype:
- upload_files: Upload files to any SharePoint folder
- delete_file: Delete a file from SharePoint
- get_preview_urls: Get preview URLs for SharePoint links
- save_sharepoint_links: Save SharePoint links to any doctype's child table

These functions are designed to be reusable across Daily Logs, Tasks, Projects,
or any other doctype that needs SharePoint integration.

Child Table Structure (uses "sharepoint child Task" doctype):
- sharepoint_link: The web URL of the file
- sharepoint_path: The SharePoint path for deletion
- filename: The name of the file

Usage Examples:
    # Upload files
    POST /api/method/landwise.api-no.Sharepoint.sharepoint_utils.upload_files
    Body (form-data): folder_path="Projects/Daily Logs/Project Name", file=<files>

    # Delete file
    POST /api/method/landwise.api-no.Sharepoint.sharepoint_utils.delete_file
    Body: {"file_path": "Real Estate - US/Novel One/Projects/file.jpg"}

    # Get preview URLs
    POST /api/method/landwise.api-no.Sharepoint.sharepoint_utils.get_preview_urls
    Body: {"sharepoint_links": ["https://...", "https://..."]}

    # Save links to a doctype
    POST /api/method/landwise.api-no.Sharepoint.sharepoint_utils.save_sharepoint_links
    Body: {
        "doctype": "Daily Logs",
        "docname": "DL-0001",
        "child_table_field": "sharepoint_links",
        "links": [{"sharepoint_link": "...", "sharepoint_path": "...", "filename": "..."}]
    }
"""

import frappe
import requests
from .sharepoint_auth import get_sharepoint_client


# =============================================================================
# UPLOAD FILES
# =============================================================================

@frappe.whitelist()
def upload_files(folder_path):
    """
    Generic function to upload one or multiple files to any SharePoint folder.
    
    This function can be used for ANY doctype - just specify the folder path.
    
    Args:
        folder_path: Target folder in SharePoint (e.g., "Projects/Daily Logs/Project Name")
                    Will be prefixed with "Real Estate - US/Novel One/" automatically
    
    Returns:
        dict: {
            "success": True/False,
            "results": [
                {
                    "filename": "file.jpg",
                    "success": True/False,
                    "web_url": "https://sharepoint.com/...",
                    "download_url": "https://sharepoint.com/...",
                    "file_id": "unique-id",
                    "folder_path": "Real Estate - US/Novel One/Projects/..."
                }
            ],
            "total_files": 2,
            "successful": 2,
            "failed": 0
        }
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.sharepoint_utils.upload_files
        Body (form-data):
            - folder_path: "Projects/Daily Logs/My Project"
            - file: <file(s)>  (can select multiple files)
    """
    try:
        if not folder_path:
            frappe.throw("folder_path parameter is required")
        
        # Get uploaded files from request
        files = frappe.request.files.getlist('file')
        if not files:
            frappe.throw("No files provided. Please attach files using the 'file' field.")
        
        # Get SharePoint client
        client = get_sharepoint_client()
        access_token = client['access_token']
        site_id = client['site_id']
        drive_id = client['drive_id']
        graph_base_url = client['graph_base_url']
        
        # Normalize folder path - carefully strip spaces
        folder_path = folder_path.strip().strip('/')
        full_folder_path = f"Real Estate - US/Novel One/{folder_path}"
        
        results = []
        
        for file_storage in files:
            filename = file_storage.filename
            file_content = file_storage.read()
            file_size = len(file_content)
            
            try:
                # For files larger than 4MB, use upload session
                if file_size > 4 * 1024 * 1024:
                    upload_result = _upload_large_file(
                        client, full_folder_path, filename, file_content, file_size
                    )
                else:
                    # Direct upload for smaller files
                    upload_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{full_folder_path}/{filename}:/content"
                    
                    headers = {
                        'Authorization': f'Bearer {access_token}',
                        'Content-Type': 'application/octet-stream'
                    }
                    
                    response = requests.put(upload_url, headers=headers, data=file_content)
                    response.raise_for_status()
                    upload_result = response.json()
                
                results.append({
                    "filename": filename,
                    "success": True,
                    "web_url": upload_result.get("webUrl"),
                    "download_url": upload_result.get("@microsoft.graph.downloadUrl"),
                    "file_id": upload_result.get("id"),
                    "folder_path": f"{full_folder_path}/{filename}",
                    "size": file_size
                })
                
            except Exception as file_error:
                results.append({
                    "filename": filename,
                    "success": False,
                    "error": str(file_error)
                })
        
        successful = len([r for r in results if r.get("success")])
        failed = len(results) - successful
        
        return {
            "success": failed == 0,
            "results": results,
            "total_files": len(results),
            "successful": successful,
            "failed": failed,
            "folder_path": full_folder_path
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "SharePoint Upload Error")
        frappe.throw(f"Failed to upload files: {str(e)}")


def _upload_large_file(client, folder_path, filename, file_content, file_size):
    """
    Internal helper for uploading large files using resumable upload session.
    """
    access_token = client['access_token']
    site_id = client['site_id']
    drive_id = client['drive_id']
    graph_base_url = client['graph_base_url']
    
    # Create upload session
    session_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{folder_path}/{filename}:/createUploadSession"
    
    session_headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    session_body = {
        "item": {
            "@microsoft.graph.conflictBehavior": "replace"
        }
    }
    
    session_response = requests.post(session_url, headers=session_headers, json=session_body)
    session_response.raise_for_status()
    upload_url = session_response.json().get("uploadUrl")
    
    # Upload in chunks (20MB chunks)
    chunk_size = 20 * 1024 * 1024
    offset = 0
    
    while offset < file_size:
        chunk_end = min(offset + chunk_size, file_size)
        chunk_data = file_content[offset:chunk_end]
        
        chunk_headers = {
            'Content-Length': str(len(chunk_data)),
            'Content-Range': f'bytes {offset}-{chunk_end - 1}/{file_size}'
        }
        
        chunk_response = requests.put(upload_url, headers=chunk_headers, data=chunk_data)
        chunk_response.raise_for_status()
        
        offset = chunk_end
    
    return chunk_response.json()


# =============================================================================
# DELETE FILE
# =============================================================================

@frappe.whitelist()
def delete_file(file_path):
    """
    Delete a file from SharePoint using the full path.
    
    Args:
        file_path: Full path to the file in SharePoint
                  (e.g., "Real Estate - US/Novel One/Projects/file.jpg")
                  or relative path (will be prefixed with "Real Estate - US/Novel One/")
    
    Returns:
        dict: {
            "success": True/False,
            "message": "File deleted successfully",
            "file_path": "the deleted file path"
        }
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.sharepoint_utils.delete_file
        Body: {"file_path": "Real Estate - US/Novel One/Projects/file.jpg"}
    """
    try:
        if not file_path:
            frappe.throw("file_path parameter is required")
        
        # Get SharePoint client
        client = get_sharepoint_client()
        access_token = client['access_token']
        site_id = client['site_id']
        drive_id = client['drive_id']
        graph_base_url = client['graph_base_url']
        
        # Normalize path - carefully strip spaces
        normalized_path = file_path.strip().strip('/')
        
        # Ensure path starts with the required SharePoint base path
        if not normalized_path.startswith("Real Estate - US/"):
            normalized_path = f"Real Estate - US/Novel One/{normalized_path}"
        
        delete_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{normalized_path}"
        
        headers = {
            'Authorization': f'Bearer {access_token}',
        }
        
        response = requests.delete(delete_url, headers=headers)
        response.raise_for_status()
        
        frappe.logger().info(f"✅ File deleted from SharePoint: {file_path}")
        
        return {
            "success": True,
            "message": "File deleted successfully from SharePoint",
            "file_path": file_path
        }
        
    except requests.exceptions.HTTPError as http_error:
        error_response = http_error.response
        error_details = ""
        try:
            error_json = error_response.json()
            error_details = error_json.get('error', {}).get('message', str(http_error))
        except:
            error_details = str(http_error)
        
        if error_response.status_code == 404:
            return {
                "success": False,
                "message": f"File not found in SharePoint: {file_path}",
                "error": error_details
            }
        else:
            frappe.throw(f"Failed to delete file from SharePoint: {error_details}")
            
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "SharePoint Delete Error")
        frappe.throw(f"Failed to delete file: {str(e)}")


# =============================================================================
# GET PREVIEW URLs
# =============================================================================

@frappe.whitelist()
def get_preview_urls(sharepoint_links):
    """
    Get temporary preview/download URLs for multiple SharePoint files.
    
    These URLs can be used directly in <img> or <video> tags without authentication.
    URLs are temporary and expire after ~1 hour.
    
    Args:
        sharepoint_links: JSON array of SharePoint web URLs
                         e.g., ["https://novelteam.sharepoint.com/...", "..."]
    
    Returns:
        dict: {
            "success": True,
            "results": {
                "original_url_1": "preview_url_1",
                "original_url_2": "preview_url_2"
            },
            "total": 2,
            "successful": 2,
            "failed": 0
        }
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.sharepoint_utils.get_preview_urls
        Body: {"sharepoint_links": ["https://...", "https://..."]}
    """
    import json
    from urllib.parse import urlparse, unquote
    
    try:
        # Parse links if string
        if isinstance(sharepoint_links, str):
            sharepoint_links = json.loads(sharepoint_links)
        
        if not sharepoint_links or not isinstance(sharepoint_links, list):
            return {
                "success": True,
                "results": {},
                "total": 0,
                "successful": 0,
                "failed": 0
            }
        
        # Get SharePoint client
        client = get_sharepoint_client()
        access_token = client['access_token']
        site_id = client['site_id']
        drive_id = client['drive_id']
        graph_base_url = client['graph_base_url']
        
        results = {}
        successful = 0
        failed = 0
        
        for link in sharepoint_links:
            if not link:
                continue
            
            link = link.strip()
                
            try:
                # Extract file path from URL
                file_path = _extract_file_path_from_url(link)
                
                if not file_path:
                    results[link] = None
                    failed += 1
                    continue
                
                # Get download URL
                item_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{file_path}"
                
                headers = {
                    'Authorization': f'Bearer {access_token}',
                }
                
                response = requests.get(item_url, headers=headers)
                response.raise_for_status()
                
                item_data = response.json()
                download_url = item_data.get("@microsoft.graph.downloadUrl")
                
                if download_url:
                    results[link] = download_url
                    successful += 1
                else:
                    results[link] = None
                    failed += 1
                    
            except Exception as e:
                results[link] = None
                failed += 1
                frappe.logger().warning(f"Failed to get preview URL for {link}: {str(e)}")
        
        return {
            "success": True,
            "results": results,
            "total": len(sharepoint_links),
            "successful": successful,
            "failed": failed
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "SharePoint Preview URL Error")
        return {
            "success": False,
            "error": str(e),
            "results": {}
        }


def _extract_file_path_from_url(sharepoint_url):
    """
    Extract the file path from a SharePoint URL.
    
    Handles different URL formats:
    1. Direct URL: https://novelteam.sharepoint.com/sites/Noveloffice/Shared%20Documents/Real%20Estate%20-%20US/...
    2. Encoded URL with special characters
    """
    from urllib.parse import urlparse, unquote
    
    try:
        parsed = urlparse(sharepoint_url.strip())
        path = unquote(parsed.path).strip()
        
        # Look for the document library path
        markers = [
            "/sites/Noveloffice/Shared Documents/",
            "/Shared Documents/",
        ]
        
        for marker in markers:
            if marker in path:
                file_path = path.split(marker)[1]
                return file_path.strip().strip('/')
        
        return None
        
    except Exception:
        return None


# =============================================================================
# SAVE SHAREPOINT LINKS TO DOCTYPE
# =============================================================================

@frappe.whitelist()
def save_sharepoint_links(doctype, docname, child_table_field, links, append=True):
    """
    Save SharePoint links to any doctype's child table.
    
    Uses the "sharepoint child Task" child doctype structure:
    - sharepoint_link: The web URL
    - sharepoint_path: The path for deletion
    - filename: The file name
    
    Args:
        doctype: The parent doctype (e.g., "Daily Logs", "Task")
        docname: The document name
        child_table_field: The field name of the child table (e.g., "sharepoint_links")
        links: JSON array of link objects:
               [{"sharepoint_link": "...", "sharepoint_path": "...", "filename": "..."}]
        append: If True, append to existing links. If False, replace all links.
    
    Returns:
        dict: {
            "success": True,
            "doctype": "Daily Logs",
            "docname": "DL-0001",
            "links_saved": 3
        }
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.sharepoint_utils.save_sharepoint_links
        Body: {
            "doctype": "Daily Logs",
            "docname": "DL-0001",
            "child_table_field": "sharepoint_links",
            "links": [
                {"sharepoint_link": "https://...", "sharepoint_path": "Real Estate.../file.jpg", "filename": "file.jpg"}
            ],
            "append": true
        }
    """
    import json
    
    try:
        if not doctype:
            frappe.throw("doctype parameter is required")
        if not docname:
            frappe.throw("docname parameter is required")
        if not child_table_field:
            frappe.throw("child_table_field parameter is required")
        
        # Parse links if string
        if isinstance(links, str):
            links = json.loads(links)
        
        if not links or not isinstance(links, list):
            return {
                "success": True,
                "doctype": doctype,
                "docname": docname,
                "links_saved": 0,
                "message": "No links provided"
            }
        
        # Parse append flag
        if isinstance(append, str):
            append = append.lower() in ['true', '1', 'yes']
        
        # Get the document
        doc = frappe.get_doc(doctype, docname)
        
        # Clear existing links if not appending
        if not append:
            doc.set(child_table_field, [])
        
        # Add new links
        for link_data in links:
            # Skip if no sharepoint_link
            sharepoint_link = link_data.get("sharepoint_link") or link_data.get("web_url") or link_data.get("download_url")
            if not sharepoint_link:
                continue
            
            doc.append(child_table_field, {
                "sharepoint_link": sharepoint_link,
                "sharepoint_path": link_data.get("sharepoint_path") or link_data.get("folder_path") or "",
                "filename": link_data.get("filename") or "",
                "uploaded_by": frappe.session.user
            })
        
        # Save the document
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        return {
            "success": True,
            "doctype": doctype,
            "docname": docname,
            "child_table_field": child_table_field,
            "links_saved": len(links),
            "message": f"Successfully saved {len(links)} link(s)"
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Save SharePoint Links Error")
        return {
            "success": False,
            "error": str(e)
        }


# =============================================================================
# DELETE SHAREPOINT LINK FROM DOCTYPE
# =============================================================================

@frappe.whitelist()
def delete_sharepoint_link(doctype, docname, child_table_field, link_name, delete_from_sharepoint=True):
    """
    Delete a SharePoint link from a doctype's child table and optionally from SharePoint.
    
    Args:
        doctype: The parent doctype (e.g., "Daily Logs", "Task")
        docname: The document name
        child_table_field: The field name of the child table (e.g., "sharepoint_links")
        link_name: The name of the child table row to delete
        delete_from_sharepoint: If True, also delete the file from SharePoint
    
    Returns:
        dict: {
            "success": True,
            "doctype": "Daily Logs",
            "docname": "DL-0001",
            "link_deleted": "row-name",
            "sharepoint_deleted": True/False
        }
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.sharepoint_utils.delete_sharepoint_link
        Body: {
            "doctype": "Daily Logs",
            "docname": "DL-0001",
            "child_table_field": "sharepoint_links",
            "link_name": "abc123",
            "delete_from_sharepoint": true
        }
    """
    try:
        if not doctype:
            frappe.throw("doctype parameter is required")
        if not docname:
            frappe.throw("docname parameter is required")
        if not child_table_field:
            frappe.throw("child_table_field parameter is required")
        if not link_name:
            frappe.throw("link_name parameter is required")
        
        # Parse delete_from_sharepoint flag
        if isinstance(delete_from_sharepoint, str):
            delete_from_sharepoint = delete_from_sharepoint.lower() in ['true', '1', 'yes']
        
        # Get the document
        doc = frappe.get_doc(doctype, docname)
        
        # Find and remove the link
        found = False
        sharepoint_path = None
        child_table = doc.get(child_table_field) or []
        
        for item in child_table:
            if item.name == link_name:
                sharepoint_path = item.sharepoint_path
                child_table.remove(item)
                found = True
                break
        
        if not found:
            return {
                "success": False,
                "message": f"Link '{link_name}' not found in {doctype} {docname}"
            }
        
        # Save the document
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        # Delete from SharePoint if requested
        sharepoint_deleted = False
        if delete_from_sharepoint and sharepoint_path:
            try:
                result = delete_file(sharepoint_path)
                sharepoint_deleted = result.get("success", False)
            except Exception as sp_error:
                frappe.logger().warning(f"Failed to delete from SharePoint: {str(sp_error)}")
        
        return {
            "success": True,
            "doctype": doctype,
            "docname": docname,
            "link_deleted": link_name,
            "sharepoint_deleted": sharepoint_deleted
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Delete SharePoint Link Error")
        return {
            "success": False,
            "error": str(e)
        }
