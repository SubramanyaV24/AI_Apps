import os
import frappe
from frappe.utils import get_site_path
import logging
import json
import re
import requests
import threading

logger = logging.getLogger(__name__)

# Reusing LLM config
LLM_BASE_URL = "https://oma.novelinfra.com"
LLM_API_KEY = "sk-8TgQCpFTeZfci4fPt0oufw"
LLM_MODEL = "openai/gpt-oss:120b-cloud"
FALLBACK_MODEL = "glm-5.2-cloud"
MAX_RETRIES = 2
TIMEOUT = 30

def fetch_resume_for_candidate(atsid: str) -> str | None:
    """
    Fetches the Candidates doc, resolves the resume file attachment, returns file path on disk.
    Returns None if no attachment found.
    """
    try:
        if getattr(frappe.local, 'db', None) is None:
            return None
            
        if not frappe.db.exists("Candidates", atsid):
            return None
            
        candidate = frappe.get_doc("Candidates", atsid)
        
        file_url = None
        
        # Look up standard Frappe File attachments
        files = frappe.get_all("File", 
            filters={"attached_to_doctype": "Candidates", "attached_to_name": atsid},
            fields=["file_url"],
            order_by="creation desc",
            limit=1
        )
        if files:
            file_url = files[0].file_url
                
        if not file_url:
            return None
            
        # Resolve to absolute path
        path = file_url.strip("/")
        if path.startswith("files/"):
            path = os.path.join("public", path)
        
        abs_path = get_site_path(path)
        if os.path.isfile(abs_path):
            return abs_path
            
    except Exception as e:
        logger.error(f"Error fetching resume for Candidate {atsid}: {e}")
        
    return None

def _extract_text_worker(file_path: str, result_container: list):
    try:
        ext = os.path.splitext(file_path)[1].lower()
        text = ""
        
        if ext == '.pdf':
            # GLM OCR Placeholder - User will provide integration later
            # For now, we will just simulate a basic read if PyPDF2 is installed, or return placeholder
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(file_path)
                for page in doc:
                    text += page.get_text() + "\n"
            except ImportError:
                text = "[PyMuPDF not installed - run 'pip install pymupdf']"
            except Exception as e:
                logger.error(f"PyMuPDF extraction failed: {e}")
                text = "[PDF extraction failed]"
        elif ext == '.docx':
            try:
                import docx
                doc = docx.Document(file_path)
                text = "\n".join([para.text for para in doc.paragraphs])
            except ImportError:
                text = "[docx extraction requires python-docx]"
        elif ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
                
        # Truncate to ~2000 tokens (roughly 8000 characters)
        if len(text) > 8000:
            text = text[:8000] + "\n...[truncated]"
            
        result_container.append(text)
    except Exception as e:
        logger.error(f"Error in extract_text_worker: {e}")

def extract_resume_text(file_path: str) -> str | None:
    """
    Extracts text from a resume file with a 5-second timeout.
    """
    if not file_path or not os.path.isfile(file_path):
        return None
        
    result_container = []
    t = threading.Thread(target=_extract_text_worker, args=(file_path, result_container))
    t.start()
    t.join(5.0) # 5 second timeout
    
    if t.is_alive():
        logger.warning(f"Resume extraction timed out for {file_path}")
        return None
        
    if result_container:
        return result_container[0]
    return None

def summarise_resume(raw_text: str) -> str | None:
    """
    Summarise resume text into a structured summary block: Education, Work History, Skills, Domain, Years of Experience.
    """
    if not raw_text or not raw_text.strip():
        return None

    system_prompt = """You are an expert HR assistant. Summarise the following candidate resume text.
Extract and format the summary STRICTLY as follows:

Education: <summary of education>
Work History: <summary of work history>
Skills: <list of key skills>
Domain: <inferred domain/industry>
Years of Experience: <inferred total years>

Do NOT output anything else. If a section is missing, put 'Not specified'."""

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Resume Text:\n\n{raw_text}"},
        ],
        "temperature": 0.1,
        "top_p": 0.9,
        "seed": 42,
    }

    url = f"{LLM_BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    for attempt in range(1, MAX_RETRIES + 1):
        current_model = LLM_MODEL if attempt == 1 else FALLBACK_MODEL
        if attempt > 1:
            payload["model"] = current_model

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                return content.strip()
        except Exception as e:
            logger.warning(f"Failed LLM resume summarize attempt {attempt}: {e}")
            
    return None

def fetch_jd_for_candidate(atsid: str) -> str | None:
    """
    Fetches the Job Description from HR Openings based on Candidate's Position and Applied Role.
    """
    try:
        if getattr(frappe.local, 'db', None) is None:
            return None
            
        if not frappe.db.exists("Candidates", atsid):
            return None
            
        candidate = frappe.get_doc("Candidates", atsid)
        position = candidate.get("position")
        applied_role = candidate.get("applied_role")
        
        if not position and not applied_role:
            return None
            
        filters = {}
        if position:
            filters["positions"] = position
        if applied_role:
            filters["applied_role"] = applied_role
            
        hr_openings = frappe.get_all(
            "HR Openings", 
            filters=filters, 
            fields=["job_description", "job_description_web", "requirements"], 
            limit=1,
            order_by="creation desc"
        )
        
        if hr_openings:
            from frappe.utils import strip_html_tags
            jd_doc = hr_openings[0]
            jd_parts = []
            if jd_doc.job_description:
                jd_parts.append(strip_html_tags(jd_doc.job_description))
            elif jd_doc.job_description_web:
                jd_parts.append(strip_html_tags(jd_doc.job_description_web))
            if jd_doc.requirements:
                jd_parts.append("Requirements:\n" + strip_html_tags(jd_doc.requirements))
                
            return "\n\n".join(jd_parts) if jd_parts else None
            
    except Exception as e:
        logger.error(f"Error fetching JD for Candidate {atsid}: {e}")
        
    return None
