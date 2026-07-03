"""
SharePoint Authentication Utility Module

This module provides reusable authentication functions for SharePoint operations.
It caches access tokens and site/drive IDs to improve API efficiency.

Usage:
    from .sharepoint_auth import get_sharepoint_client
    
    client = get_sharepoint_client()
    access_token = client['access_token']
    site_id = client['site_id']
    drive_id = client['drive_id']
    headers = client['headers']
"""

import frappe
import requests
from urllib.parse import urlparse
from datetime import datetime, timedelta


# Cache storage (in-memory, will reset on server restart)
_cache = {
    'access_token': None,
    'token_expires_at': None,
    'site_id': None,
    'drive_id': None,
    'sharepoint_site': None
}


def get_access_token():
    """
    Get or refresh access token for Microsoft Graph API.
    Caches the token until it expires (typically 1 hour).
    
    Returns:
        str: Access token
    """
    global _cache
    
    # Check if we have a valid cached token
    if _cache['access_token'] and _cache['token_expires_at']:
        if datetime.now() < _cache['token_expires_at']:
            return _cache['access_token']
    
    # Get credentials from Frappe config
    tenant_id = frappe.conf.get("sharepoint_tenant_id")
    client_id = frappe.conf.get("sharepoint_client_id") or frappe.db.get_single_value("SharePoint Settings", "client_id")
    client_secret = frappe.conf.get("sharepoint_client_secret") or frappe.db.get_single_value("SharePoint Settings", "client_secret")
    
    if not client_id or not client_secret:
        frappe.throw("SharePoint credentials not configured. Please set client_id and client_secret in site_config.json or SharePoint Settings.")
    
    if not tenant_id:
        frappe.throw("SharePoint tenant_id not configured. Please set sharepoint_tenant_id in site_config.json.")
    
    # Get new access token
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    
    token_data = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
        'scope': 'https://graph.microsoft.com/.default'
    }
    
    token_response = requests.post(token_url, data=token_data)
    
    if token_response.status_code != 200:
        error_details = ""
        try:
            error_json = token_response.json()
            error_details = error_json.get('error_description', error_json.get('error', str(token_response.text)))
        except:
            error_details = token_response.text
        
        frappe.throw(
            f"Failed to obtain access token: {error_details}\n\n"
            f"Token URL: {token_url}\n"
            "Please verify:\n"
            "1. Tenant ID is correct\n"
            "2. Client ID is correct\n"
            "3. Client Secret is correct and not expired"
        )
    
    token_data_response = token_response.json()
    access_token = token_data_response.get('access_token')
    
    if not access_token:
        frappe.throw("Failed to obtain access token from Microsoft Graph API - no access_token in response")
    
    # Cache the token with expiration (subtract 5 minutes for safety margin)
    expires_in = token_data_response.get('expires_in', 3600)  # Default to 1 hour if not provided
    expires_at = datetime.now() + timedelta(seconds=expires_in - 300)  # 5 min buffer
    
    _cache['access_token'] = access_token
    _cache['token_expires_at'] = expires_at
    
    frappe.logger().info("✅ SharePoint access token refreshed")
    
    return access_token


def get_site_and_drive_ids(force_refresh=False):
    """
    Get or retrieve cached site_id and drive_id for SharePoint.
    These rarely change, so we cache them indefinitely unless force_refresh=True.
    
    Args:
        force_refresh (bool): Force refresh of site_id and drive_id from API
    
    Returns:
        tuple: (site_id, drive_id)
    """
    global _cache
    
    sharepoint_site = frappe.conf.get("sharepoint_site")
    
    # Check if we have cached values and site hasn't changed
    if not force_refresh and _cache['site_id'] and _cache['drive_id'] and _cache['sharepoint_site'] == sharepoint_site:
        return _cache['site_id'], _cache['drive_id']
    
    # Get access token
    access_token = get_access_token()
    
    # Extract site information from SharePoint URL
    parsed_url = urlparse(sharepoint_site)
    hostname = parsed_url.netloc  # e.g., novelteam.sharepoint.com
    site_path = parsed_url.path.strip('/')  # e.g., sites/Noveloffice
    
    # Get site ID using Graph API
    graph_base_url = "https://graph.microsoft.com/v1.0"
    site_url = f"{graph_base_url}/sites/{hostname}:/{site_path}"
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    site_response = requests.get(site_url, headers=headers)
    
    if site_response.status_code == 401:
        # Token might be expired, clear cache and retry once
        _cache['access_token'] = None
        _cache['token_expires_at'] = None
        access_token = get_access_token()
        headers['Authorization'] = f'Bearer {access_token}'
        site_response = requests.get(site_url, headers=headers)
    
    site_response.raise_for_status()
    site_data = site_response.json()
    site_id = site_data.get('id')
    
    if not site_id:
        frappe.throw("Failed to get site_id from SharePoint")
    
    # Get the default document library (drive)
    drives_url = f"{graph_base_url}/sites/{site_id}/drives"
    drives_response = requests.get(drives_url, headers=headers)
    drives_response.raise_for_status()
    drives_data = drives_response.json()
    
    # Find the default document library (usually named "Documents" or "Shared Documents")
    drive_id = None
    for drive in drives_data.get('value', []):
        drive_name = drive.get('name', '').lower()
        if 'document' in drive_name and drive.get('driveType') == 'documentLibrary':
            drive_id = drive.get('id')
            break
    
    if not drive_id and drives_data.get('value'):
        # Use first drive if no document library found
        drive_id = drives_data['value'][0].get('id')
    
    if not drive_id:
        frappe.throw("Could not find document library in SharePoint site")
    
    # Cache the values
    _cache['site_id'] = site_id
    _cache['drive_id'] = drive_id
    _cache['sharepoint_site'] = sharepoint_site
    
    frappe.logger().info(f"✅ SharePoint site_id and drive_id cached: site={site_id[:20]}..., drive={drive_id[:20]}...")
    
    return site_id, drive_id


def get_sharepoint_client(force_refresh=False):
    """
    Get a complete SharePoint client configuration with all necessary authentication info.
    This is the main function to use for SharePoint operations.
    
    Args:
        force_refresh (bool): Force refresh of cached values
    
    Returns:
        dict: {
            'access_token': str,
            'site_id': str,
            'drive_id': str,
            'headers': dict,  # Ready-to-use headers for Graph API requests
            'graph_base_url': str,
            'sharepoint_site': str
        }
    """
    access_token = get_access_token()
    site_id, drive_id = get_site_and_drive_ids(force_refresh=force_refresh)
    sharepoint_site = frappe.conf.get("sharepoint_site") 
    
    return {
        'access_token': access_token,
        'site_id': site_id,
        'drive_id': drive_id,
        'headers': {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        },
        'graph_base_url': 'https://graph.microsoft.com/v1.0',
        'sharepoint_site': sharepoint_site
    }


def clear_cache():
    """
    Clear all cached authentication data.
    Useful for testing or when credentials change.
    """
    global _cache
    _cache = {
        'access_token': None,
        'token_expires_at': None,
        'site_id': None,
        'drive_id': None,
        'sharepoint_site': None
    }
    frappe.logger().info("✅ SharePoint authentication cache cleared")

