import frappe
import csv
import sys
import os

def main():

    # Get candidates that have an AI priority assigned
    candidates = frappe.get_all(
        "Candidates",
        filters={"ai_priority": ["is", "set"]},
        fields=["name", "ai_priority", "application_status", "ai_remarks"]
    )

    csv_path = "candidate_report.csv"
    with open(csv_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Candidate ID", "AI Priority", "Application Status"])
        
        for c in candidates:
            # name is usually Candidate ID
            writer.writerow([c.get("name"), c.get("ai_priority"), c.get("application_status")])

    print(f"Exported {len(candidates)} candidates to {csv_path}")
    
    # Print stats for the agent to analyze
    priority_counts = {}
    status_counts = {}
    for c in candidates:
        p = c.get("ai_priority", "Unknown")
        s = c.get("application_status", "Unknown")
        priority_counts[p] = priority_counts.get(p, 0) + 1
        status_counts[s] = status_counts.get(s, 0) + 1

    print("\n--- Priority Summary ---")
    for k, v in priority_counts.items():
        print(f"{k}: {v}")
        
    print("\n--- Status Summary ---")
    for k, v in status_counts.items():
        print(f"{k}: {v}")

    # Also calculate the agreement between AI Priority and Application Status if Application Status has been updated
    # e.g., if P1/P2 is Approved/Shortlisted and P3/P4 is Rejected, we can measure accuracy.
    # We will print out a confusion matrix
    print("\n--- Cross Tabulation (Priority vs Status) ---")
    matrix = {}
    for c in candidates:
        p = c.get("ai_priority", "Unknown")
        s = c.get("application_status", "Unknown")
        if p not in matrix:
            matrix[p] = {}
        matrix[p][s] = matrix[p].get(s, 0) + 1
        
    for p in sorted(matrix.keys()):
        for s in sorted(matrix[p].keys()):
            print(f"Priority: {p}, Status: {s} -> {matrix[p][s]}")

if __name__ == "__main__":
    main()
