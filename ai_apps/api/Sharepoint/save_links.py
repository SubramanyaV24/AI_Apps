"""
SharePoint Save Links API

Save SharePoint image/video links to Remodel doctype's child tables.
- image_links: Child table for image links
- video_links: Child table for video links
- explanation: Field for notes/description
"""

import frappe


@frappe.whitelist()
def save_links(property_name, save_type="all"):
    """
    Fetch images/videos from SharePoint and save their links to Remodel.
    
    Args:
        property_name: The Remodel property name
        save_type: "images", "videos", or "all" (default)
    
    Returns:
        dict: Success status with counts
    """
    try:
        if not property_name:
            frappe.throw("property_name is required")
        
        # Get the Remodel document
        doc = frappe.get_doc("Remodel", property_name)
        
        images_saved = 0
        videos_saved = 0
        
        # Save Images
        if save_type in ["images", "all"]:
            from .upload_attachments import get_images
            images_result = get_images(property_name)
            image_links = []
            if images_result.get("success") and images_result.get("images"):
                for img in images_result.get("images", []):
                    url = img.get("web_url")
                    if url:
                        image_links.append(url)
            
            # Clear and update image_links child table
            doc.image_links = []
            for link in image_links:
                doc.append("image_links", {
                    "image_link": link
                })
            images_saved = len(image_links)
        
        # Save Videos
        if save_type in ["videos", "all"]:
            from .upload_attachments import get_videos
            videos_result = get_videos(property_name)
            video_links = []
            if videos_result.get("success") and videos_result.get("videos"):
                for vid in videos_result.get("videos", []):
                    url = vid.get("web_url")
                    if url:
                        video_links.append(url)
            
            # Clear and update video_links child table
            doc.video_links = []
            for link in video_links:
                doc.append("video_links", {
                    "video_links": link
                })
            videos_saved = len(video_links)
        
        # Save the document
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        return {
            "success": True,
            "property_name": property_name,
            "images_saved": images_saved,
            "videos_saved": videos_saved,
            "save_type": save_type,
            "message": f"Saved {images_saved} images and {videos_saved} videos"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def save_description(property_name, description):
    """
    Save description/notes to the explanation field of Remodel.
    
    Args:
        property_name: The Remodel property name
        description: The description text to save
    
    Returns:
        dict: Success status
    """
    try:
        if not property_name:
            frappe.throw("property_name is required")
        
        frappe.db.set_value("Remodel", property_name, "explanation", description)
        frappe.db.commit()
        
        return {
            "success": True,
            "property_name": property_name,
            "message": "Description saved successfully"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
