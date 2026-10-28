"""
frappe_integration.py — Frappe ERP integration for the AI HR Screening pipeline.

Provides two entry points:
  - run_ai_screening(docname)      → processes one candidate, returns result dict
  - enqueue_ai_screening(docname)  → queues the above as a background job

# Usage from Frappe server script or hook:
#     from Ai_App.frappe_integration import enqueue_ai_screening
#     enqueue_ai_screening("CAND-0001")
# 
# NOTE: Set FRAPPE_APP_NAME below to match your Frappe app's module path.
# """

import os
import logging
from datetime import datetime, timedelta

import frappe
from frappe.utils import get_site_path

# ── Config ────────────────────────────────────────────────────────────────────
# The dotted module path Frappe uses to enqueue background jobs.
# Change "ai_hr_screening" to your actual Frappe app name if different.
FRAPPE_APP_NAME = "ai_apps.ai_screening"

# Frappe doctype name for candidate screening documents
DOCTYPE = "WEB Page screening"

# Field on the doctype that holds the uploaded audio file URL
AUDIO_FIELD = "self_introduction"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_audio_path(file_url: str) -> str | None:
    """
    Convert a Frappe file URL (e.g. /private/files/audio.mp3 or /files/audio.mp3)
    to an absolute filesystem path.
    """
    if not file_url:
        return None

    path = file_url.strip("/")
    if path.startswith("files/"):
        # In Frappe, /files/ points to the public files directory
        path = os.path.join("public", path)

    abs_path = get_site_path(path)
    if os.path.isfile(abs_path):
        return abs_path

    # Fallback: check private/files if stored with /files/ URL
    fname = os.path.basename(path)
    priv_path = get_site_path("private", "files", fname)
    if os.path.isfile(priv_path):
        return priv_path

    # Fallback for double extension mismatch (e.g. .mp3.mp3)
    if not abs_path.endswith(".mp3.mp3") and abs_path.endswith(".mp3"):
        fallback_path = abs_path + ".mp3"
        if os.path.isfile(fallback_path):
            return fallback_path

    return abs_path


def _build_result(candidate_result: dict) -> dict:
    """
    Map the pipeline output dict to the shape expected by the caller.
    """
    evaluation = candidate_result.get("evaluation") or {}
    return {
        "transcript":          candidate_result.get("transcript"),
        "cleaned_transcript":  candidate_result.get("cleaned_transcript"),
        "evaluation":          evaluation,
        "calibrated_score":    candidate_result.get("calibrated_score"),
        "decision":            candidate_result.get("calibrated_decision") or evaluation.get("decision"),
        "confidence":          candidate_result.get("evaluation_confidence"),
        "communication_traits": candidate_result.get("communication_traits", []),
        "behavioral_indicators": candidate_result.get("behavioral_indicators", []),
        "experience_assessment": candidate_result.get("experience_assessment", []),
        "professional_readiness": candidate_result.get("professional_readiness", []),
        "ai_flags":            candidate_result.get("ai_flags", []),
        "accent":              candidate_result.get("accent") or evaluation.get("accent"),
        "mother_tongue_influence": candidate_result.get("mother_tongue_influence") or evaluation.get("mother_tongue_influence"),
        "mother_tongue_influence_percentage": candidate_result.get("mother_tongue_influence_percentage") or evaluation.get("mother_tongue_influence_percentage"),
        # Populated by format_output() in run_ai_screening()
        "ai_remarks":          None,
        "ai_priority":         None,
    }


# ── Core entry point ──────────────────────────────────────────────────────────


def run_ai_screening_and_save(docname: str) -> dict:
    """
    Executes the pure run_ai_screening pipeline for a given WEB Page screening document
    and persists the relevant AI fields back to the linked Candidates document.
    This helper maintains the separation: run_ai_screening remains side‑effect free,
    while this function handles DB writes.
    """
    # Resolve short ATS ID to full docname if necessary
    if not frappe.db.exists(DOCTYPE, docname):
        docs = frappe.get_all(DOCTYPE, filters={"atsid": ["like", f"{docname}%"]}, limit=1)
        if not docs:
            docs = frappe.get_all(DOCTYPE, filters={"name": ["like", f"{docname}%"]}, limit=1)
        if docs:
            docname = docs[0].name

    # Step 1: run the pure pipeline
    result = run_ai_screening(docname)

    # Step 2: locate the WEB Page screening record to fetch ATSID
    web_doc = frappe.get_doc(DOCTYPE, docname)
    raw_atsid = getattr(web_doc, "atsid", None) or web_doc.name
    if not raw_atsid:
        frappe.log_error(f"Missing ATSID on WEB Page screening {docname}", "AI Screening Orchestration Error")
        return result
        
    # Strip the date suffix to get the actual Candidate ID (e.g. ATSID12345678-11-01-2026 -> ATSID12345678)
    atsid = str(raw_atsid).split("-")[0]

    # Step 3: fetch the Candidate document
    if not frappe.db.exists("Candidates", atsid):
        frappe.log_error(f"No Candidate found for ATSID {atsid}", "AI Screening Orchestration Error")
        return result
    candidate = frappe.get_doc("Candidates", atsid)

    # Step 4: write the AI fields (guards ensure fields exist)
    from evaluator import CATEGORY_SUB_TO_MAIN

    def _derive_main_tag(sub_tags: list, sub_to_main: dict) -> str | None:
        """Majority-vote across sub-tags to pick the single correct Main tag."""
        if not sub_tags:
            return None
        counts = {}
        for tag in sub_tags:
            main = sub_to_main.get(tag)
            if main:
                counts[main] = counts.get(main, 0) + 1
        return max(counts, key=counts.get) if counts else None

    def add_tags_to_candidate(candidate_doc, table_field: str, category_key: str, sub_tags: list):
        """
        Write exactly ONE derived Main tag + all sub-tags to a candidate child table.
        Main tag appears first so it's visible at a glance in the UI.
        """
        sub_to_main = CATEGORY_SUB_TO_MAIN.get(category_key, {})
        main_tag    = _derive_main_tag(sub_tags, sub_to_main)

        candidate_doc.set(table_field, [])   # clear existing tags
        added = set()

        # Write ONE main tag first
        if main_tag and main_tag not in added:
            candidate_doc.append(table_field, {category_key: main_tag})
            added.add(main_tag)

        # Then write sub-tags (deduped)
        for tag in sub_tags:
            if tag not in added:
                candidate_doc.append(table_field, {category_key: tag})
                added.add(tag)

    if hasattr(candidate, "ai_remarks"):
        candidate.ai_remarks = result.get("ai_remarks", "")
    if hasattr(candidate, "ai_priority"):
        candidate.ai_priority = result.get("ai_priority", "")

    if hasattr(candidate, "communication_trait"):
        add_tags_to_candidate(candidate, "communication_trait",
                              "communication_traits", result.get("communication_traits", []))
    if hasattr(candidate, "behavioral_indicators"):
        add_tags_to_candidate(candidate, "behavioral_indicators",
                              "behavioral_indicators", result.get("behavioral_indicators", []))
    if hasattr(candidate, "experience_assessment"):
        add_tags_to_candidate(candidate, "experience_assessment",
                              "experience_assessment", result.get("experience_assessment", []))
    if hasattr(candidate, "professional_readiness"):
        add_tags_to_candidate(candidate, "professional_readiness",
                              "professional_readiness", result.get("professional_readiness", []))
    if hasattr(candidate, "ai_flags"):
        add_tags_to_candidate(candidate, "ai_flags",
                              "ai_flags", result.get("ai_flags", []))

    # Accent & Mother Tongue Influence fields
    accent = result.get("accent") or ""
    mti_desc = result.get("mother_tongue_influence") or ""
    mti_pct = result.get("mother_tongue_influence_percentage") or ""

    def _find_field(doc, target_type: str) -> str | None:
        """
        Dynamically find the appropriate fieldname on a Frappe document/meta
        for 'accent', 'mti_desc', or 'mti_pct'. Supports custom_ prefixes and label fuzzy-matching.
        """
        meta = frappe.get_meta(doc.doctype)
        name_map = {
            "accent": [
                "accent", "custom_accent", "speaker_accent", "custom_speaker_accent",
                "candidate_accent", "custom_candidate_accent", "detected_accent"
            ],
            "mti_desc": [
                "mother_tongue_influence", "custom_mother_tongue_influence",
                "mother_tongue_influence_details", "custom_mother_tongue_influence_details",
                "mother_tongue_influence_explanation", "custom_mother_tongue_influence_explanation",
                "mti_explanation", "custom_mti_explanation",
                "mti_details", "custom_mti_details",
                "mti_influence", "custom_mti_influence"
            ],
            "mti_pct": [
                "mother_tongue_influence_percentage", "custom_mother_tongue_influence_percentage",
                "mother_tongue_influence_rating", "custom_mother_tongue_influence_rating",
                "mti_percentage", "custom_mti_percentage",
                "mother_tongue_percentage", "custom_mother_tongue_percentage",
                "mti_rating", "custom_mti_rating",
                "mti", "custom_mti",
                "percentage", "custom_percentage"
            ]
        }
        for c in name_map.get(target_type, []):
            if meta.has_field(c) or hasattr(doc, c):
                return c

        # Fallback: fuzzy match by label or fieldname across meta.fields
        for f in meta.fields:
            fn = (f.fieldname or "").lower()
            lbl = (f.label or "").lower()
            if target_type == "accent":
                if "accent" in fn or "accent" in lbl:
                    return f.fieldname
            elif target_type == "mti_desc":
                if ("mother" in fn or "mother" in lbl or "influence" in fn or "influence" in lbl or "mti" in fn or "mti" in lbl):
                    if not any(p in fn or p in lbl for p in ["percent", "%", "rating", "rate"]):
                        return f.fieldname
            elif target_type == "mti_pct":
                if ("mother" in fn or "mother" in lbl or "influence" in fn or "influence" in lbl or "mti" in fn or "mti" in lbl):
                    if any(p in fn or p in lbl for p in ["percent", "%", "rating", "rate"]):
                        return f.fieldname
        return None

    def _assign_field(doc, target_type: str, val) -> bool:
        if val is None or val == "":
            return False
        fn = _find_field(doc, target_type)
        if fn:
            meta = frappe.get_meta(doc.doctype)
            df = meta.get_field(fn)
            ft = getattr(df, "fieldtype", "") if df else ""
            if ft in ("Percent", "Float", "Currency", "Int"):
                try:
                    clean_num = float(str(val).replace("%", "").strip())
                    val = int(round(clean_num)) if ft == "Int" else clean_num
                except (ValueError, TypeError):
                    pass
            setattr(doc, fn, val)
            return True
        return False

    # Persist to Candidates doc if fields exist
    _assign_field(candidate, "accent", accent)
    _assign_field(candidate, "mti_desc", mti_desc)
    _assign_field(candidate, "mti_pct", mti_pct)

    # Step 5: persist changes
    candidate.save(ignore_permissions=True)

    # Also persist to WEB Page screening doc if fields exist there
    saved_web = False
    if _assign_field(web_doc, "accent", accent):
        saved_web = True
    if _assign_field(web_doc, "mti_desc", mti_desc):
        saved_web = True
    if _assign_field(web_doc, "mti_pct", mti_pct):
        saved_web = True
    if saved_web:
        web_doc.save(ignore_permissions=True)

    frappe.db.commit()
    return result


def run_ai_screening(docname: str) -> dict:
    """
    Main AI screening entry point. Called directly or via background job.

    Parameters
    ----------
    docname : str
        The name of the 'WEB Page screening' Frappe document to process.

    Returns
    -------
    dict
        Structured screening result ready to be written into the doctype.
    """
    logger = frappe.logger("ai_screening")
    logger.info(f"AI Screening started for: {docname}")

    # Inject virtualenv bin into PATH so subprocess can find ffmpeg
    import os
    os.environ["PATH"] = "/home/frappe/frappe-bench/env/bin:" + os.environ.get("PATH", "")

    # ── Step 1: Fetch document ────────────────────────────────────────────────
    if not frappe.db.exists(DOCTYPE, docname):
        # Allow passing the short ATS ID directly by searching for it
        docs = frappe.get_all(DOCTYPE, filters={"atsid": ["like", f"{docname}%"]}, limit=1)
        if not docs:
            # Fallback for when the document name itself starts with ATSID but the atsid field is empty
            docs = frappe.get_all(DOCTYPE, filters={"name": ["like", f"{docname}%"]}, limit=1)
        
        if docs:
            docname = docs[0].name
            logger.info(f"Resolved ATS ID to document name: {docname}")
        else:
            raise ValueError(f"Could not find a WEB Page screening document for '{docname}'")

    doc = frappe.get_doc(DOCTYPE, docname)

    # ── Step 2: Resolve audio file ────────────────────────────────────────────
    file_url = getattr(doc, AUDIO_FIELD, None)
    if not file_url:
        msg = f"Field '{AUDIO_FIELD}' is empty on {docname}. No audio to process."
        raise ValueError(msg)

    audio_path = _resolve_audio_path(file_url)
    if not audio_path or not os.path.isfile(audio_path):
        msg = f"Audio file not found on disk: {audio_path}"
        raise FileNotFoundError(msg)

    logger.info(f"Audio resolved: {audio_path}")

    # ── Step 3: Run pipeline ──────────────────────────────────────────────────
    import sys
    pipeline_dir = os.path.dirname(os.path.abspath(__file__))
    if pipeline_dir not in sys.path:
        sys.path.append(pipeline_dir)

    from main import process_single_candidate, setup_logging
    setup_logging()
    from evaluator import format_output, evaluate_tags
    
    from resume_extractor import fetch_resume_for_candidate, extract_resume_text, summarise_resume, fetch_jd_for_candidate
    import json
    
    jd_text = None
    
    pipeline_logger = logging.getLogger("pipeline")
    pipeline_logger.info(f"Fetching Resume context for {docname}...")
    raw_atsid = getattr(doc, "atsid", None) or doc.name
    atsid = str(raw_atsid).split("-")[0] if raw_atsid else None
    
    applied_role = None
    if atsid and frappe.db.exists("Candidates", atsid):
        try:
            cand_doc = frappe.get_doc("Candidates", atsid)
            pos = cand_doc.get("position")
            role = cand_doc.get("applied_role")
            if pos and role and str(pos).strip() != str(role).strip():
                applied_role = f"{pos} ({role})"
            else:
                applied_role = pos or role or cand_doc.get("applied_role_data")
        except Exception:
            pass
    if not applied_role:
        pos = getattr(doc, "position", None)
        role = getattr(doc, "applied_role", None)
        if pos and role and str(pos).strip() != str(role).strip():
            applied_role = f"{pos} ({role})"
        else:
            applied_role = pos or role

    if atsid:
        jd_text = fetch_jd_for_candidate(atsid)
        if jd_text:
            pipeline_logger.info("✔ JD context successfully extracted.")
        else:
            pipeline_logger.info("No JD context found.")
            
    resume_summary = None
    if atsid:
        resume_path = fetch_resume_for_candidate(atsid)
        if resume_path:
            pipeline_logger.info(f"Resume found at {resume_path}, extracting text...")
            resume_text = extract_resume_text(resume_path)
            if resume_text:
                pipeline_logger.info("RAW RESUME TEXT (first 2000 chars):")
                pipeline_logger.info(resume_text[:2000])
                pipeline_logger.info("Summarising resume text via LLM...")
                resume_summary = summarise_resume(resume_text)
                if resume_summary:
                    pipeline_logger.info("✔ Resume context successfully extracted.")
                    pipeline_logger.info("=" * 80)
                    pipeline_logger.info("RESUME CONTEXT")
                    pipeline_logger.info(resume_summary)
                    pipeline_logger.info("=" * 80)
                else:
                    pipeline_logger.warning("Failed to summarise resume text.")
            else:
                pipeline_logger.warning("Failed to extract text from resume file.")
        else:
            pipeline_logger.warning(f"No resume file found for candidate {atsid}.")
    else:
        pipeline_logger.warning("ATS ID could not be resolved, skipping resume extraction.")

    raw_result = process_single_candidate(audio_path, jd_text=jd_text, resume_summary=resume_summary)

    transcript = raw_result.get("transcript") or ""

    # Separate tag pass — transcript + JD + resume + acoustic signals, no score influence
    tags = evaluate_tags(
        transcript=transcript,
        jd_text=jd_text,
        resume_summary=resume_summary,
        speech_features=raw_result.get("speech_features")
    )

    # Merge tags into result (do NOT feed into format_output or priority logic)
    raw_result["communication_traits"] = tags.get("communication_traits", [])
    raw_result["behavioral_indicators"] = tags.get("behavioral_indicators", [])
    raw_result["experience_assessment"] = tags.get("experience_assessment", [])
    raw_result["professional_readiness"] = tags.get("professional_readiness", [])
    raw_result["ai_flags"] = tags.get("ai_flags", [])

    # ── Step 4: Shape result ──────────────────────────────────────────────────
    result = _build_result(raw_result)

    logger.info(
        f"AI Screening completed for {docname} — "
        f"Score: {result.get('calibrated_score')}  "
        f"Decision: {result.get('decision')}"
    )

    # ── Step 5: Format HR output (second LLM pass — minimal context only) ─────
    evaluation = raw_result.get("evaluation") or {}
    raw_reason = evaluation.get("reason") or ""
    accent_val = result.get("accent")
    mti_desc_val = result.get("mother_tongue_influence")
    mti_pct_val = result.get("mother_tongue_influence_percentage")

    # format_output receives: decision, final_score, confidence, reason, applied_role, accent, MTI
    formatted = format_output(
        decision=result.get("decision") or "",
        final_score=result.get("calibrated_score") or 0,
        confidence=result.get("confidence") or "low",
        reason=raw_reason,
        applied_role=applied_role,
        accent=accent_val,
        mother_tongue_influence=mti_desc_val,
        mother_tongue_influence_percentage=mti_pct_val,
    )

    if formatted:
        ai_remarks = formatted["ai_remarks"]
        ai_priority = formatted["ai_priority"]
    else:
        # Fallback — guarantees output is never empty.
        # Priority is confidence + score aware so weak-confidence cases are never inflated.
        logger.warning(
            f"format_output failed for {docname} — falling back to raw reason text."
        )
        ai_remarks = raw_reason
        fallback_score = result.get("calibrated_score") or 0
        fallback_confidence = result.get("confidence") or "low"

        if fallback_confidence == "low":
            ai_priority = "P4"          # uncertainty principle — never promote low-confidence
        elif fallback_score >= 6.5:
            ai_priority = "P2"          # strong enough score with acceptable confidence
        else:
            ai_priority = "P3"

    # Guard 1 — Validate priority against allowed set (LLM edge-case protection)
    _VALID_PRIORITIES = {"P1", "P2", "P3", "P4", "P5"}
    if ai_priority not in _VALID_PRIORITIES:
        logger.warning(
            f"Invalid ai_priority '{ai_priority}' for {docname} — defaulting to P3."
        )
        ai_priority = "P3"

    # Guard 2 — Hard-enforce P4 if the pipeline flagged uncertainty
    # Applied after priority validation so it always wins
    if result.get("decision") == "Needs Human Review":
        ai_priority = "P4"

    # Guard 3 — Strip and cap remarks length (UI / DB safety)
    ai_remarks = ai_remarks.strip()
    if len(ai_remarks) > 1200:
        ai_remarks = ai_remarks[:1200].strip()

    # Guard 4 — Ensure remarks are never empty under any failure path
    if not ai_remarks:
        logger.warning(
            f"ai_remarks empty for {docname} after all fallbacks — using default message."
        )
        ai_remarks = "Insufficient data for evaluation. Requires manual review."
        ai_priority = "P4"

    result["ai_remarks"] = ai_remarks
    result["ai_priority"] = ai_priority

    logger.info(
        f"AI Screening done for {docname} — "
        f"Priority: {ai_priority} | Score: {result.get('calibrated_score')}"
    )

    # DB write is intentionally NOT here — caller (batch layer) owns the write.
    return result


# ── Background job wrapper ────────────────────────────────────────────────────

@frappe.whitelist()
def enqueue_ai_screening(docname: str) -> dict:
    """
    Enqueue run_ai_screening as a Frappe background job.
    Safe to call from client scripts, server scripts, and hooks.

    The job runs in the 'long' queue with a 10-minute timeout.

    Parameters
    ----------
    docname : str
        The name of the 'WEB Page screening' document to process.

    Returns
    -------
    dict
        Confirmation that the job was enqueued (not the screening result).
    """
    frappe.enqueue(
        f"{FRAPPE_APP_NAME}.frappe_integration.run_ai_screening_and_save",
        queue="long",
        timeout=600,          # 10 minutes — transcription + LLM can be slow
        job_id=f"ai_screening_{docname}",   # prevents duplicate jobs
        docname=docname,
    )

    frappe.logger("ai_screening").info(f"AI Screening enqueued for: {docname}")

    return {
        "status": "enqueued",
        "docname": docname,
        "message": f"AI screening job queued for {docname}. Check background jobs for result.",
    }


def daily_ai_screening_batch():
    """
    Runs daily at 10 PM IST via Frappe scheduler
    Processes WEB Page screening docs from last 24 hours
    """
    import json
    import os

    now = frappe.utils.now_datetime()
    last_24_hours = now - timedelta(hours=24)

    # Load previously processed records to avoid reprocessing
    processed_file = frappe.get_site_path("private", "files", "processed_ai_screenings.json")
    processed_docs = set()
    
    if os.path.exists(processed_file):
        try:
            with open(processed_file, "r") as f:
                processed_docs = set(json.load(f))
        except Exception:
            # If the file is corrupted or empty, fallback to an empty set
            pass

    docs = frappe.get_all(
        "WEB Page screening",
        filters={
            "creation": [">=", last_24_hours],
            "self_introduction": ["!=", ""]
        },
        fields=["name"]
    )

    frappe.logger().info(f"AI Batch Start: {len(docs)} records found")

    for d in docs:
        if d.name in processed_docs:
            frappe.logger().debug(f"Skipping already processed record: {d.name}")
            continue

        try:
            # ── STEP 1: EXTRACT CORRECT FIELD ─────────────────────────────────
            web_doc = frappe.get_doc("WEB Page screening", d.name)
            raw_atsid = web_doc.atsid

            # ── STEP 2: VALIDATE ATSID ────────────────────────────────────────
            if not raw_atsid:
                frappe.logger().warning(f"Missing ATSID for {d.name}")
                continue

            atsid = str(raw_atsid).split("-")[0]

            # ── STEP 3: VERIFY CANDIDATE EXISTS ───────────────────────────────
            if not frappe.db.exists("Candidates", atsid):
                frappe.logger().warning(f"No Candidate found for ATSID: {atsid}")
                continue

            # ── STEP 4: FETCH CANDIDATE ───────────────────────────────────────
            candidate = frappe.get_doc("Candidates", atsid)

            # ── STEP 6: RUN PIPELINE AND SAVE ─────────────────────────────────
            result = run_ai_screening_and_save(d.name)
            
            if not result or "ai_remarks" not in result or "ai_priority" not in result:
                frappe.logger().error(f"Pipeline failed to return remarks/priority for {d.name}")
                continue

            # ── STEP 8: LOG SUCCESS ───────────────────────────────────────────
            frappe.logger().debug({
                "web_doc": d.name,
                "atsid": atsid,
                "candidate_doc": atsid,
                "ai_priority": result["ai_priority"]
            })

            # Mark as processed
            processed_docs.add(d.name)

        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"AI Batch Failure: {d.name}"
            )

    # Save the updated processed list
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(processed_file), exist_ok=True)
        with open(processed_file, "w") as f:
            json.dump(list(processed_docs), f)
    except Exception as exc:
        frappe.log_error(f"Failed to save processed records list: {exc}", "AI Batch Tracker Error")

    frappe.logger().info("AI Batch Completed")
