"""
SharePoint Folder Documents API

This module provides APIs to fetch documents from SharePoint folders based on:
- Project
- Folder Type (Daily Logs, Bids, Purchase Orders, Purchase Invoices)

It returns photos, videos, PDFs, and other documents stored in SharePoint.
"""

import frappe
import requests
from .sharepoint_auth import get_sharepoint_client
from urllib.parse import unquote
import mimetypes


@frappe.whitelist()
def get_folder_documents(project, folder_type):
    # frappe.msgprint(f"get_folder_documents project: {project}, type: {folder_type}")
    try:
        if not project:
            frappe.throw("Project parameter is required")
        
        if not folder_type:
            frappe.throw("Folder type parameter is required")
        
        # Validate folder type
        valid_folder_types = ["daily_logs", "bids", "purchase_order", "purchase_invoice", "rfq"]
        if folder_type not in valid_folder_types:
            frappe.throw(f"Invalid folder_type. Must be one of: {', '.join(valid_folder_types)}")
        
        # Check if project exists or if it's a project_name
        project_id = project
        if not frappe.db.exists("Project", project):
            # Try searching by project_name
            p_id = frappe.db.get_value("Project", {"project_name": project}, "name")
            if p_id:
                project_id = p_id
            else:
                frappe.throw(f"Project {project} not found")
        
        # Use project_id from here on
        project = project_id
        
        # Get project name for folder structure
        project_name = frappe.db.get_value("Project", project, "project_name") or project
        
        # Map folder type to SharePoint folder path
        folder_mapping = {
            "daily_logs": f"Projects/{project_name}/Daily Logs",
            "bids": f"Projects/{project_name}/Bids",
            "purchase_order": f"Projects/{project_name}/Purchase Orders",
            "purchase_invoice": f"Projects/{project_name}/Purchase Invoices",
            "rfq": f"Projects/{project_name}/RFQs"
        }
        
        relative_folder_path = folder_mapping[folder_type]
        full_folder_path = f"Real Estate - US/Novel One/{relative_folder_path}"
        
        # Initialize response
        response_data = {
            "success": True,
            "project": project,
            "folder_type": folder_type,
            "frappe_records": [],
            "documents": [],
            "total": 0,
            "folder_path": full_folder_path
        }
        
        # Fetch Frappe records for specific folder types
        if folder_type in ["bids", "rfq"]:
            response_data["frappe_records"] = get_bids_from_frappe(project)
        elif folder_type == "purchase_order":
            response_data["frappe_records"] = get_purchase_orders_from_frappe(project)
        elif folder_type == "purchase_invoice":
            response_data["frappe_records"] = get_purchase_invoices_from_frappe(project)
        
        # Fetch SharePoint documents
        sharepoint_docs = get_sharepoint_documents(full_folder_path)
        
        # Enrich SharePoint docs with uploaded_by from Frappe
        links_meta = get_all_sharepoint_links_with_meta(project)
        for doc in sharepoint_docs:
            web_url = doc.get("web_url")
            download_url = doc.get("download_url")
            
            # Try to match by web_url first, then download_url
            user = links_meta.get(web_url) or (links_meta.get(download_url) if download_url else None)
            
            if user:
                doc["created_by"] = user
        
        response_data["documents"] = sharepoint_docs
        response_data["total"] = len(response_data["frappe_records"]) + len(sharepoint_docs)
        
        return response_data
        
    except requests.exceptions.HTTPError as http_error:
        error_response = http_error.response
        error_details = ""
        try:
            error_json = error_response.json()
            error_details = error_json.get('error', {}).get('message', str(http_error))
        except:
            error_details = str(http_error)
        
        frappe.log_error(frappe.get_traceback(), "SharePoint Folder Documents Error")
        return {
            "success": False,
            "error": error_details,
            "project": project,
            "folder_type": folder_type,
            "frappe_records": [],
            "documents": [],
            "total": 0
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "SharePoint Folder Documents Error")
        return {
            "success": False,
            "error": str(e),
            "project": project,
            "folder_type": folder_type,
            "frappe_records": [],
            "documents": [],
            "total": 0
        }


def get_all_sharepoint_links_with_meta(project):
    """
    Fetch all SharePoint links associated with this project across multiple doctypes
    to get the 'uploaded_by' metadata.
    """
    links_meta = {}
    
    # Doctypes that use 'sharepoint child Task'
    doctypes_to_check = [
        {"doctype": "Daily Logs", "parent_field": "project"},
        {"doctype": "Project Bids", "parent_field": "project"},
        {"doctype": "Purchase Order", "parent_field": "project"},
        {"doctype": "Purchase Invoice", "parent_field": "project"},
    ]
    
    for dt_info in doctypes_to_check:
        dt = dt_info["doctype"]
        field = dt_info["parent_field"]
        
        try:
            # Check if doctype exists
            if not frappe.db.exists("DocType", dt):
                continue
                
            parents = frappe.get_all(dt, filters={field: project}, pluck="name")
            if not parents:
                continue
                
            links = frappe.get_all(
                "sharepoint child Task",
                filters={"parent": ["in", parents], "parenttype": dt},
                fields=["sharepoint_link", "uploaded_by"]
            )
            
            for l in links:
                if l.sharepoint_link:
                    user_name = l.uploaded_by
                    if user_name:
                        # Get full name for display
                        full_name = frappe.db.get_value("User", user_name, "full_name")
                        links_meta[l.sharepoint_link] = full_name or user_name
        except Exception:
            # Silently skip errors for individual doctypes
            pass
            
    return links_meta




def extract_project_from_filename(filename):
    """
    Extract project name from filename.
    Example: "Estimate_Items_PROJ-0008 (1).xlsx" -> "PROJ-0008"
    """
    import re
    if not filename:
        return None
    
    # Pattern to match project format: PROJ-XXXX or PROJECT-XXXX
    pattern = r'(PROJ(?:ECT)?-\d+)'
    match = re.search(pattern, filename, re.IGNORECASE)
    
    if match:
        return match.group(1).upper()
    return None


def get_bids_from_frappe(project):
    """Fetch bid-related files from File Manager for a project."""
    try:
        # Get all Project Bids for this project to get their names
        bids = frappe.get_all(
            "Project Bids",
            filters={"project": project},
            fields=["name"],
            pluck="name",
            limit_page_length=0
        )
        
        if not bids:
            return []
        
        # Get files attached to these bid documents
        files = frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": "Project Bids",
                "attached_to_name": ["in", bids]
            },
            fields=[
                "name", 
                "file_name", 
                "file_url", 
                "file_size", 
                "file_type",
                "is_private",
                "is_folder",
                "modified", 
                "attached_to_name", 
                "attached_to_doctype",
                "content_hash",
                "uploaded_to_dropbox",
                "uploaded_to_google_drive",
                "owner"
            ],
            order_by="modified desc",
            limit_page_length=0
        )
        
        # Format files for display
        formatted_files = []
        for file in files:
            # Extract project from filename (for display/debug)
            filename = file.get("file_name", "")
            file_project = extract_project_from_filename(filename)
            
            # Derive type and extension
            extension = get_file_extension(filename)
            file_type = categorize_file_type(extension)
            
            # Get bid details
            bid_details = frappe.db.get_value(
                "Project Bids",
                file.get("attached_to_name"),
                ["title", "status"],
                as_dict=True
            ) or {}
            
            file_url = file.get("file_url")
            
            formatted_files.append({
                # 'name' = display filename (used by UI), 'frappe_doc_name' = Frappe File docname (used for deletion)
                "name": filename,
                "frappe_doc_name": file.get("name"),  # Fix 1: real Frappe File docname e.g. "File-00123"
                "file_name": filename,
                "file_url": file_url,
                "web_url": file_url,
                "download_url": file_url,
                "thumbnail_url": file_url if file_type == "image" else None,
                "size": file.get("file_size", 0),
                "file_size": file.get("file_size", 0),
                "type": file_type,
                "file_type": file.get("file_type"),
                "extension": extension,
                "is_private": file.get("is_private"),
                "is_folder": file.get("is_folder"),
                "modified": file.get("modified"),
                "attached_to_doctype": file.get("attached_to_doctype"),
                "attached_to_name": file.get("attached_to_name"),
                "content_hash": file.get("content_hash"),
                "uploaded_to_dropbox": file.get("uploaded_to_dropbox"),
                "uploaded_to_google_drive": file.get("uploaded_to_google_drive"),
                "created_by": frappe.db.get_value("User", file.get("owner"), "full_name") or file.get("owner"),
                "source": "frappe",
                "attached_to": file.get("attached_to_name"),
                "display_name": f"{bid_details.get('title', file.get('attached_to_name'))} - {filename}",
                "status": bid_details.get("status"),
                "bid_title": bid_details.get("title"),
                "extracted_project": file_project
            })
        
        return formatted_files
    except Exception as e:
        frappe.logger().error(f"Error fetching bid files: {str(e)}")
        return []


def get_vendor_responses_from_frappe(project):
    """Fetch Bid Response attachments from File Manager for a project.

    Bid Response has a direct 'project' field, so we filter directly.
    """
    try:
        # Get all Bid Response names for this project directly
        response_names = frappe.get_all(
            "Bid Response",
            filters={"project": project},
            fields=["name", "supplier_info", "bid_package_link"],
            limit_page_length=0
        )
        if not response_names:
            return []

        # Build a quick lookup: response_name -> {supplier_info, bid_package_link}
        response_meta = {r["name"]: r for r in response_names}
        rnames = list(response_meta.keys())

        # Get all File records attached to these Bid Responses
        files = frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": "Bid Response",
                "attached_to_name": ["in", rnames]
            },
            fields=[
                "name",
                "file_name",
                "file_url",
                "file_size",
                "file_type",
                "is_private",
                "is_folder",
                "modified",
                "attached_to_name",
                "attached_to_doctype",
                "content_hash",
                "uploaded_to_dropbox",
                "uploaded_to_google_drive",
                "owner"
            ],
            order_by="modified desc",
            limit_page_length=0
        )

        # Cache bid titles to avoid repeated DB calls
        bid_title_cache = {}

        formatted_files = []
        for file in files:
            filename = file.get("file_name", "")
            file_project = extract_project_from_filename(filename)
            extension = get_file_extension(filename)
            file_type = categorize_file_type(extension)

            attached_to = file.get("attached_to_name", "")
            meta = response_meta.get(attached_to, {})
            supplier_info = meta.get("supplier_info") or ""
            bid_pkg = meta.get("bid_package_link") or ""

            # Get supplier display name
            supplier_display = supplier_info
            if supplier_info:
                supplier_display = frappe.db.get_value("Supplier", supplier_info, "supplier_name") or supplier_info

            # Get bid title (cached)
            bid_title = ""
            if bid_pkg:
                if bid_pkg not in bid_title_cache:
                    bid_title_cache[bid_pkg] = frappe.db.get_value("Project Bids", bid_pkg, "title") or ""
                bid_title = bid_title_cache[bid_pkg]

            file_url = file.get("file_url")

            formatted_files.append({
                "name": filename,
                "frappe_doc_name": file.get("name"),
                "file_name": filename,
                "file_url": file_url,
                "web_url": file_url,
                "download_url": file_url,
                "thumbnail_url": file_url if file_type == "image" else None,
                "size": file.get("file_size", 0),
                "file_size": file.get("file_size", 0),
                "type": file_type,
                "file_type": file.get("file_type"),
                "extension": extension,
                "is_private": file.get("is_private"),
                "is_folder": file.get("is_folder"),
                "modified": file.get("modified"),
                "attached_to_doctype": file.get("attached_to_doctype"),
                "attached_to_name": attached_to,
                "content_hash": file.get("content_hash"),
                "uploaded_to_dropbox": file.get("uploaded_to_dropbox"),
                "uploaded_to_google_drive": file.get("uploaded_to_google_drive"),
                "created_by": frappe.db.get_value("User", file.get("owner"), "full_name") or file.get("owner"),
                "source": "frappe",
                "attached_to": attached_to,
                "display_name": f"{supplier_display} - {filename}" if supplier_display else filename,
                "supplier": supplier_display,
                "bid_title": bid_title,
                "extracted_project": file_project
            })

        return formatted_files
    except Exception as e:
        frappe.logger().error(f"Error fetching vendor response files: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Get Vendor Response Files Error")
        return []



def get_purchase_orders_from_frappe(project):
    """Fetch purchase order files from File Manager for a project."""
    try:
        # Get all Purchase Orders for this project
        purchase_orders = frappe.get_all(
            "Purchase Order",
            filters={"project": project},
            fields=["name"],
            pluck="name",
            limit_page_length=0
        )
        
        if not purchase_orders:
            return []
        
        # Get files attached to these PO documents
        files = frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": "Purchase Order",
                "attached_to_name": ["in", purchase_orders]
            },
            fields=[
                "name", 
                "file_name", 
                "file_url", 
                "file_size", 
                "file_type",
                "is_private",
                "is_folder",
                "modified", 
                "attached_to_name", 
                "attached_to_doctype",
                "content_hash",
                "uploaded_to_dropbox",
                "uploaded_to_google_drive",
                "owner"
            ],
            order_by="modified desc",
            limit_page_length=0
        )
        
        # Format files for display
        formatted_files = []
        for file in files:
            # Extract project from filename (for display/debug)
            file_project = extract_project_from_filename(file.get("file_name"))
            
            # Get PO details
            po_details = frappe.db.get_value(
                "Purchase Order",
                file.get("attached_to_name"),
                ["supplier", "status", "transaction_date", "grand_total", "docstatus"],
                as_dict=True
            ) or {}
            
            formatted_files.append({
                "name": file.get("name"),
                "file_name": file.get("file_name"),
                "file_url": file.get("file_url"),
                "size": file.get("file_size", 0),
                "file_size": file.get("file_size", 0),
                "file_type": file.get("file_type"),
                "is_private": file.get("is_private"),
                "is_folder": file.get("is_folder"),
                "modified": file.get("modified"),
                "attached_to_doctype": file.get("attached_to_doctype"),
                "attached_to_name": file.get("attached_to_name"),
                "content_hash": file.get("content_hash"),
                "uploaded_to_dropbox": file.get("uploaded_to_dropbox"),
                "uploaded_to_google_drive": file.get("uploaded_to_google_drive"),
                "created_by": frappe.db.get_value("User", file.get("owner"), "full_name") or file.get("owner"),
                "source": "frappe",
                "type": "purchase_order",
                "attached_to": file.get("attached_to_name"),
                "display_name": f"{file.get('attached_to_name')} - {file.get('file_name')}",
                "status": po_details.get("status"),
                "supplier": po_details.get("supplier"),
                "transaction_date": str(po_details.get("transaction_date")) if po_details.get("transaction_date") else None,
                "grand_total": po_details.get("grand_total"),
                "docstatus": po_details.get("docstatus"),
                "extracted_project": file_project  # Add extracted project for debugging
            })
        
        return formatted_files
    except Exception as e:
        frappe.logger().error(f"Error fetching purchase order files: {str(e)}")
        return []


def get_purchase_invoices_from_frappe(project):
    """Fetch purchase invoice files from File Manager for a project."""
    try:
        # Get all Purchase Invoices for this project
        purchase_invoices = frappe.get_all(
            "Purchase Invoice",
            filters={"project": project},
            fields=["name"],
            pluck="name",
            limit_page_length=0
        )
        
        if not purchase_invoices:
            return []
        
        # Get files attached to these PI documents
        files = frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": "Purchase Invoice",
                "attached_to_name": ["in", purchase_invoices]
            },
            fields=[
                "name", 
                "file_name", 
                "file_url", 
                "file_size", 
                "file_type",
                "is_private",
                "is_folder",
                "modified", 
                "attached_to_name", 
                "attached_to_doctype",
                "content_hash",
                "uploaded_to_dropbox",
                "uploaded_to_google_drive",
                "owner"
            ],
            order_by="modified desc",
            limit_page_length=0
        )
        
        # Format files for display
        formatted_files = []
        for file in files:
            # Extract project from filename (for display/debug)
            file_project = extract_project_from_filename(file.get("file_name"))
            
            # Get PI details
            pi_details = frappe.db.get_value(
                "Purchase Invoice",
                file.get("attached_to_name"),
                ["supplier", "status", "posting_date", "grand_total", "docstatus"],
                as_dict=True
            ) or {}
            
            formatted_files.append({
                "name": file.get("name"),
                "file_name": file.get("file_name"),
                "file_url": file.get("file_url"),
                "size": file.get("file_size", 0),
                "file_size": file.get("file_size", 0),
                "file_type": file.get("file_type"),
                "is_private": file.get("is_private"),
                "is_folder": file.get("is_folder"),
                "modified": file.get("modified"),
                "attached_to_doctype": file.get("attached_to_doctype"),
                "attached_to_name": file.get("attached_to_name"),
                "content_hash": file.get("content_hash"),
                "uploaded_to_dropbox": file.get("uploaded_to_dropbox"),
                "uploaded_to_google_drive": file.get("uploaded_to_google_drive"),
                "created_by": frappe.db.get_value("User", file.get("owner"), "full_name") or file.get("owner"),
                "source": "frappe",
                "type": "purchase_invoice",
                "attached_to": file.get("attached_to_name"),
                "display_name": f"{file.get('attached_to_name')} - {file.get('file_name')}",
                "status": pi_details.get("status"),
                "supplier": pi_details.get("supplier"),
                "posting_date": str(pi_details.get("posting_date")) if pi_details.get("posting_date") else None,
                "grand_total": pi_details.get("grand_total"),
                "docstatus": pi_details.get("docstatus"),
                "extracted_project": file_project  # Add extracted project for debugging
            })
        
        return formatted_files
    except Exception as e:
        frappe.logger().error(f"Error fetching purchase invoice files: {str(e)}")
        return []


def get_sharepoint_documents(full_folder_path):
    """Fetch documents from SharePoint."""
    try:
        # Get SharePoint client
        client = get_sharepoint_client()
        access_token = client['access_token']
        site_id = client['site_id']
        drive_id = client['drive_id']
        graph_base_url = client['graph_base_url']
        
        # Encode folder path to handle spaces and special characters
        from urllib.parse import quote
        encoded_path = quote(full_folder_path)
        
        # Get folder contents
        # Get folder contents using fallback strategies
        items_data = None
        headers = {'Authorization': f'Bearer {access_token}'}
        base_url_encoded = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/children"

        try:
            # Strategy 1: Expand Title (Preferred)
            folder_url = f"{base_url_encoded}?expand=fields(select=Title)"
            response = requests.get(folder_url, headers=headers)
            response.raise_for_status()
            items_data = response.json()
        except Exception as e1:
            # Strategy 2: Expand All Fields (Fallback if select=Title fails)
            try:
                folder_url = f"{base_url_encoded}?expand=fields"
                response = requests.get(folder_url, headers=headers)
                response.raise_for_status()
                items_data = response.json()
            except Exception as e2:
                # Strategy 3: Basic Query (No metadata, minimal failure chance)
                try:
                    folder_url = base_url_encoded
                    response = requests.get(folder_url, headers=headers)
                    
                    if response.status_code == 404:
                        return []
                    
                    response.raise_for_status()
                    items_data = response.json()
                except Exception as e3:
                    frappe.log_error(title="SharePoint Fetch Error", message=f"All strategies failed. Last error: {str(e3)}")
                    return []
        
        documents = []
        items = items_data.get("value", [])
        
        for item in items:
            # Skip folders, only process files
            if "folder" in item:
                continue
            
            filename = item.get("name", "")
            extension = get_file_extension(filename)
            file_type = categorize_file_type(extension)
            
            # Get thumbnail URL for images/videos
            thumbnail_url = None
            if file_type in ["image", "video", "pdf"]:
                thumbnail_url = get_thumbnail_url(item, access_token)
            
            doc = {
                "name": filename,
                "title": item.get("fields", {}).get("Title"),
                "type": file_type,
                "size": item.get("size", 0),
                "web_url": item.get("webUrl"),
                "download_url": item.get("@microsoft.graph.downloadUrl"),
                "thumbnail_url": thumbnail_url,
                "modified": item.get("lastModifiedDateTime"),
                "file_id": item.get("id"),
                "extension": extension,
                "source": "sharepoint",
                "created": item.get("createdDateTime"),
                "created_by": item.get("createdBy", {}).get("user", {}).get("displayName", "Unknown")
            }
            
            documents.append(doc)
        
        # Sort by modified date (newest first)
        documents.sort(key=lambda x: x.get("modified", ""), reverse=True)
        
        return documents
        
    except Exception as e:
        frappe.logger().error(f"Error fetching SharePoint documents: {str(e)}")
        return []


def get_file_extension(filename):
    """Extract file extension from filename."""
    if not filename or "." not in filename:
        return ""
    return f".{filename.rsplit('.', 1)[-1].lower()}"


def categorize_file_type(extension):
    """Categorize file by extension."""
    extension = extension.lower()
    
    image_extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"]
    video_extensions = [".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm"]
    pdf_extensions = [".pdf"]
    document_extensions = [".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".odt", ".ods", ".odp"]
    
    if extension in image_extensions:
        return "image"
    elif extension in video_extensions:
        return "video"
    elif extension in pdf_extensions:
        return "pdf"
    elif extension in document_extensions:
        return "document"
    else:
        return "other"


def get_thumbnail_url(item, access_token):
    """Get thumbnail URL for an item if available."""
    try:
        # Get thumbnails from item metadata
        if "thumbnails" in item and len(item["thumbnails"]) > 0:
            thumbnails = item["thumbnails"][0]
            # Try to get large thumbnail, fallback to medium, then small
            for size in ["large", "medium", "small"]:
                if size in thumbnails:
                    return thumbnails[size].get("url")
        
        # Fallback: use download URL
        return item.get("@microsoft.graph.downloadUrl")
        
    except Exception as e:
        frappe.logger().warning(f"Failed to get thumbnail: {str(e)}")
        return item.get("@microsoft.graph.downloadUrl")


@frappe.whitelist()
def get_project_folders(project):
    """
    List all folders inside a project's SharePoint directory.

    Splits results into:
    - default_folders: matching the known system folder names (blue)
    - custom_folders: everything else created by users (yellow)

    Args:
        project: Frappe Project name (e.g., "PROJ-0001")

    Returns:
        dict: {
            "success": True,
            "default_folders": [...],
            "custom_folders": [...],
        }
    """
    try:
        if not project:
            frappe.throw("project parameter is required")

        # Resolve project_name
        project_name = frappe.db.get_value("Project", project, "project_name") or project

        client = get_sharepoint_client()
        site_id = client["site_id"]
        drive_id = client["drive_id"]
        graph_base_url = client["graph_base_url"]
        headers = client["headers"]

        # Known default folder names (as they appear in SharePoint)
        DEFAULT_FOLDERS = {"Daily Logs", "RFQs", "Selections", "Purchase Orders", "Purchase Invoices", "Change Orders", "Bills"}

        folder_path = f"Real Estate - US/Novel One/Projects/{project_name}"
        from urllib.parse import quote
        encoded_path = quote(folder_path)
        list_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/children?$select=id,name,folder,webUrl,createdDateTime,lastModifiedDateTime"

        response = requests.get(list_url, headers=headers)

        # If project folder does not exist yet, return empty lists
        if response.status_code == 404:
            return {"success": True, "default_folders": [], "custom_folders": []}

        response.raise_for_status()
        data = response.json()

        # Count actual bid files from Frappe for the Bids virtual folder
        bid_names = frappe.get_all(
            "Project Bids",
            filters={"project": project},
            pluck="name",
            limit_page_length=0
        )
        bids_file_count = frappe.db.count(
            "File",
            filters={
                "attached_to_doctype": "Project Bids",
                "attached_to_name": ["in", bid_names] if bid_names else ["in", ["__none__"]]
            }
        ) if bid_names else 0

        # Count Bid Response attachments for the Vendors virtual folder
        # Bid Response has a direct 'project' field — no multi-hop needed
        vendor_response_names = frappe.get_all(
            "Bid Response",
            filters={"project": project},
            pluck="name",
            limit_page_length=0
        )
        vendors_file_count = frappe.db.count(
            "File",
            filters={
                "attached_to_doctype": "Bid Response",
                "attached_to_name": ["in", vendor_response_names]
            }
        ) if vendor_response_names else 0


        default_folders = [
            {
                "id": "virtual-bids",
                "name": "Bids",
                "web_url": None,
                "created": None,
                "modified": None,
                "child_count": bids_file_count,
                "source": "frappe"
            },
            {
                "id": "virtual-vendors",
                "name": "Vendors",
                "web_url": None,
                "created": None,
                "modified": None,
                "child_count": vendors_file_count,
                "source": "frappe"
            }
        ]
        custom_folders = []

        for item in data.get("value", []):
            if "folder" not in item:
                continue  # skip files, only folders

            folder_info = {
                "id": item.get("id"),
                "name": item.get("name"),
                "web_url": item.get("webUrl"),
                "created": item.get("createdDateTime"),
                "modified": item.get("lastModifiedDateTime"),
                "child_count": item.get("folder", {}).get("childCount", 0),
            }

            if item.get("name") in DEFAULT_FOLDERS:
                default_folders.append(folder_info)
            else:
                custom_folders.append(folder_info)

        return {
            "success": True,
            "project": project,
            "project_name": project_name,
            "default_folders": default_folders,
            "custom_folders": custom_folders,
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Project Folders Error")
        return {"success": False, "error": str(e), "default_folders": [], "custom_folders": []}


@frappe.whitelist()
def create_project_custom_folder(project, folder_name, parent_folder_path=None):
    """
    Create a custom (yellow) folder inside a project's SharePoint directory.

    Can also create sub-folders inside existing custom folders by passing
    parent_folder_path (relative to the project root, e.g., "My Folder").

    Args:
        project: Frappe Project name
        folder_name: Name of the new folder (user-provided)
        parent_folder_path: Optional. Relative path of parent custom folder
                            e.g., "My Folder" creates inside Projects/{project_name}/My Folder/

    Returns:
        dict: { "success": True, "folder_name": ..., "sharepoint_path": ..., "web_url": ... }
    """
    try:
        if not project:
            frappe.throw("project parameter is required")
        if not folder_name or not folder_name.strip():
            frappe.throw("folder_name parameter is required")

        # Resolve project_name
        project_name = frappe.db.get_value("Project", project, "project_name") or project

        client = get_sharepoint_client()

        # Build the parent path in SharePoint
        if parent_folder_path:
            parent_folder_path = parent_folder_path.strip("/")
            base_path = f"Real Estate - US/Novel One/Projects/{project_name}/{parent_folder_path}"
        else:
            base_path = f"Real Estate - US/Novel One/Projects/{project_name}"

        # Reuse the existing create_single_folder helper
        from .create_folder import create_single_folder, sanitize_folder_name

        result = create_single_folder(client, base_path, folder_name)

        if result.get("success"):
            safe_name = result.get("folder_name", sanitize_folder_name(folder_name))
            relative_path = f"{parent_folder_path}/{safe_name}" if parent_folder_path else safe_name

            return {
                "success": True,
                "folder_name": safe_name,
                "original_name": folder_name,
                "sharepoint_path": f"Projects/{project_name}/{relative_path}",
                "web_url": result.get("web_url"),
                "already_existed": result.get("already_existed", False),
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Failed to create folder"),
            }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Project Custom Folder Error")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_folder_files(project, folder_path, page_size=20, skip_token=None):
    """
    Fetch files from a SharePoint folder with cursor-based pagination.

    Works for both default and custom folders. For the 'Bids' folder,
    also fetches Frappe File Manager records attached to Project Bids.

    Args:
        project: Frappe Project name
        folder_path: Relative SharePoint path from project root
                     e.g., "Daily Logs" or "My Custom Folder" or "My Folder/Sub Folder"
        page_size: Number of items per page (default 20)
        skip_token: Cursor token from previous response for next page

    Returns:
        dict: {
            "success": True,
            "files": [...],            # SharePoint files
            "frappe_records": [...],   # Only for Bids folder
            "has_more": True/False,
            "next_token": "...",       # Pass this back for next page
            "total_fetched": N,
        }
    """
    try:
        if not project:
            frappe.throw("project parameter is required")
        if not folder_path:
            frappe.throw("folder_path parameter is required")

        page_size = int(page_size) if page_size else 20

        # Resolve project_name
        project_name = frappe.db.get_value("Project", project, "project_name") or project

        client = get_sharepoint_client()
        site_id = client["site_id"]
        drive_id = client["drive_id"]
        graph_base_url = client["graph_base_url"]
        headers = client["headers"]

        # Build full SharePoint path
        # Strip spaces from every segment so "My Folder  " matches the folder
        # as stored in SharePoint (sanitize_folder_name strips spaces on creation)
        folder_path = "/".join(seg.strip() for seg in folder_path.strip("/").split("/") if seg.strip())
        full_path = f"Real Estate - US/Novel One/Projects/{project_name}/{folder_path}"


        from urllib.parse import quote
        encoded_path = quote(full_path)

        # Build paginated URL — include thumbnails in expand so get_thumbnail_url works without extra calls
        base_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/children"

        if skip_token:
            list_url = f"{base_url}?$top={page_size}&$skiptoken={skip_token}&expand=thumbnails"
        else:
            list_url = f"{base_url}?$top={page_size}&expand=thumbnails"


        # RFQ: SharePoint only (frappe_records stays empty)
        # Bids / Vendors: Frappe File doctype only — short-circuit before SP request
        frappe_records = []
        folder_path_lower = folder_path.lower()

        if folder_path_lower == "bids" and not skip_token:
            frappe_records = get_bids_from_frappe(project)
            return {
                "success": True,
                "files": [],
                "folders": [],
                "frappe_records": frappe_records,
                "has_more": False,
                "next_token": None,
                "total_fetched": len(frappe_records),
            }

        if folder_path_lower == "vendors" and not skip_token:
            frappe_records = get_vendor_responses_from_frappe(project)
            return {
                "success": True,
                "files": [],
                "folders": [],
                "frappe_records": frappe_records,
                "has_more": False,
                "next_token": None,
                "total_fetched": len(frappe_records),
            }

        response = requests.get(list_url, headers=headers)

        if response.status_code == 404:
            return {
                "success": True,
                "files": [],
                "frappe_records": [],
                "has_more": False,
                "next_token": None,
                "total_fetched": 0,
            }

        response.raise_for_status()
        data = response.json()

        # Extract next page token from @odata.nextLink
        next_link = data.get("@odata.nextLink", "")
        next_token = None
        has_more = False
        if next_link:
            has_more = True
            # Extract skipToken from nextLink URL
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(next_link)
            qs = parse_qs(parsed.query)
            next_token = qs.get("$skipToken", [None])[0] or qs.get("$skiptoken", [None])[0]
            if not next_token:
                # Fallback: check all keys case-insensitively if needed
                for k, v in qs.items():
                    if k.lower() == "$skiptoken":
                        next_token = v[0]
                        break

        # Process files and folders separately
        # Folders go into their own list so they don't count against page_size
        folders = []
        files = []
        for item in data.get("value", []):
            if "folder" in item:
                folders.append({
                    "name": item.get("name"),
                    "id": item.get("id"),
                    "type": "folder",
                    "web_url": item.get("webUrl"),
                    "created": item.get("createdDateTime"),
                    "modified": item.get("lastModifiedDateTime"),
                    "child_count": item.get("folder", {}).get("childCount", 0),
                    "source": "sharepoint",
                })
                continue

            filename = item.get("name", "")
            extension = get_file_extension(filename)
            file_type = categorize_file_type(extension)

            thumbnail_url = None
            if file_type in ["image", "video", "pdf"]:
                thumbnail_url = get_thumbnail_url(item, client["access_token"])

            files.append({
                "name": filename,
                "title": item.get("fields", {}).get("Title"),
                "id": item.get("id"),
                "type": file_type,
                "size": item.get("size", 0),
                "web_url": item.get("webUrl"),
                "download_url": item.get("@microsoft.graph.downloadUrl"),
                "thumbnail_url": thumbnail_url,
                "modified": item.get("lastModifiedDateTime"),
                "created": item.get("createdDateTime"),
                "created_by": item.get("createdBy", {}).get("user", {}).get("displayName", "Unknown"),
                "extension": extension,
                "source": "sharepoint",
            })

        return {
            "success": True,
            "files": files,
            "folders": folders,
            "frappe_records": frappe_records,
            "has_more": has_more,
            "next_token": next_token,
            "total_fetched": len(files),
            "folder_path": full_path,
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Folder Files Error")
        return {
            "success": False,
            "error": str(e),
            "files": [],
            "frappe_records": [],
            "has_more": False,
            "next_token": None,
        }


@frappe.whitelist()
def delete_folder_files(project, folder_path, files):
    """
    Bulk delete files from a custom project folder.

    Handles two sources:
    - 'sharepoint': deletes by constructing the full SharePoint path
    - 'frappe': deletes by Frappe File docname (frappe_file_name field)

    Args:
        project: Frappe Project name
        folder_path: Relative path inside the project folder (e.g. "My Folder")
        files: JSON list of file objects, each with:
               { source, name, frappe_file_name? }
               For SharePoint files 'name' is the filename (basename).
               For Frappe files 'frappe_file_name' is the Frappe File docname.

    Returns:
        dict: { success, deleted, failed, results }
    """
    import json

    try:
        if not project:
            frappe.throw("project parameter is required")
        if not folder_path:
            frappe.throw("folder_path parameter is required")
        if not files:
            return {"success": True, "deleted": 0, "failed": 0, "results": []}

        # files may arrive as JSON string when called via whitelisted POST
        if isinstance(files, str):
            files = json.loads(files)

        # Resolve project name for SharePoint path
        project_name = frappe.db.get_value("Project", project, "project_name") or project

        # Normalize folder path
        folder_path = "/".join(seg.strip() for seg in folder_path.strip("/").split("/") if seg.strip())
        sp_folder_full = f"Real Estate - US/Novel One/Projects/{project_name}/{folder_path}"

        # GetSharePoint client for SP deletions
        client = get_sharepoint_client()
        site_id = client["site_id"]
        drive_id = client["drive_id"]
        graph_base_url = client["graph_base_url"]
        headers = client["headers"]

        from urllib.parse import quote

        results = []
        deleted = 0
        failed = 0

        for f in files:
            source = f.get("source", "sharepoint")
            name = f.get("name", "")

            try:
                if source == "frappe":
                    # Delete Frappe File record (and the underlying file)
                    frappe_file_name = f.get("frappe_file_name") or name
                    if frappe.db.exists("File", frappe_file_name):
                        frappe.delete_doc("File", frappe_file_name, ignore_permissions=True, force=True)
                        results.append({"name": name, "success": True})
                        deleted += 1
                    else:
                        results.append({"name": name, "success": False, "error": "File not found in Frappe"})
                        failed += 1
                else:
                    # SharePoint file — Fix 3: prefer item-ID deletion (bulletproof)
                    # vs path-based (fragile if file was renamed in SharePoint)
                    item_id = f.get("sharepoint_item_id", "")
                    if item_id:
                        delete_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/items/{item_id}"
                    else:
                        # Fallback: path-based delete
                        full_file_path = f"{sp_folder_full}/{name}"
                        encoded_path = quote(full_file_path)
                        delete_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}"
                    resp = requests.delete(delete_url, headers=headers)
                    if resp.status_code in (200, 204):
                        results.append({"name": name, "success": True})
                        deleted += 1
                    elif resp.status_code == 404:
                        # Already gone — treat as success
                        results.append({"name": name, "success": True, "note": "already deleted"})
                        deleted += 1
                    else:
                        resp.raise_for_status()

            except Exception as err:
                results.append({"name": name, "success": False, "error": str(err)})
                failed += 1
                frappe.log_error(frappe.get_traceback(), f"Delete folder file error: {name}")

        return {
            "success": failed == 0,
            "deleted": deleted,
            "failed": failed,
            "results": results,
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Delete Folder Files Error")
        return {"success": False, "error": str(e), "deleted": 0, "failed": 0, "results": []}


@frappe.whitelist()
def get_projects_list():
    """
    Get list of all projects for the dropdown.
    
    Returns:
        dict: {
            "success": True,
            "projects": [
                {"name": "PROJECT-001", "project_name": "Building A"},
                ...
            ]
        }
    """
    try:
        projects = frappe.get_all(
            "Project",
            fields=["name", "project_name", "status"],
            filters={"status": ["!=", "Cancelled"]},
            order_by="modified desc",
            limit_page_length=0
        )
        
        return {
            "success": True,
            "projects": projects
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Projects List Error")
        return {
            "success": False,
            "error": str(e),
            "projects": []
        }
