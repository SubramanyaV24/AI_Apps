import frappe
from ai_apps.api.proctor_api.proctor_session import sync_session_metrics

def execute():
    sessions = frappe.get_all("Proctor Session", fields=["name"])
    print(f"Found {len(sessions)} sessions to sync...")
    count = 0
    for s in sessions:
        try:
            sync_session_metrics(s.name)
            count += 1
            if count % 10 == 0:
                print(f"Synced {count} sessions...")
                frappe.db.commit()
        except Exception as e:
            print(f"Failed to sync {s.name}: {e}")
            
    frappe.db.commit()
    print(f"Successfully backfilled {count} sessions.")
