import json
import frappe
import logging
import requests
from frappe.utils import now
from ai_apps.api.Sharepoint.sharepoint_auth import get_sharepoint_client
from urllib.parse import quote


def _delete_file_from_sharepoint(client, sharepoint_path):
    """Delete a file from SharePoint given its full path.
    The path should be the same as stored in ``sharepoint_path`` (e.g. "Real Estate - US/Novel One/Proctor/Evidence/<session>/<filename>").
    Returns ``True`` on success, ``False`` otherwise.
    """
    site_id = client["site_id"]
    drive_id = client["drive_id"]
    graph_base_url = client["graph_base_url"]
    access_token = client["access_token"]

    # Encode the full path for the API call
    encoded_path = quote(sharepoint_path)
    delete_url = f"{graph_base_url}/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.delete(delete_url, headers=headers)
        response.raise_for_status()
        return True
    except Exception as e:
        frappe.log_error(message=str(e), title="SharePoint delete error for path: {0}".format(sharepoint_path))
        return False


def delete_expired_evidence():
    """Scheduled task: delete Proctor Evidence records whose retention period has elapsed.
    It queries ``Proctor Evidence`` docs where ``retention_until`` is in the past, attempts to
    delete the associated file from SharePoint, and finally removes the document from the database.
    This function is intended to be called daily via the Frappe scheduler.
    """
    now_dt = now()
    # Fetch all evidence docs that have expired
    expired = frappe.get_all(
        "Proctor Evidence",
        filters={"retention_until": ("<", now_dt)},
        fields=["name", "sharepoint_url", "metadata"],
    )

    if not expired:
        logging.info("No expired Proctor Evidence to clean up.")
        return

    client = get_sharepoint_client()
    for rec in expired:
        doc = frappe.get_doc("Proctor Evidence", rec["name"])
        # Extract the stored SharePoint path from metadata if present
        sharepoint_path = None
        try:
            meta = json.loads(doc.metadata or "{}")
            sharepoint_path = meta.get("sharepoint_path") or meta.get("sharepoint_path")
        except Exception:
            pass
        # Fallback to URL parsing if path missing
        if not sharepoint_path and doc.sharepoint_url:
            # The URL typically ends with the filename; we can derive the path by stripping the domain
            # Example: https://tenant.sharepoint.com/sites/.../drive/root:/Real Estate - US/Novel One/Proctor/Evidence/.../file.jpg:/
            # We'll lookup the part after ":/" and before the final ":/"
            parts = doc.sharepoint_url.split(":/")
            if len(parts) > 1:
                sharepoint_path = parts[-2] if parts[-1] == "" else parts[-1]
        # Attempt SharePoint deletion if we have a path
        if sharepoint_path:
            success = _delete_file_from_sharepoint(client, sharepoint_path)
            if not success:
                frappe.log_error(message="Failed to delete SharePoint file for evidence {0}".format(doc.name), title="SharePoint Deletion Failure")
                continue
        # Delete the Doctype record
        try:
            doc.delete()
            logging.info("Deleted expired Proctor Evidence %s", doc.name)
        except Exception as e:
            frappe.log_error(message=str(e), title="Failed to delete Proctor Evidence record {0}".format(doc.name))


    logging.info("Expired Proctor Evidence cleanup completed. Total processed: %d", len(expired))
