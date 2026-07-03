"""
SharePoint Preview URL API

This module provides functionality to get temporary download/preview URLs
for SharePoint files. These URLs can be used directly in <img> tags
without authentication.

The download URLs are temporary and expire after ~1 hour.
"""

import frappe
import requests
from urllib.parse import urlparse, unquote
from .sharepoint_auth import get_sharepoint_client


@frappe.whitelist(allow_guest=True)
def get_preview_url(sharepoint_link):
    """
    Get a temporary preview/download URL for a SharePoint file.
    
    This converts a permanent SharePoint web URL into a temporary
    anonymous download URL that can be used in <img> or <video> tags.
    
    Args:
        sharepoint_link: The SharePoint web URL 
                        e.g., "https://novelteam.sharepoint.com/sites/Noveloffice/Shared%20Documents/..."
    
    Returns:
        dict: {
            "success": True/False,
            "download_url": "temporary anonymous URL",
            "filename": "file name",
            "mime_type": "image/jpeg",
            "size": 12345
        }
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.get_preview_url.get_preview_url
        Body: {"sharepoint_link": "https://novelteam.sharepoint.com/..."}
    """
    try:
        if not sharepoint_link:
            frappe.local.response['http_status_code'] = 400
            return {
                "success": False,
                "error": "sharepoint_link parameter is required"
            }
        
        
        # Get SharePoint client
        client = get_sharepoint_client()
        site_id = client['site_id']
        drive_id = client['drive_id']
        graph_base_url = client['graph_base_url']
        headers = client['headers']
        
        # Parse the SharePoint URL to extract the file path
        file_path = extract_file_path_from_url(sharepoint_link)
        
        if not file_path:
            frappe.local.response['http_status_code'] = 400
            return {
                "success": False,
                "error": "Could not extract file path from SharePoint URL",
                "sharepoint_link": sharepoint_link
            }
        
        # Get file metadata using Graph API - this includes the download URL
        # Use the path-based endpoint
        item_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{file_path}"
        
        response = requests.get(item_url, headers=headers)
        
        if response.status_code == 404:
            frappe.local.response['http_status_code'] = 404
            return {
                "success": False,
                "error": "File not found in SharePoint",
                "sharepoint_link": sharepoint_link,
                "file_path": file_path
            }
        
        response.raise_for_status()
        item_data = response.json()
        
        # The @microsoft.graph.downloadUrl is a temporary pre-authenticated URL
        download_url = item_data.get('@microsoft.graph.downloadUrl')
        
        if not download_url:
            frappe.local.response['http_status_code'] = 500
            return {
                "success": False,
                "error": "Could not get download URL from SharePoint",
                "sharepoint_link": sharepoint_link
            }
        
        return {
            "success": True,
            "download_url": download_url,
            "filename": item_data.get('name'),
            "mime_type": item_data.get('file', {}).get('mimeType'),
            "size": item_data.get('size'),
            "web_url": item_data.get('webUrl'),
            "id": item_data.get('id')
        }
        
    except requests.exceptions.HTTPError as http_error:
        frappe.local.response['http_status_code'] = http_error.response.status_code
        error_details = ""
        try:
            error_json = http_error.response.json()
            error_details = error_json.get('error', {}).get('message', str(http_error))
        except:
            error_details = str(http_error)
        
        return {
            "success": False,
            "error": error_details,
            "sharepoint_link": sharepoint_link
        }
    except Exception as e:
        frappe.local.response['http_status_code'] = 500
        frappe.log_error(frappe.get_traceback(), "SharePoint Get Preview URL Error")
        return {
            "success": False,
            "error": str(e),
            "sharepoint_link": sharepoint_link
        }


@frappe.whitelist(allow_guest=True)
def get_preview_urls_batch(sharepoint_links):
    """
    Get temporary preview/download URLs for multiple SharePoint files at once.
    
    This is more efficient than calling get_preview_url multiple times
    as it reuses the same authentication token.
    
    Args:
        sharepoint_links: JSON array of SharePoint URLs or list of URL strings
                         e.g., ["https://...", "https://..."]
    
    Returns:
        dict: {
            "success": True,
            "results": [
                {"success": True, "download_url": "...", "filename": "..."},
                {"success": False, "error": "..."}
            ]
        }
    
    Usage:
        POST /api/method/landwise.api-no.Sharepoint.get_preview_url.get_preview_urls_batch
        Body: {"sharepoint_links": ["https://...", "https://..."]}
    """
    import json
    
    try:
        # Parse JSON if it's a string
        if isinstance(sharepoint_links, str):
            try:
                sharepoint_links = json.loads(sharepoint_links)
            except json.JSONDecodeError:
                # If it's a single URL string, wrap it in a list
                sharepoint_links = [sharepoint_links]
        
        if not sharepoint_links or not isinstance(sharepoint_links, list):
            return {
                "success": False,
                "error": "sharepoint_links must be a non-empty array of URLs"
            }
        
        # Limit batch size to prevent timeout
        MAX_BATCH_SIZE = 20
        if len(sharepoint_links) > MAX_BATCH_SIZE:
            sharepoint_links = sharepoint_links[:MAX_BATCH_SIZE]
        
        # Get SharePoint client once for all requests
        client = get_sharepoint_client()
        site_id = client['site_id']
        drive_id = client['drive_id']
        graph_base_url = client['graph_base_url']
        headers = client['headers']
        
        from concurrent.futures import ThreadPoolExecutor
        
        def fetch_single_preview(link):
            try:
                file_path = extract_file_path_from_url(link)
                
                if not file_path:
                    return {
                        "success": False,
                        "sharepoint_link": link,
                        "error": "Could not extract file path from URL"
                    }
                
                # Get file metadata
                item_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{file_path}"
                response = requests.get(item_url, headers=headers)
                
                if response.status_code == 404:
                    return {
                        "success": False,
                        "sharepoint_link": link,
                        "error": "File not found"
                    }
                
                response.raise_for_status()
                item_data = response.json()
                
                download_url = item_data.get('@microsoft.graph.downloadUrl')
                
                if download_url:
                    return {
                        "success": True,
                        "sharepoint_link": link,
                        "download_url": download_url,
                        "filename": item_data.get('name'),
                        "mime_type": item_data.get('file', {}).get('mimeType'),
                        "size": item_data.get('size'),
                        "id": item_data.get('id')
                    }
                else:
                    return {
                        "success": False,
                        "sharepoint_link": link,
                        "error": "No download URL available"
                    }
                    
            except Exception as e:
                return {
                    "success": False,
                    "sharepoint_link": link,
                    "error": str(e)
                }
        
        with ThreadPoolExecutor(max_workers=min(len(sharepoint_links), 10)) as executor:
            results = list(executor.map(fetch_single_preview, sharepoint_links))
        
        return {
            "success": True,
            "total": len(sharepoint_links),
            "results": results
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "SharePoint Get Preview URLs Batch Error")
        return {
            "success": False,
            "error": str(e)
        }


def extract_file_path_from_url(sharepoint_url):
    """
    Extract the file path from a SharePoint URL.
    
    Handles different URL formats:
    1. Direct URL: https://novelteam.sharepoint.com/sites/Noveloffice/Shared%20Documents/Real%20Estate%20-%20US/...
    2. Doc.aspx URL: https://novelteam.sharepoint.com/sites/Noveloffice/_layouts/15/Doc.aspx?sourcedoc=...
    
    Args:
        sharepoint_url: The SharePoint URL
    
    Returns:
        str: The file path relative to the document library root, or None if can't parse
    """
    if not sharepoint_url:
        return None
    
    try:
        sharepoint_url = sharepoint_url.strip()
        parsed = urlparse(sharepoint_url)
        path = unquote(parsed.path).strip()  # Decode URL encoding and strip spaces
        
        # Handle _layouts/15/Doc.aspx URLs - these need the filename from parameters
        if '_layouts/15/Doc.aspx' in path or '_layouts/15/doc.aspx' in path.lower():
            # For Doc.aspx URLs, we can't easily get the path 
            # We would need the file parameter which only gives filename, not full path
            # Return None for now - these are typically document links
            return None
        
        # Handle direct file URLs
        # Look for "Shared Documents" or "Shared%20Documents" in the path
        shared_docs_markers = ['Shared Documents/', 'Shared%20Documents/']
        
        for marker in shared_docs_markers:
            if marker in path or marker.replace('%20', ' ') in path:
                # Extract everything after "Shared Documents/"
                idx = path.find('Shared Documents/')
                if idx == -1:
                    idx = path.find('Shared%20Documents/')
                    if idx != -1:
                        file_path = path[idx + len('Shared%20Documents/'):]
                    else:
                        return None
                else:
                    file_path = path[idx + len('Shared Documents/'):]
                
                # Clean up the path
                file_path = file_path.strip('/')
                return file_path
        
        # If we can't find "Shared Documents", try to extract path after /sites/sitename/
        # This is a fallback for other document libraries
        if '/sites/' in path:
            parts = path.split('/sites/')
            if len(parts) > 1:
                after_sites = parts[1]
                # Skip the site name
                site_parts = after_sites.split('/', 1)
                if len(site_parts) > 1:
                    return site_parts[1].strip('/')
        
        return None
        
    except Exception as e:
        frappe.logger().warning(f"Failed to parse SharePoint URL: {sharepoint_url}, error: {str(e)}")
        return None


@frappe.whitelist(allow_guest=True)
def get_file_thumbnail(sharepoint_link, size="medium"):
    """
    Get a thumbnail URL for a SharePoint file (works for images and documents).
    
    SharePoint can generate thumbnails for many file types including:
    - Images (jpg, png, gif, etc.)
    - PDFs
    - Office documents (docx, xlsx, pptx)
    
    Args:
        sharepoint_link: The SharePoint web URL
        size: Thumbnail size - "small" (96px), "medium" (176px), "large" (800px)
    
    Returns:
        dict: {
            "success": True/False,
            "thumbnail_url": "temporary thumbnail URL",
            "filename": "file name"
        }
    """
    try:
        if not sharepoint_link:
            return {
                "success": False,
                "error": "sharepoint_link parameter is required"
            }
        
        # Get SharePoint client
        client = get_sharepoint_client()
        site_id = client['site_id']
        drive_id = client['drive_id']
        graph_base_url = client['graph_base_url']
        headers = client['headers']
        
        # Parse the SharePoint URL to extract the file path
        file_path = extract_file_path_from_url(sharepoint_link)
        
        if not file_path:
            return {
                "success": False,
                "error": "Could not extract file path from SharePoint URL"
            }
        
        # First get the item ID
        item_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{file_path}"
        response = requests.get(item_url, headers=headers)
        
        if response.status_code == 404:
            return {
                "success": False,
                "error": "File not found in SharePoint"
            }
        
        response.raise_for_status()
        item_data = response.json()
        item_id = item_data.get('id')
        
        if not item_id:
            return {
                "success": False,
                "error": "Could not get file ID"
            }
        
        # Get thumbnails for the item
        thumbnails_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/items/{item_id}/thumbnails"
        thumb_response = requests.get(thumbnails_url, headers=headers)
        
        if thumb_response.status_code != 200:
            # Thumbnails not available for this file type
            # Fall back to download URL for images
            download_url = item_data.get('@microsoft.graph.downloadUrl')
            if download_url:
                return {
                    "success": True,
                    "thumbnail_url": download_url,
                    "filename": item_data.get('name'),
                    "is_original": True
                }
            return {
                "success": False,
                "error": "Thumbnails not available for this file"
            }
        
        thumb_data = thumb_response.json()
        thumbnails = thumb_data.get('value', [])
        
        if not thumbnails:
            # Fall back to download URL
            download_url = item_data.get('@microsoft.graph.downloadUrl')
            if download_url:
                return {
                    "success": True,
                    "thumbnail_url": download_url,
                    "filename": item_data.get('name'),
                    "is_original": True
                }
            return {
                "success": False,
                "error": "No thumbnails available"
            }
        
        # Get the requested size thumbnail
        thumb_set = thumbnails[0]  # First thumbnail set
        
        size_map = {
            "small": "small",
            "medium": "medium", 
            "large": "large"
        }
        
        thumb_size = size_map.get(size, "medium")
        thumbnail = thumb_set.get(thumb_size, thumb_set.get('medium', thumb_set.get('small')))
        
        if thumbnail and thumbnail.get('url'):
            return {
                "success": True,
                "thumbnail_url": thumbnail.get('url'),
                "filename": item_data.get('name'),
                "width": thumbnail.get('width'),
                "height": thumbnail.get('height'),
                "is_original": False
            }
        
        # Final fallback
        download_url = item_data.get('@microsoft.graph.downloadUrl')
        if download_url:
            return {
                "success": True,
                "thumbnail_url": download_url,
                "filename": item_data.get('name'),
                "is_original": True
            }
        
        return {
            "success": False,
            "error": "Could not get thumbnail URL"
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "SharePoint Get Thumbnail Error")
        return {
            "success": False,
            "error": str(e)
        }
