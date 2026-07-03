"""
SharePoint Folder Creation API

This module provides functionality to create dynamic folders in SharePoint
for Remodel properties. Folders are created inside:
Real Estate - US > Novel One > Remodel > OnfieldAnalysis

Uses the shared authentication module for efficient API calls.
"""

import frappe
import requests
import re
from .sharepoint_auth import get_sharepoint_client


def sanitize_folder_name(name):
    """
    Sanitize a string to be used as a SharePoint folder name.
    
    SharePoint folder names cannot contain: " * : < > ? / \ |
    Also removes leading/trailing spaces and dots.
    
    Args:
        name: The original folder name
    
    Returns:
        str: Sanitized folder name safe for SharePoint
    """
    if not name:
        return "Unnamed"
    
    # Characters not allowed in SharePoint folder names
    invalid_chars = r'[\"*:<>?/\\|]'
    
    # Replace invalid characters with underscore
    sanitized = re.sub(invalid_chars, '_', str(name))
    
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip(' .')
    
    # Replace multiple consecutive underscores with single underscore
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # Ensure we have a valid name
    if not sanitized:
        return "Unnamed"
    
    return sanitized

def create_single_folder(client, folder_path, folder_name):
    """
    Create a single folder in SharePoint.
    
    Args:
        client: SharePoint client from get_sharepoint_client()
        folder_path: Parent folder path where the new folder will be created
        folder_name: Name of the folder to create
    
    Returns:
        dict: Result with success status and folder details
    """
    site_id = client['site_id']
    drive_id = client['drive_id']
    graph_base_url = client['graph_base_url']
    headers = client['headers']
    
    # Sanitize the folder name
    safe_folder_name = sanitize_folder_name(folder_name)
    
    # Construct the API URL for creating a folder
    # POST /sites/{site-id}/drives/{drive-id}/root:/{parent-path}:/children
    parent_path = folder_path.strip('/')
    create_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{parent_path}:/children"
    
    # Request body for creating a folder
    folder_data = {
        "name": safe_folder_name,
        "folder": {},
        "@microsoft.graph.conflictBehavior": "fail"  # fail if exists - we'll handle the error
    }
    
    try:
        response = requests.post(create_url, headers=headers, json=folder_data)
        response.raise_for_status()
        
        folder_info = response.json()
        return {
            "success": True,
            "folder_name": safe_folder_name,
            "original_name": folder_name,
            "folder_id": folder_info.get('id'),
            "web_url": folder_info.get('webUrl'),
            "created_datetime": folder_info.get('createdDateTime'),
            "already_existed": False
        }
    except requests.exceptions.HTTPError as http_error:
        error_response = http_error.response
        
        # 409 Conflict = folder already exists - treat as success!
        if error_response.status_code == 409:
            return {
                "success": True,
                "folder_name": safe_folder_name,
                "original_name": folder_name,
                "already_existed": True,
                "message": "Folder already exists"
            }
        
        error_details = ""
        try:
            error_json = error_response.json()
            error_details = error_json.get('error', {}).get('message', str(http_error))
        except:
            error_details = str(http_error)
        
        return {
            "success": False,
            "folder_name": safe_folder_name,
            "original_name": folder_name,
            "error": error_details,
            "status_code": error_response.status_code
        }
    except Exception as e:
        return {
            "success": False,
            "folder_name": safe_folder_name,
            "original_name": folder_name,
            "error": str(e)
        }


# @frappe.whitelist()
# def create_property_folders():
#     """DEPRECATED: Use create_doctype_folders() instead.
#     Create folders for all Remodel properties including Images and Videos subfolders"""
#     try:
#         # Get all Remodel properties
#         properties = frappe.get_all('Remodel', fields=['name'])
#         
#         created = 0
#         failed = 0
#         
#         for prop in properties:
#             property_name = prop.name
#             
#             # Create main property folder
#             base_path = f"Real Estate - US/Novel One/Remodel/OnfieldAnalysis/{property_name}"
#             
#             result = create_sharepoint_folder(base_path)
#             
#             if result.get('success'):
#                 # Create Images subfolder
#                 images_path = f"{base_path}/Images"
#                 create_sharepoint_folder(images_path)
#                 
#                 # Create Videos subfolder
#                 videos_path = f"{base_path}/Videos"
#                 create_sharepoint_folder(videos_path)
#                 
#                 created += 1
#             else:
#                 failed += 1
#         
#         return {
#             "success": True,
#             "created": created,
#             "failed": failed
#         }
#     except Exception as e:
#         frappe.log_error(f"Error creating property folders: {str(e)}")
#         return {"success": False, "error": str(e)}


def get_folder_name_from_doc(doc, folder_name_field=None):
    """
    Get the folder name from a document based on field priority.
    
    Args:
        doc: The document dictionary
        folder_name_field: Optional specific field to use
    
    Returns:
        str: The folder name to use
    """
    # If specific field is provided, try to use it
    if folder_name_field and folder_name_field in doc and doc.get(folder_name_field):
        return str(doc.get(folder_name_field))
    
    # Default priority: name > address > title
    priority_fields = ['name', 'address', 'title']
    
    for field in priority_fields:
        if field in doc and doc.get(field):
            return str(doc.get(field))
    
    # Fallback to 'name' which should always exist
    return str(doc.get('name', 'Unnamed'))


@frappe.whitelist()
def create_doctype_folders(doctype, base_path, folder_name_field=None, filters=None, create_subfolders=None):
    """
    Generic function to create SharePoint folders for any doctype.
    
    Folders are created inside: Real Estate - US/Novel One/{base_path}/{folder_name}
    
    Args:
        doctype: The doctype name (e.g., "Remodel", "Project")
        base_path: The subfolder path inside SharePoint (e.g., "Remodel/OnfieldAnalysis", "Projects/Daily Logs")
        folder_name_field: Optional field to use as folder name. If not provided, uses priority: name > address > title
        filters: Optional JSON string or dict of filters (e.g., {"status": "Active"})
        create_subfolders: Optional JSON array of subfolder names to create (e.g., ["Images", "Videos"])
    
    Returns:
        dict: Summary of folder creation results
    
    Usage Examples:
        # For Remodel properties with Images and Videos subfolders
        POST /api/method/landwise.api-no.Sharepoint.create_folder.create_doctype_folders
        Body: {
            "doctype": "Remodel",
            "base_path": "Remodel/OnfieldAnalysis",
            "folder_name_field": "address",
            "filters": {"final_analysis_status": "Need Input Onsite"},
            "create_subfolders": ["Images", "Videos"]
        }
        
        # For Projects with Daily Logs
        POST /api/method/landwise.api-no.Sharepoint.create_folder.create_doctype_folders
        Body: {
            "doctype": "Project",
            "base_path": "Projects/Daily Logs",
            "folder_name_field": "name"
        }
    """
    import json
    
    try:
        # Validate required parameters
        if not doctype:
            frappe.throw("doctype parameter is required")
        if not base_path:
            frappe.throw("base_path parameter is required")
        
        # Parse filters if it's a string
        if filters:
            if isinstance(filters, str):
                filters = json.loads(filters)
        else:
            filters = {}
        
        # Parse create_subfolders if it's a string
        if create_subfolders:
            if isinstance(create_subfolders, str):
                create_subfolders = json.loads(create_subfolders)
        else:
            create_subfolders = []
        
        # Get the doctype meta to check which fields exist
        meta = frappe.get_meta(doctype)
        existing_fields = [df.fieldname for df in meta.fields]
        existing_fields.append('name')  # 'name' is always present
        
        # Determine which fields to fetch (only fields that exist in the doctype)
        fields_to_fetch = ['name']  # name always exists
        
        # If specific folder_name_field is provided, add it if it exists
        if folder_name_field and folder_name_field in existing_fields and folder_name_field not in fields_to_fetch:
            fields_to_fetch.append(folder_name_field)
        
        # Add fallback fields only if they exist in the doctype
        # Priority: name > address > title
        fallback_fields = ['address', 'title']
        for field in fallback_fields:
            if field in existing_fields and field not in fields_to_fetch:
                fields_to_fetch.append(field)
        
        # Get all documents from the doctype
        try:
            documents = frappe.get_all(doctype, filters=filters, fields=fields_to_fetch)
        except Exception as e:
            frappe.throw(f"Error fetching documents from {doctype}: {str(e)}")
        
        if not documents:
            return {
                "success": True,
                "message": f"No documents found in {doctype} with the given filters",
                "doctype": doctype,
                "base_path": base_path,
                "total": 0,
                "created": 0,
                "failed": 0,
                "results": []
            }
        
        # Get SharePoint client (cached authentication)
        client = get_sharepoint_client()
        
        # SharePoint root path (constant)
        sharepoint_root = "Real Estate - US/Novel One"
        
        # Clean up base_path (remove leading/trailing slashes)
        clean_base_path = base_path.strip('/')
        
        # Full parent path
        full_base_path = f"{sharepoint_root}/{clean_base_path}"
        
        created_count = 0
        failed_count = 0
        results = []
        
        for doc in documents:
            # Get the folder name from the document
            folder_name = get_folder_name_from_doc(doc, folder_name_field)
            
            # Create the main folder
            result = create_single_folder(client, full_base_path, folder_name)
            
            if result['success']:
                created_count += 1
                
                # Create subfolders if specified
                if create_subfolders:
                    subfolder_path = f"{full_base_path}/{result['folder_name']}"
                    for subfolder in create_subfolders:
                        subfolder_result = create_single_folder(client, subfolder_path, subfolder)
                        if not subfolder_result['success']:
                            frappe.logger().warning(
                                f"Failed to create subfolder {subfolder} for {folder_name}: {subfolder_result.get('error')}"
                            )
                
                result['subfolders_created'] = create_subfolders
                frappe.logger().info(f"✅ Created SharePoint folder: {result['folder_name']}")
            else:
                failed_count += 1
                frappe.logger().warning(f"❌ Failed to create folder for: {folder_name} - {result.get('error')}")
            
            results.append(result)
        
        return {
            "success": True,
            "message": f"Folder creation completed. Created: {created_count}, Failed: {failed_count}",
            "doctype": doctype,
            "base_path": full_base_path,
            "total": len(documents),
            "created": created_count,
            "failed": failed_count,
            "results": results
        }
        
    except json.JSONDecodeError as e:
        frappe.throw(f"Invalid JSON format: {str(e)}")
    except Exception as e:
        error_msg = f"Failed to create folders for {doctype}: {str(e)}"
        frappe.log_error(error_msg, "SharePoint Create Doctype Folders Error")
        frappe.throw(error_msg)

def create_sharepoint_folder(folder_path):
    """Create a single folder in SharePoint (skip if already exists)"""
    try:
        # Get SharePoint client
        client = get_sharepoint_client()
        
        # Split the path to get parent path and folder name
        path_parts = folder_path.rstrip('/').rsplit('/', 1)
        if len(path_parts) == 2:
            parent_path = path_parts[0]
            folder_name = path_parts[1]
        else:
            parent_path = ""
            folder_name = path_parts[0]
        
        # Use the existing create_single_folder function
        result = create_single_folder(client, parent_path, folder_name)
        
        return result
    except Exception as e:
        frappe.log_error(f"Error creating SharePoint folder {folder_path}: {str(e)}")
        # If folder already exists, that's okay
        if "already exists" in str(e).lower() or "409" in str(e):
            return {"success": True, "path": folder_path, "message": "Folder already exists"}
        return {"success": False, "error": str(e)}

@frappe.whitelist(allow_guest=True)
def create_folder_for_property(property_name):
    """
    Create a single folder in SharePoint for a specific property.
    
    Folder is created inside: Real Estate - US/Novel One/Remodel/OnfieldAnalysis
    
    Args:
        property_name: The property address/name to create a folder for
    
    Returns:
        dict: Result with success status and folder details
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.create_folder.create_folder_for_property
        Body: {"property_name": "123 Main Street, Houston, TX"}
    """
    try:
        if not property_name:
            frappe.throw("property_name parameter is required")
        
        # Get SharePoint client (cached authentication)
        client = get_sharepoint_client()
        
        # Base path for folders
        base_path = "Real Estate - US/Novel One/Remodel/OnfieldAnalysis"
        
        # Create the folder
        result = create_single_folder(client, base_path, property_name)
        
        if result['success']:
            frappe.logger().info(f"✅ Created SharePoint folder: {result['folder_name']}")
            return {
                "success": True,
                "message": f"Folder '{result['folder_name']}' created successfully",
                "base_path": base_path,
                "folder_name": result['folder_name'],
                "original_name": result['original_name'],
                "web_url": result.get('web_url'),
                "folder_id": result.get('folder_id')
            }
        else:
            frappe.throw(f"Failed to create folder: {result.get('error')}")
            
    except Exception as e:
        error_msg = f"Failed to create folder for property: {str(e)}"
        frappe.log_error(error_msg, "SharePoint Create Folder Error")
        frappe.throw(error_msg)


@frappe.whitelist(allow_guest=True)
def create_folders_for_properties(property_names):
    """
    Create folders in SharePoint for a list of specific properties.
    
    Folders are created inside: Real Estate - US/Novel One/Remodel/OnfieldAnalysis
    
    Args:
        property_names: JSON array of property addresses/names to create folders for
                       e.g., ["123 Main St", "456 Oak Ave"]
    
    Returns:
        dict: Summary of folder creation results with success/failure counts
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.create_folder.create_folders_for_properties
        Body: {"property_names": ["123 Main Street", "456 Oak Avenue"]}
    """
    try:
        import json
        
        # Parse property_names if it's a string
        if isinstance(property_names, str):
            property_names = json.loads(property_names)
        
        if not property_names or not isinstance(property_names, list):
            frappe.throw("property_names must be a non-empty list of property names")
        
        # Get SharePoint client (cached authentication)
        client = get_sharepoint_client()
        
        # Base path for folders
        base_path = "Real Estate - US/Novel One/Remodel/OnfieldAnalysis"
        
        results = []
        created_count = 0
        failed_count = 0
        
        for property_name in property_names:
            if not property_name:
                results.append({
                    "success": False,
                    "folder_name": None,
                    "original_name": property_name,
                    "error": "Empty property name"
                })
                failed_count += 1
                continue
            
            # Create folder for this property
            result = create_single_folder(client, base_path, property_name)
            results.append(result)
            
            if result['success']:
                created_count += 1
                frappe.logger().info(f"✅ Created SharePoint folder: {result['folder_name']}")
            else:
                failed_count += 1
                frappe.logger().warning(f"❌ Failed to create folder for: {property_name} - {result.get('error')}")
        
        return {
            "success": True,
            "message": f"Folder creation completed. Created: {created_count}, Failed: {failed_count}",
            "base_path": base_path,
            "total": len(property_names),
            "created": created_count,
            "failed": failed_count,
            "results": results
        }
        
    except json.JSONDecodeError as e:
        frappe.throw(f"Invalid JSON format for property_names: {str(e)}")
    except Exception as e:
        error_msg = f"Failed to create property folders: {str(e)}"
        frappe.log_error(error_msg, "SharePoint Create Folders Error")
        frappe.throw(error_msg)
