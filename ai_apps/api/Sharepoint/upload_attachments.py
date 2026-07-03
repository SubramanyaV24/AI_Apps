"""
SharePoint Attachments API

This module provides functionality to:
- Upload attachments (images, videos) to SharePoint
- List images from a property folder
- List videos from a property folder

Uses the shared authentication module for efficient API calls.
"""

import frappe
import requests
from .sharepoint_auth import get_sharepoint_client
import uuid
import os


@frappe.whitelist(allow_guest=True)
def upload_attachments(folder_path):
    """
    Generic function to upload one or multiple attachments to any SharePoint folder.
    
    This is a global/reusable function that can be used for any scenario:
    - Projects: folder_path = "Projects/Daily Logs/Project/{project_name}"
    - Remodel: folder_path = "Remodel/OnfieldAnalysis/{property_name}"
    - Any other: Just provide the appropriate folder_path
    
    The full SharePoint path will be: Real Estate - US/Novel One/{folder_path}
    
    Args:
        folder_path: The folder path relative to "Real Estate - US/Novel One/"
                     e.g., "Projects/Daily Logs/Project/4927 Heatherglen Dr"
        file/files: Single file or multiple files (from form data)
    
    Returns:
        dict: Upload results with SharePoint URLs for all files
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.upload_attachments.upload_attachments
        Body (form-data):
            - folder_path: "Projects/Daily Logs/Project/My Project Name"
            - file: <file(s)>  (can select multiple files)
    """
    try:
        if not folder_path:
            frappe.throw("folder_path parameter is required")
        
        # Get files from request - handle both single and multiple files
        files = frappe.request.files.getlist('file')
        if not files:
            files = frappe.request.files.getlist('files')
        if not files:
            frappe.throw("No files provided. Please upload files with key 'file' or 'files'")
        
        # Get SharePoint client
        client = get_sharepoint_client()
        site_id = client['site_id']
        drive_id = client['drive_id']
        graph_base_url = client['graph_base_url']
        
        # Build full folder path - Carefully strip starting and ending spaces
        folder_path = folder_path.strip().strip('/')
        full_folder_path = f"Real Estate - US/Novel One/{folder_path}"
        
        upload_headers = {
            'Authorization': f'Bearer {client["access_token"]}',
            'Content-Type': 'application/octet-stream'
        }
        
        results = []
        success_count = 0
        failed_count = 0
        
        for uploaded_file in files:
            try:
                original_filename = uploaded_file.filename
                
                # Add unique ID to filename to prevent conflicts across daily logs/features
                name_part, ext = os.path.splitext(original_filename)
                unique_id = uuid.uuid4().hex[:8]
                filename = f"{name_part}_{unique_id}{ext}"

                file_content = uploaded_file.stream.read()
                
                # Upload file
                upload_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{full_folder_path}/{filename}:/content"
                
                response = requests.put(upload_url, headers=upload_headers, data=file_content)
                response.raise_for_status()
                
                uploaded_data = response.json()
                
                results.append({
                    "success": True,
                    "filename": filename,
                    "web_url": uploaded_data.get('webUrl'),
                    "download_url": uploaded_data.get('@microsoft.graph.downloadUrl'),
                    "id": uploaded_data.get('id'),
                    "size": uploaded_data.get('size'),
                    "mime_type": uploaded_data.get('file', {}).get('mimeType')
                })
                success_count += 1
                
                frappe.logger().info(f"✅ Uploaded to SharePoint: {original_filename} -> {filename} in {full_folder_path}")
                
            except Exception as file_error:
                results.append({
                    "success": False,
                    "filename": uploaded_file.filename,
                    "error": str(file_error)
                })
                failed_count += 1
                frappe.logger().warning(f"❌ Failed to upload {uploaded_file.filename}: {str(file_error)}")
        
        # If any files failed, return error status
        if failed_count > 0:
            frappe.local.response['http_status_code'] = 207  # Multi-Status
            return {
                "success": False,
                "message": f"Upload incomplete. Success: {success_count}, Failed: {failed_count}",
                "folder_path": full_folder_path,
                "total": len(files),
                "uploaded": success_count,
                "failed": failed_count,
                "results": results
            }

        return {
            "success": True,
            "message": f"Upload completed successfully. {success_count} file(s) uploaded.",
            "folder_path": full_folder_path,
            "total": len(files),
            "uploaded": success_count,
            "failed": failed_count,
            "results": results
        }
        
    except Exception as e:
        frappe.local.response['http_status_code'] = 500
        frappe.log_error(frappe.get_traceback(), "SharePoint Upload Attachments Error")
        return {
            "success": False,
            "error": f"Failed to upload attachments: {str(e)}"
        }


@frappe.whitelist(allow_guest=True)
def get_images(property_name):
    """
    Get list of images from a property's Images folder in SharePoint.
    
    Folder path: Real Estate - US/Novel One/Remodel/OnfieldAnalysis/{property_name}/Images
    
    Args:
        property_name: The property address/name
    
    Returns:
        dict: List of images with their URLs and metadata
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.upload_attachments.get_images
        Body: {"property_name": "123 Main Street"}
    """
    try:
        if not property_name:
            frappe.throw("property_name parameter is required")
        
        # Get SharePoint client
        client = get_sharepoint_client()
        site_id = client['site_id']
        drive_id = client['drive_id']
        graph_base_url = client['graph_base_url']
        headers = client['headers']
        
        # Build folder path
        folder_path = f"Real Estate - US/Novel One/Remodel/OnfieldAnalysis/{property_name}/Images"
        
        # List files in the folder
        list_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{folder_path}:/children"
        
        response = requests.get(list_url, headers=headers)
        
        # If folder doesn't exist, create it and return empty list
        if response.status_code == 404:
            # Try to create the Images folder
            from .create_folder import create_sharepoint_folder
            create_sharepoint_folder(folder_path)
            
            # Also create the Videos folder at the same time
            videos_folder_path = f"Real Estate - US/Novel One/Remodel/OnfieldAnalysis/{property_name}/Videos"
            create_sharepoint_folder(videos_folder_path)
            
            return {
                "success": True,
                "property_name": property_name,
                "folder_path": folder_path,
                "images": [],
                "count": 0,
                "message": "Images folder created, no images yet"
            }
        
        response.raise_for_status()
        data = response.json()
        
        # Filter for image files only
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tiff', '.tif']
        images = []
        
        for item in data.get('value', []):
            # Skip folders
            if 'folder' in item:
                continue
            
            file_name = item.get('name', '')
            file_ext = file_name.lower()[file_name.rfind('.'):]
            
            if file_ext in image_extensions:
                images.append({
                    "name": file_name,
                    "id": item.get('id'),
                    "web_url": item.get('webUrl'),
                    "download_url": item.get('@microsoft.graph.downloadUrl'),
                    "size": item.get('size'),
                    "created": item.get('createdDateTime'),
                    "modified": item.get('lastModifiedDateTime'),
                    "mime_type": item.get('file', {}).get('mimeType')
                })
        
        return {
            "success": True,
            "property_name": property_name,
            "folder_path": folder_path,
            "images": images,
            "count": len(images)
        }
        
    except requests.exceptions.HTTPError as http_error:
        error_response = http_error.response
        error_details = ""
        try:
            error_json = error_response.json()
            error_details = error_json.get('error', {}).get('message', str(http_error))
        except:
            error_details = str(http_error)
        
        return {
            "success": False,
            "property_name": property_name,
            "error": error_details,
            "images": [],
            "count": 0
        }
    except Exception as e:
        return {
            "success": False,
            "property_name": property_name,
            "error": str(e),
            "images": [],
            "count": 0
        }


@frappe.whitelist(allow_guest=True)
def get_videos(property_name):
    """
    Get list of videos from a property's Videos folder in SharePoint.
    
    Folder path: Real Estate - US/Novel One/Remodel/OnfieldAnalysis/{property_name}/Videos
    
    Args:
        property_name: The property address/name
    
    Returns:
        dict: List of videos with their URLs and metadata
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.upload_attachments.get_videos
        Body: {"property_name": "123 Main Street"}
    """
    try:
        if not property_name:
            frappe.throw("property_name parameter is required")
        
        # Get SharePoint client
        client = get_sharepoint_client()
        site_id = client['site_id']
        drive_id = client['drive_id']
        graph_base_url = client['graph_base_url']
        headers = client['headers']
        
        # Build folder path
        folder_path = f"Real Estate - US/Novel One/Remodel/OnfieldAnalysis/{property_name}/Videos"
        
        # List files in the folder
        list_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{folder_path}:/children"
        
        response = requests.get(list_url, headers=headers)
        
        # If folder doesn't exist, create it and return empty list
        if response.status_code == 404:
            # Try to create the folder
            from .create_folder import create_sharepoint_folder
            create_sharepoint_folder(folder_path)
            
            return {
                "success": True,
                "property_name": property_name,
                "folder_path": folder_path,
                "videos": [],
                "count": 0,
                "message": "Videos folder created, no videos yet"
            }
        
        response.raise_for_status()
        data = response.json()
        
        # Filter for video files only
        video_extensions = ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm', '.m4v', '.mpeg', '.mpg']
        videos = []
        
        for item in data.get('value', []):
            # Skip folders
            if 'folder' in item:
                continue
            
            file_name = item.get('name', '')
            file_ext = file_name.lower()[file_name.rfind('.'):]
            
            if file_ext in video_extensions:
                videos.append({
                    "name": file_name,
                    "id": item.get('id'),
                    "web_url": item.get('webUrl'),
                    "download_url": item.get('@microsoft.graph.downloadUrl'),
                    "size": item.get('size'),
                    "created": item.get('createdDateTime'),
                    "modified": item.get('lastModifiedDateTime'),
                    "mime_type": item.get('file', {}).get('mimeType'),
                    "duration": item.get('video', {}).get('duration')  # Duration in milliseconds if available
                })
        
        return {
            "success": True,
            "property_name": property_name,
            "folder_path": folder_path,
            "videos": videos,
            "count": len(videos)
        }
        
    except requests.exceptions.HTTPError as http_error:
        error_response = http_error.response
        error_details = ""
        try:
            error_json = error_response.json()
            error_details = error_json.get('error', {}).get('message', str(http_error))
        except:
            error_details = str(http_error)
        
        return {
            "success": False,
            "property_name": property_name,
            "error": error_details,
            "videos": [],
            "count": 0
        }
    except Exception as e:
        return {
            "success": False,
            "property_name": property_name,
            "error": str(e),
            "videos": [],
            "count": 0
        }


@frappe.whitelist(allow_guest=True)
def upload_images(property_name):
    """
    Upload one or multiple images to a property's Images folder in SharePoint.
    
    Folder path: Real Estate - US/Novel One/Remodel/OnfieldAnalysis/{property_name}/Images
    
    Args:
        property_name: The property address/name (from form data)
        file/files: Single file or multiple files (from form data)
    
    Returns:
        dict: Upload results for all files
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.upload_attachments.upload_images
        Body (form-data):
            - property_name: "123 Main Street"
            - file: <image file(s)>  (can select multiple files)
    """
    try:
        if not property_name:
            frappe.throw("property_name parameter is required")
        
        # Get files from request - handle both single and multiple files
        files = frappe.request.files.getlist('file')
        if not files:
            files = frappe.request.files.getlist('files')
        if not files:
            frappe.throw("No files provided. Please upload files with key 'file' or 'files'")
        
        # Get SharePoint client
        client = get_sharepoint_client()
        site_id = client['site_id']
        drive_id = client['drive_id']
        graph_base_url = client['graph_base_url']
        
        # Build folder path
        folder_path = f"Real Estate - US/Novel One/Remodel/OnfieldAnalysis/{property_name}/Images"
        
        upload_headers = {
            'Authorization': f'Bearer {client["access_token"]}',
            'Content-Type': 'application/octet-stream'
        }
        
        results = []
        success_count = 0
        failed_count = 0
        
        for uploaded_file in files:
            try:
                file_content = uploaded_file.stream.read()
                filename = uploaded_file.filename
                
                # Upload file
                upload_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{folder_path}/{filename}:/content"
                
                response = requests.put(upload_url, headers=upload_headers, data=file_content)
                response.raise_for_status()
                
                uploaded_data = response.json()
                
                results.append({
                    "success": True,
                    "filename": filename,
                    "web_url": uploaded_data.get('webUrl'),
                    "download_url": uploaded_data.get('@microsoft.graph.downloadUrl'),
                    "id": uploaded_data.get('id')
                })
                success_count += 1
                
            except Exception as file_error:
                results.append({
                    "success": False,
                    "filename": uploaded_file.filename,
                    "error": str(file_error)
                })
                failed_count += 1
        
        # If any files failed, throw an error with detailed information
        if failed_count > 0:
            error_details = [r for r in results if not r.get('success')]
            frappe.local.response['http_status_code'] = 400
            return {
                "success": False,
                "message": f"Upload failed. Success: {success_count}, Failed: {failed_count}",
                "property_name": property_name,
                "folder_path": folder_path,
                "total": len(files),
                "uploaded": success_count,
                "failed": failed_count,
                "results": results
            }
        
        return {
            "success": True,
            "message": f"Upload completed successfully. {success_count} file(s) uploaded.",
            "property_name": property_name,
            "folder_path": folder_path,
            "total": len(files),
            "uploaded": success_count,
            "failed": failed_count,
            "results": results
        }
        
    except Exception as e:
        frappe.local.response['http_status_code'] = 500
        return {
            "success": False,
            "error": f"Failed to upload images: {str(e)}"
        }


# Streaming upload helper - 20MB chunks (must be multiple of 320 KB)
# 320 KB = 327,680 bytes
# 20 * 1024 * 1024 = 20,971,520 (NOT divisible by 320 KB)
# Correct safe value: 64 * 320 KB * 1 = 20,971,520 is close but let's use exact multiple
# 20 * 1024 * 1024 + 327680 = 21,299,200 bytes (perfectly aligned)
CHUNK_SIZE = 21299200


def upload_large_file(upload_url, file_stream, file_size):
    """
    Upload a large file using resumable upload session with streaming.
    Streams from disk, never loads entire file into RAM.
    Auto-resumes on failures, TLS-safe, supports up to 250GB.
    
    Args:
        upload_url: The upload session URL from Microsoft Graph
        file_stream: The file stream object
        file_size: Total file size in bytes
    
    Returns:
        dict: The uploaded file data from Microsoft Graph
    """
    # Resume check - see where server expects next byte
    try:
        status = requests.get(upload_url).json()
        if status.get("nextExpectedRanges"):
            offset = int(status["nextExpectedRanges"][0].split("-")[0])
            file_stream.seek(offset)
        else:
            offset = 0
    except:
        # If check fails, start from beginning
        offset = 0
        file_stream.seek(0)
    
    uploaded_data = None

    while offset < file_size:
        chunk = file_stream.read(CHUNK_SIZE)
        length = len(chunk)
        end = offset + length - 1

        headers = {
            "Content-Length": str(length),
            "Content-Range": f"bytes {offset}-{end}/{file_size}"
        }

        r = requests.put(upload_url, headers=headers, data=chunk)
        if r.status_code in (200, 201):
            # Upload complete
            uploaded_data = r.json()
            break
        elif r.status_code != 202:
            # 202 = Accepted, continue uploading
            r.raise_for_status()

        offset += length

    return uploaded_data


@frappe.whitelist(allow_guest=True)
def upload_videos(property_name):
    """
    Upload one or multiple videos to a property's Videos folder in SharePoint.
    
    Folder path: Real Estate - US/Novel One/Remodel/OnfieldAnalysis/{property_name}/Videos
    
    Args:
        property_name: The property address/name (from form data)
        file/files: Single file or multiple files (from form data)
    
    Returns:
        dict: Upload results for all files
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.upload_attachments.upload_videos
        Body (form-data):
            - property_name: "123 Main Street"
            - file: <video file(s)>  (can select multiple files)
    """
    try:
        if not property_name:
            frappe.throw("property_name parameter is required")
        
        # Get files from request - handle both single and multiple files
        files = frappe.request.files.getlist('file')
        if not files:
            files = frappe.request.files.getlist('files')
        if not files:
            frappe.throw("No files provided. Please upload files with key 'file' or 'files'")
        
        # Get SharePoint client
        client = get_sharepoint_client()
        site_id = client['site_id']
        drive_id = client['drive_id']
        graph_base_url = client['graph_base_url']
        
        # Build folder path
        folder_path = f"Real Estate - US/Novel One/Remodel/OnfieldAnalysis/{property_name}/Videos"
        
        results = []
        success_count = 0
        failed_count = 0
        
        # Microsoft Graph API limits:
        # - Simple PUT upload: max 4MB
        # - Resumable upload session: up to 250GB (practical limit ~15GB for videos)
        SIMPLE_UPLOAD_MAX_SIZE = 4 * 1024 * 1024  # 4MB
        
        for uploaded_file in files:
            try:
                filename = uploaded_file.filename
                
                # Get file size without loading into memory
                uploaded_file.stream.seek(0, 2)  # Seek to end
                file_size = uploaded_file.stream.tell()
                uploaded_file.stream.seek(0)  # Seek back to start
                
                if file_size <= SIMPLE_UPLOAD_MAX_SIZE:
                    # Use simple PUT for small files (<= 4MB)
                    file_content = uploaded_file.stream.read()
                    upload_headers = {
                        'Authorization': f'Bearer {client["access_token"]}',
                        'Content-Type': 'application/octet-stream'
                    }
                    upload_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{folder_path}/{filename}:/content"
                    
                    response = requests.put(upload_url, headers=upload_headers, data=file_content)
                    response.raise_for_status()
                    
                    uploaded_data = response.json()
                else:
                    # Use resumable upload session for large files (> 4MB)
                    # Step 1: Create upload session
                    session_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{folder_path}/{filename}:/createUploadSession"
                    session_headers = {
                        'Authorization': f'Bearer {client["access_token"]}',
                        'Content-Type': 'application/json'
                    }
                    session_body = {
                        "item": {
                            "@microsoft.graph.conflictBehavior": "replace",
                            "name": filename
                        }
                    }
                    
                    session_response = requests.post(session_url, headers=session_headers, json=session_body)
                    session_response.raise_for_status()
                    session_data = session_response.json()
                    upload_url = session_data.get('uploadUrl')
                    
                    if not upload_url:
                        raise Exception("Failed to create upload session")
                    
                    # Step 2: Stream upload in 20MB chunks (no RAM usage)
                    uploaded_data = upload_large_file(upload_url, uploaded_file.stream, file_size)
                
                results.append({
                    "success": True,
                    "filename": filename,
                    "web_url": uploaded_data.get('webUrl') if uploaded_data else None,
                    "download_url": uploaded_data.get('@microsoft.graph.downloadUrl') if uploaded_data else None,
                    "id": uploaded_data.get('id') if uploaded_data else None,
                    "size": file_size
                })
                success_count += 1
                
            except requests.exceptions.HTTPError as http_error:
                error_details = str(http_error)
                try:
                    error_json = http_error.response.json()
                    error_details = error_json.get('error', {}).get('message', str(http_error))
                except:
                    pass
                results.append({
                    "success": False,
                    "filename": uploaded_file.filename,
                    "error": error_details
                })
                failed_count += 1
            except Exception as file_error:
                results.append({
                    "success": False,
                    "filename": uploaded_file.filename,
                    "error": str(file_error)
                })
                failed_count += 1
        
        # If any files failed, return error status
        if failed_count > 0:
            frappe.local.response['http_status_code'] = 400
            return {
                "success": False,
                "message": f"Upload failed. Success: {success_count}, Failed: {failed_count}",
                "property_name": property_name,
                "folder_path": folder_path,
                "total": len(files),
                "uploaded": success_count,
                "failed": failed_count,
                "results": results
            }
        
        return {
            "success": True,
            "message": f"Upload completed successfully. {success_count} video(s) uploaded.",
            "property_name": property_name,
            "folder_path": folder_path,
            "total": len(files),
            "uploaded": success_count,
            "failed": failed_count,
            "results": results
        }
        
    except Exception as e:
        frappe.local.response['http_status_code'] = 500
        return {
            "success": False,
            "error": f"Failed to upload videos: {str(e)}"
        }


@frappe.whitelist(allow_guest=True)
def delete_attachment(property_name, file_id, file_type, file_name=None):
    """
    Delete an attachment from SharePoint and remove its link from the Remodel doctype.
    
    Args:
        property_name: The property address/name
        file_id: The SharePoint file ID to delete
        file_type: Either "image" or "video"
        file_name: Optional - the filename (used to match and remove from child table)
    
    Returns:
        dict: Success status
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.upload_attachments.delete_attachment
        Body: {"property_name": "123 Main Street", "file_id": "abc123", "file_type": "image"}
    """
    try:
        if not property_name:
            frappe.throw("property_name parameter is required")
        
        if not file_id:
            frappe.throw("file_id parameter is required")
        
        if file_type not in ["image", "video"]:
            frappe.throw("file_type must be 'image' or 'video'")
        
        # Get SharePoint client
        client = get_sharepoint_client()
        site_id = client['site_id']
        drive_id = client['drive_id']
        graph_base_url = client['graph_base_url']
        headers = client['headers']
        
        # Delete the file from SharePoint using the file ID
        delete_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/items/{file_id}"
        
        response = requests.delete(delete_url, headers=headers)
        
        # 204 No Content = successful deletion, 404 = file not found (already deleted)
        if response.status_code not in [204, 404]:
            response.raise_for_status()
        
        sharepoint_deleted = response.status_code == 204
        
        # Now remove the link from the Remodel doctype if it exists
        link_removed = False
        try:
            from urllib.parse import unquote
            doc = frappe.get_doc("Remodel", property_name)
            
            if file_type == "image":
                # Get current image links
                current_links = doc.get("image_links") or []
                # Filter out the link that matches the file name
                new_links = []
                for link in current_links:
                    link_value = link.get("image_link") or ""
                    # URL decode and case-insensitive match
                    decoded_link = unquote(link_value).lower()
                    file_name_lower = (file_name or "").lower()
                    
                    if file_name and file_name_lower in decoded_link:
                        link_removed = True
                        frappe.logger().info(f"Removing image link: {link_value}")
                        continue
                    new_links.append(link)
                
                if link_removed:
                    doc.set("image_links", [])
                    for link in new_links:
                        doc.append("image_links", {"image_link": link.get("image_link")})
                    doc.save(ignore_permissions=True)
                    frappe.db.commit()
            
            elif file_type == "video":
                # Get current video links
                current_links = doc.get("video_links") or []
                # Filter out the link that matches the file name
                new_links = []
                for link in current_links:
                    link_value = link.get("video_links") or ""
                    # URL decode and case-insensitive match
                    decoded_link = unquote(link_value).lower()
                    file_name_lower = (file_name or "").lower()
                    
                    if file_name and file_name_lower in decoded_link:
                        link_removed = True
                        frappe.logger().info(f"Removing video link: {link_value}")
                        continue
                    new_links.append(link)
                
                if link_removed:
                    doc.set("video_links", [])
                    for link in new_links:
                        doc.append("video_links", {"video_links": link.get("video_links")})
                    doc.save(ignore_permissions=True)
                    frappe.db.commit()
        
        except Exception as doc_error:
            frappe.logger().warning(f"Could not update doctype links: {str(doc_error)}")
        
        return {
            "success": True,
            "property_name": property_name,
            "file_id": file_id,
            "file_type": file_type,
            "sharepoint_deleted": sharepoint_deleted,
            "link_removed": link_removed,
            "message": f"{'File deleted from SharePoint' if sharepoint_deleted else 'File not found in SharePoint'}. {'Link removed from doctype.' if link_removed else ''}"
        }
        
    except requests.exceptions.HTTPError as http_error:
        error_response = http_error.response
        error_details = ""
        try:
            error_json = error_response.json()
            error_details = error_json.get('error', {}).get('message', str(http_error))
        except:
            error_details = str(http_error)
        
        return {
            "success": False,
            "property_name": property_name,
            "error": error_details
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "SharePoint Delete Attachment Error")
        return {
            "success": False,
            "property_name": property_name,
            "error": str(e)
        }

