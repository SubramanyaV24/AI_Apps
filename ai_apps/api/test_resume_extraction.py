import frappe
from ai_apps.ai_screening.resume_extractor import (
    extract_resume_text,
    summarise_resume,
    fetch_jd_for_candidate
)
import os

def run():
    print("Testing JD Extraction for ATSID01541592...")
    jd_text = fetch_jd_for_candidate("ATSID01541592")
    if jd_text:
        print(f"SUCCESS: Extracted JD ({len(jd_text)} chars):\n{jd_text}\n")
    else:
        print("FAILED to extract JD.\n")

    print("Creating a fake resume file for testing...")
    fake_resume_path = os.path.abspath("test_resume.txt")
    with open(fake_resume_path, "w") as f:
        f.write("""
John Doe
Location: Bangalore, India
Email: johndoe@example.com

Education:
- B.Tech in Computer Science, Visvesvaraya Technological University (2018-2022)

Work History:
- Software Engineer at TechCorp (2022 - Present)
  * Developed Python backend services.
  * Maintained PostgreSQL databases.

Skills: Python, Frappe, JavaScript, SQL, Git
""")

    print(f"Testing Resume Extraction on {fake_resume_path}...")
    raw_text = extract_resume_text(fake_resume_path)
    if raw_text:
        print(f"SUCCESS: Extracted raw text. Preview:\n{raw_text[:200]}...\n")
        
        print("Calling LLM to summarise resume...")
        summary = summarise_resume(raw_text)
        if summary:
            print(f"SUCCESS: LLM Summary:\n{summary}")
        else:
            print("FAILED: LLM failed to return a summary.")
    else:
        print("FAILED: Could not extract raw text from file.")
        
    os.remove(fake_resume_path)
