import frappe
from ai_apps.ai_screening.frappe_integration import enqueue_ai_screening, _resolve_audio_path
import os

BATCH_SIZE = 150

def main():
    docs = frappe.get_all(
        "WEB Page screening",
        filters={"self_introduction": ["!=", ""]},
        fields=["name", "atsid", "self_introduction"],
        limit=100000
    )
    
    print(f"Scanning {len(docs)} screening records to find {BATCH_SIZE} unprocessed candidates...")
    
    success_count = 0
    already_processed_count = 0
    missing_audio_count = 0
    
    for doc in docs:
        if success_count >= BATCH_SIZE:
            break
            
        # 1. Skip if physical audio file is missing
        audio_path = _resolve_audio_path(doc.self_introduction)
        if not audio_path or not os.path.isfile(audio_path):
            missing_audio_count += 1
            continue
            
        raw_atsid = doc.atsid
        if not raw_atsid:
            continue
            
        # 2. Extract clean ATSID
        atsid = str(raw_atsid).split("-")[0]
        
        # 3. Check if Candidate exists
        if not frappe.db.exists("Candidates", atsid):
            continue
            
        # 4. Target ONLY already processed candidates for re-evaluation
        ai_remarks = frappe.db.get_value("Candidates", atsid, "ai_remarks")
        if not ai_remarks:
            continue
        already_processed_count += 1
            
        # 5. Enqueue!
        try:
            # Frappe inherently prevents duplicate queueing if the job_id is still in the queue
            enqueue_ai_screening(doc.name)
            success_count += 1
            print(f"[{success_count}/{BATCH_SIZE}] Queued job for: {doc.name} (ATSID: {atsid})")
        except Exception as e:
            print(f"Failed to queue {doc.name}: {e}")
            
    print(f"\nSummary:")
    print(f"- Skipped missing physical audio: {missing_audio_count}")
    print(f"- Skipped already evaluated (ai_remarks present): {already_processed_count}")
    print(f"- Successfully queued for processing: {success_count}")

if __name__ == "__main__":
    main()
