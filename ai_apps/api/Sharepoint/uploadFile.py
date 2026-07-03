import frappe
import os
import requests
from .sharepoint_auth import get_sharepoint_client

@frappe.whitelist()
def upload_file_to_sharepoint(remote_folder="Tasks", filename=None):
    """
    Upload a file from frontend to SharePoint using Graph API.
    
    Files are automatically routed to type-specific folders based on file extension:
    - Excel files (.xlsx, .xls, .csv, etc.) → Excel folder
    - Images (.jpg, .png, .gif, etc.) → Images folder
    - PDF files (.pdf) → Pdf folder
    - Text files (.txt, .rtf, .md, etc.) → Text folder
    - Videos (.mp4, .avi, .mov, etc.) → Videos folder
    - Word files (.doc, .docx, etc.) → Word folder
    - Other files → Others folder
    
    The file type folder is automatically appended to the remote_folder path.
    Example: remote_folder="Test/Shahid" + file="image.jpg" → "Test/Shahid/Images"
    
    Call this API with the file in the request body (multipart/form-data).
    
    Usage in Postman/Frontend:
    1. Method: POST
    2. URL: /api/method/landwise.api-no.Sharepoint.uploadFile.upload_file_to_sharepoint
    3. Body: form-data
       - Key: "file" (type: File) → Select your file
       - Key: "remote_folder" (type: Text, optional) → Base folder path (e.g., "Test/Shahid")
       - Key: "filename" (type: Text, optional) → Custom filename in SharePoint
    
    Args:
        remote_folder: Base SharePoint folder path (file type folder will be appended automatically)
        filename: Optional filename in SharePoint (defaults to uploaded filename)
    
    Returns:
        dict: Success message with file URL, folder path, and file type folder
    """
    try:
        # Get file from frontend request
        if 'file' not in frappe.request.files:
            frappe.throw("No file provided. Please upload a file in the request (form-data with key 'file')")
        
        uploaded_file = frappe.request.files['file']
        file_content = uploaded_file.stream.read()
        
        # Get filename
        if not filename:
            filename = uploaded_file.filename or "uploaded_file"
        
        # Determine file extension and map to folder
        file_extension = os.path.splitext(filename)[1].lower().lstrip('.')
        
        # Map file extensions to folder names
        extension_to_folder = {
            # Excel files
            'xlsx': 'Excel',
            'xls': 'Excel',
            'xlsm': 'Excel',
            'xlsb': 'Excel',
            'csv': 'Excel',
            # Images
            'jpg': 'Images',
            'jpeg': 'Images',
            'png': 'Images',
            'gif': 'Images',
            'bmp': 'Images',
            'svg': 'Images',
            'webp': 'Images',
            'ico': 'Images',
            'tiff': 'Images',
            'tif': 'Images',
            # PDF files
            'pdf': 'Pdf',
            # Text files
            'txt': 'Text',
            'rtf': 'Text',
            'md': 'Text',
            'log': 'Text',
            # Videos
            'mp4': 'Videos',
            'avi': 'Videos',
            'mov': 'Videos',
            'wmv': 'Videos',
            'flv': 'Videos',
            'mkv': 'Videos',
            'webm': 'Videos',
            'm4v': 'Videos',
            # Word files
            'doc': 'Word',
            'docx': 'Word',
            'docm': 'Word',
            'dot': 'Word',
            'dotx': 'Word',
        }
        
        # Get the appropriate folder based on extension, default to 'Others'
        file_type_folder = extension_to_folder.get(file_extension, 'Others')
        
        # Validate and normalize remote_folder: first letter uppercase, rest lowercase
        if remote_folder:
            remote_folder = remote_folder.strip()
            if remote_folder:
                # Capitalize first letter and make rest lowercase
                remote_folder = remote_folder[0].upper() + remote_folder[1:].lower()
        
        # Append the file type folder to the remote_folder path
        if remote_folder:
            # If remote_folder already ends with a folder, append the file type folder
            final_folder_path = f"Real Estate - US/Novel One/{remote_folder.strip('/')}/{file_type_folder}"
        else:
            # If no remote_folder specified, just use the file type folder
            final_folder_path = file_type_folder
        
        # Get SharePoint client (cached authentication - much more efficient!)
        try:
            client = get_sharepoint_client()
            access_token = client['access_token']
            site_id = client['site_id']
            drive_id = client['drive_id']
            graph_base_url = client['graph_base_url']
            sharepoint_site = client['sharepoint_site']
            
            # Upload file to the specified folder
            folder_path = final_folder_path.strip('/')
            upload_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{folder_path}/{filename}:/content"
            
            upload_headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/octet-stream'
            }
            
            upload_response = requests.put(upload_url, headers=upload_headers, data=file_content)
            upload_response.raise_for_status()
            
            uploaded_file_data = upload_response.json()
            file_url = uploaded_file_data.get('webUrl', f"{sharepoint_site}/{final_folder_path}/{filename}")
        
        except requests.exceptions.HTTPError as http_error:
            error_response = http_error.response
            error_details = ""
            try:
                error_json = error_response.json()
                error_details = error_json.get('error', {}).get('message', str(http_error))
            except:
                error_details = str(http_error)
            
            if error_response.status_code == 401:
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
                frappe.throw(f"Failed to upload file to SharePoint: {error_details}")
        except Exception as api_error:
            error_details = str(api_error)
            frappe.log_error(f"Graph API error: {error_details}", "SharePoint Upload Error")
            frappe.throw(f"Failed to upload file to SharePoint: {error_details}")
        
        frappe.logger().info(f"✅ File uploaded successfully to SharePoint: {file_url}")
        
        return {
            "success": True,
            "message": "File uploaded successfully to SharePoint",
            "file_url": file_url,
            "filename": filename,
            "folder_path": final_folder_path,
            "file_type_folder": file_type_folder
        }
        
    except Exception as e:
        error_msg = f"Failed to upload file to SharePoint: {str(e)}"
        frappe.log_error(error_msg, "SharePoint Upload Error")
        frappe.throw(error_msg)


