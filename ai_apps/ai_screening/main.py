"""
main.py — AI HR Screening Pipeline orchestrator.

BACKEND INTEGRATION MODE:
  Call process_single_candidate(audio_path) from your Frappe integration.
  It returns a structured dict — no folders, no file I/O needed.

BATCH CLI MODE (optional):
  Place audio files in input_audio/ and run:
    python main.py
"""

import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

_pipeline_dir = os.path.dirname(os.path.abspath(__file__))
if _pipeline_dir not in sys.path:
    sys.path.insert(0, _pipeline_dir)

from audio_pipeline import process_audio, extract_speech_features
from transcription import transcribe_audio
from utils import clean_transcript, transcript_quality_score
from evaluator import evaluate_candidate

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
    )


# ── Calibration ───────────────────────────────────────────────────────────────
def calibrate_decision(result: dict) -> dict:
    """Apply penalties based on confidence and quality to normalise the score."""
    if result.get("status") != "completed":
        return result

    eval_data = result.get("evaluation", {})
    if eval_data.get("decision") == "Needs Human Review":
        return result

    score = eval_data.get("final_score", 0)
    confidence = result.get("evaluation_confidence", "high")
    quality = result.get("transcript_quality", {}).get("quality_score", 7)

    if confidence == "low":
        score -= 1.2
    elif confidence == "medium":
        score -= 0.4

    if quality <= 3:
        score -= 0.8

    score = max(0.0, min(10.0, score))

    decision = "Reject" if score < 5 else "Consider"

    result["calibrated_score"] = round(score, 2)
    result["calibrated_decision"] = decision
    return result


# ── Ranking ───────────────────────────────────────────────────────────────────
def rank_candidates(results: list[dict]) -> list[dict]:
    """Normalise scores across all candidates and assign ranks."""
    valid = [
        r for r in results
        if r.get("status") == "completed"
        and r.get("evaluation", {}).get("final_score", 0) > 0
    ]

    if not valid:
        return []

    scores = [r["evaluation"]["final_score"] for r in valid]
    min_s, max_s = min(scores), max(scores)

    if max_s - min_s < 0.5:
        for r in valid:
            r["normalized_score"] = round(r["evaluation"]["final_score"], 2)
    else:
        for r in valid:
            raw = r["evaluation"]["final_score"]
            r["normalized_score"] = round(10 * (raw - min_s) / (max_s - min_s), 2)

    valid.sort(key=lambda x: x["normalized_score"], reverse=True)
    for i, r in enumerate(valid):
        r["rank"] = i + 1

    return valid


# ── Core processing function (used by Frappe & CLI) ───────────────────────────
def process_single_candidate(audio_path: str, jd_text: str = None, resume_summary: str = None) -> dict:
    """
    Process a single candidate audio file through the full pipeline.

    Parameters
    ----------
    audio_path : str
        Absolute path to the audio file (any format supported by ffmpeg).

    Returns
    -------
    dict
        Structured result with transcript, scores, decision, and speech features.
        Write this dict directly into your Frappe doctype fields.
    """
    logger = logging.getLogger("pipeline")
    filename = os.path.basename(audio_path)
    cleaned_path = None

    result = {
        "filename": filename,
        "timestamp": datetime.now().isoformat(),
        "status": "pending",
        "transcript": None,
        "cleaned_transcript": None,
        "transcript_quality": None,
        "speech_features": None,
        "evaluation": None,
        "evaluation_confidence": None,
        "calibrated_score": None,
        "calibrated_decision": None,
        "accent": None,
        "mother_tongue_influence": None,
        "mother_tongue_influence_percentage": None,
        "error": None,
    }

    try:
        # Step 1 — Audio preprocessing (temp file, auto-cleaned)
        logger.info("[1/4] Audio preprocessing: %s", filename)
        cleaned_path = process_audio(audio_path)
        if cleaned_path is None:
            result["status"] = "skipped"
            result["error"] = "Audio is empty, silent, or could not be processed."
            return result

        # Step 2 — Speech feature extraction
        result["speech_features"] = extract_speech_features(cleaned_path)

        # Step 3 — Transcription
        logger.info("[2/4] Transcription: %s", filename)
        transcript = transcribe_audio(cleaned_path)
        if not transcript:
            result["status"] = "failed"
            result["error"] = "Transcription returned empty result."
            return result

        result["transcript"] = transcript

        # Step 4 — Text cleaning + quality
        logger.info("[3/4] Text cleaning: %s", filename)
        cleaned = clean_transcript(transcript)
        result["cleaned_transcript"] = cleaned
        quality = transcript_quality_score(cleaned)
        result["transcript_quality"] = quality

        # Step 5 — LLM evaluation
        logger.info("[4/4] LLM evaluation: %s", filename)
        evaluation = evaluate_candidate(
            cleaned,
            quality=quality,
            speech_features=result["speech_features"],
            jd_text=jd_text,
            resume_summary=resume_summary,
        )
        if evaluation is None:
            result["status"] = "failed"
            result["error"] = "LLM evaluation failed after retries."
            return result

        result["evaluation"] = evaluation
        result["evaluation_confidence"] = evaluation.get("evaluation_confidence")
        result["accent"] = evaluation.get("accent")
        result["mother_tongue_influence"] = evaluation.get("mother_tongue_influence")
        result["mother_tongue_influence_percentage"] = evaluation.get("mother_tongue_influence_percentage")
        result["status"] = "completed"

        # Step 6 — Calibration
        result = calibrate_decision(result)

        if evaluation.get("decision") == "Needs Human Review":
            logger.info("ℹ Human review required for %s.", filename)

    except Exception as exc:
        logger.exception("Unexpected failure processing %s: %s", filename, exc)
        result["status"] = "failed"
        result["error"] = str(exc)

    finally:
        # Always clean up the temp WAV file
        if cleaned_path and os.path.exists(cleaned_path):
            os.remove(cleaned_path)

    return result


# ── CLI Batch Mode (optional) ─────────────────────────────────────────────────
def _run_batch(input_dir: str = "input_audio") -> list[dict]:
    """
    Process all audio files in a given directory.
    Returns a ranked list of results (no files written).
    """
    logger = logging.getLogger("pipeline")
    AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus", ".webm"}

    audio_files = sorted([
        f for f in Path(input_dir).iterdir()
        if f.is_file() and f.suffix.lower() in AUDIO_EXTS
    ])

    if not audio_files:
        logger.warning("No audio files found in %s", input_dir)
        return []

    logger.info("Found %d audio file(s).", len(audio_files))
    start = time.time()

    max_workers = min(3, os.cpu_count() or 2)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        all_results = list(executor.map(
            lambda f: process_single_candidate(str(f)), audio_files
        ))

    ranked = rank_candidates(all_results)

    logger.info("─" * 60)
    logger.info("Pipeline complete — %.1fs", time.time() - start)
    for r in ranked:
        logger.info(
            "  #%d  %s  |  Score: %.2f  |  %s",
            r["rank"], r["filename"], r["normalized_score"],
            r.get("calibrated_decision", "—")
        )
    logger.info("─" * 60)

    return ranked


if __name__ == "__main__":
    setup_logging()
    _run_batch()
