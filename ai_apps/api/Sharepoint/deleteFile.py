"""
SharePoint File Deletion API

This module provides functionality to delete files from SharePoint.
Uses the shared authentication module for efficient API calls.
"""

import frappe
import requests
from .sharepoint_auth import get_sharepoint_client


@frappe.whitelist()
def delete_file_from_sharepoint(file_path):
    """
    Delete a file from SharePoint using Graph API.
    
    Args:
        file_path: Full path to the file in SharePoint (e.g., "Real Estate - US/Novel One/Tasks/Images/photo.jpg")
                   or relative path from the document library root
    
    Returns:
        dict: Success message with deleted file path
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.deleteFile.delete_file_from_sharepoint
        Body: {"file_path": "Real Estate - US/Novel One/Tasks/Images/photo.jpg"}
    """
    try:
        if not file_path:
            frappe.throw("file_path parameter is required")
        
        # Get SharePoint client (uses cached authentication - no need to fetch site_id/drive_id again!)
        client = get_sharepoint_client()
        access_token = client['access_token']
        site_id = client['site_id']
        drive_id = client['drive_id']
        graph_base_url = client['graph_base_url']
        
        # Construct delete URL
        # Remove leading/trailing slashes and normalize path
        normalized_path = file_path.strip('/')
        
        # Ensure path starts with the required SharePoint base path
        if not normalized_path.startswith("Real Estate - US/"):
            normalized_path = f"Real Estate - US/Novel One/{normalized_path}"
            
        delete_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{normalized_path}"
        
        delete_headers = {
            'Authorization': f'Bearer {access_token}',
        }
        
        # Delete the file
        delete_response = requests.delete(delete_url, headers=delete_headers)
        delete_response.raise_for_status()
        
        frappe.logger().info(f"✅ File deleted successfully from SharePoint: {file_path}")
        
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
            frappe.throw(f"File not found in SharePoint: {file_path}\n\n{error_details}")
        elif error_response.status_code == 401:
            frappe.throw(
                f"SharePoint authentication failed: {error_details}\n\n"
                "Please verify:\n"
                "1. Client ID and Client Secret are correct\n"
                "2. Tenant ID is correct (if specified)\n"
                "3. App has necessary permissions granted\n"
                "4. Admin consent has been granted"
            )
        elif error_response.status_code == 403:
            frappe.throw(
                f"SharePoint access denied: {error_details}\n\n"
                "Please verify that:\n"
                "1. The app registration has the necessary permissions\n"
                "2. The app is granted access to the SharePoint site\n"
                "3. Admin consent has been granted for the required permissions"
            )
        else:
            frappe.throw(f"Failed to delete file from SharePoint: {error_details}")
    except Exception as e:
        error_msg = f"Failed to delete file from SharePoint: {str(e)}"
        frappe.log_error(error_msg, "SharePoint Delete Error")
        frappe.throw(error_msg)

