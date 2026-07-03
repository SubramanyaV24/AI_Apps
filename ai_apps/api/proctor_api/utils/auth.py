import frappe
import os

def get_token_from_header() -> str:
    """Extract Bearer token from request headers."""
    auth_header = frappe.get_request_header('Authorization')
    if not auth_header:
        raise frappe.AuthenticationError('Missing Authorization header')
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        raise frappe.AuthenticationError('Invalid Authorization header format')
    return parts[1]

def validate_token() -> None:
    """Validate the token against a whitelist.

    The token can be stored in site config under "proctor_api_token" or as an
    environment variable ``PROCTOR_API_TOKEN``.
    """
    token = get_token_from_header()
    # Prefer site config, fallback to env var
    allowed = frappe.get_site_config().get('proctor_api_token') or os.getenv('PROCTOR_API_TOKEN')
    if not allowed:
        raise frappe.AuthenticationError('API token not configured')
    if token != allowed:
        raise frappe.PermissionError('Invalid API token')
