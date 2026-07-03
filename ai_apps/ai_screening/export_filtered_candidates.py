import frappe
import csv
import os
from ai_apps.ai_screening.frappe_integration import _resolve_audio_path

def main():
    docs = frappe.get_all(
        "WEB Page screening",
        filters={"self_introduction": ["!=", ""]},
        fields=["name", "atsid", "self_introduction"],
        limit=100000
    )
    
    valid_atsids = []
    
    for doc in docs:
        audio_path = _resolve_audio_path(doc.self_introduction)
        if not audio_path or not os.path.isfile(audio_path):
            continue
            
        raw_atsid = doc.atsid
        if not raw_atsid:
            continue
            
        atsid = str(raw_atsid).split("-")[0]
        
        if not frappe.db.exists("Candidates", atsid):
            continue
            
        ai_remarks = frappe.db.get_value("Candidates", atsid, "ai_remarks")
        if not ai_remarks:
            continue
            
        valid_atsids.append(atsid)
        
    print(f"Found {len(valid_atsids)} matching candidates.")
    
    if not valid_atsids:
        return
        
    candidates = frappe.get_all("Candidates", filters={"name": ["in", valid_atsids]}, fields=["*"])
    
    if not candidates:
        print("No candidates found.")
        return
        
    # Extract headers
    headers = list(candidates[0].keys())
    
    output_file = "/home/frappe/frappe-bench/apps/ai_apps/ai_apps/ai_screening/filtered_candidates_export.csv"
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        for candidate in candidates:
            # Frappe can return some non-string types, so let's write rows
            writer.writerow(candidate)
            
    print(f"Successfully exported data to {output_file}")

if __name__ == "__main__":
    main()
