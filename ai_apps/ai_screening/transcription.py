"""
transcription.py — Speech-to-text module for the AI HR Screening pipeline.

Transcribes candidate audio files using a remote Faster-Whisper service
(configured via whisper_base_url in site_config or WHISPER_BASE_URL env var),
with automatic fallback to local faster-whisper (CTranslate2).
Handles low-quality audio, partial silence, and Indian English
(including Hinglish) inputs gracefully.
"""

import os
import logging
from typing import Any
import requests

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
DEFAULT_MODEL_SIZE  = "medium"
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_DEVICE      = "cpu"
MIN_TRANSCRIPT_LENGTH = 20   # chars — below this is considered unusable
REMOTE_TIMEOUT_SEC  = 120

INITIAL_PROMPT = (
    "This is an Indian English speaker. Common terms include "
    "B.Tech, M.Tech, Indian city and village names, and Hinglish phrases."
)

# ── Module-level model cache ───────────────────────────────────────────────────
_model_cache = None
_model_cache_key: str = ""


def _get_whisper_base_url() -> str | None:
    """Fetch remote Whisper service base URL from Frappe site_config or env var."""
    base_url = None
    try:
        import frappe
        site_config = frappe.get_site_config()
        base_url = site_config.get("whisper_base_url")
    except Exception:
        pass
    return base_url or os.getenv("WHISPER_BASE_URL", "http://10.80.4.84:8000")


def _transcribe_remote(file_path: str, base_url: str) -> str:
    """Send audio file to remote Faster-Whisper service."""
    url = f"{base_url.rstrip('/')}/transcribe"
    logger.info("Transcribing via remote Whisper service: %s -> %s", os.path.basename(file_path), url)

    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "audio/wav")}
        data = {"initial_prompt": INITIAL_PROMPT}
        resp = requests.post(url, files=files, data=data, timeout=REMOTE_TIMEOUT_SEC)

    if resp.status_code == 200:
        result = resp.json()
        transcript = result.get("text", "").strip()
        lang = result.get("language")
        prob = result.get("language_probability")
        if lang:
            logger.info("Remote Whisper detected language: %s (probability: %s)", lang, prob)
        return transcript
    else:
        logger.warning("Remote Whisper returned status %d: %s", resp.status_code, resp.text)
        return ""


def _get_model(
    model_size: str = DEFAULT_MODEL_SIZE,
    device: str = DEFAULT_DEVICE,
    compute_type: str = DEFAULT_COMPUTE_TYPE,
) -> Any:
    """Load (or return cached) local faster-whisper model."""
    from faster_whisper import WhisperModel
    
    global _model_cache, _model_cache_key

    cache_key = f"{model_size}:{device}:{compute_type}"
    if _model_cache is not None and _model_cache_key == cache_key:
        return _model_cache

    logger.info(
        "Loading local Whisper model: size=%s  device=%s  compute=%s",
        model_size, device, compute_type,
    )
    _model_cache = WhisperModel(model_size, device=device, compute_type=compute_type)
    _model_cache_key = cache_key
    return _model_cache


def transcribe_audio(
    file_path: str,
    model_size: str = DEFAULT_MODEL_SIZE,
    device: str = DEFAULT_DEVICE,
    compute_type: str = DEFAULT_COMPUTE_TYPE,
) -> str:
    """
    Transcribe a single audio file using remote Whisper service (fallback to local faster-whisper).

    Parameters
    ----------
    file_path : str
        Path to the audio file to transcribe.

    Returns
    -------
    str
        Full transcript text. Empty string if transcription fails.
    """
    if not os.path.isfile(file_path):
        logger.error("Audio file not found: %s", file_path)
        return ""

    # Attempt 1: Remote Whisper Service
    remote_url = _get_whisper_base_url()
    if remote_url:
        try:
            transcript = _transcribe_remote(file_path, remote_url)
            if transcript:
                logger.info("Remote transcription complete (%d chars): %s", len(transcript), os.path.basename(file_path))
                return transcript
            logger.warning("Remote Whisper returned empty transcript; attempting local fallback.")
        except Exception as exc:
            logger.warning("Remote Whisper request failed (%s); falling back to local model.", exc)

    # Attempt 2: Local faster-whisper fallback
    logger.info("Running local faster-whisper: %s", os.path.basename(file_path))
    model = _get_model(model_size, device, compute_type)

    try:
        segments, info = model.transcribe(
            file_path,
            beam_size=5,
            best_of=5,
            language=None,       # auto-detect (handles Hinglish)
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200,
            ),
            initial_prompt=INITIAL_PROMPT,
        )

        transcript = " ".join(seg.text.strip() for seg in segments).strip()

        logger.info(
            "Detected language: %s (probability: %.2f)",
            info.language, info.language_probability,
        )

    except Exception as exc:
        logger.error("Local transcription failed for %s: %s", file_path, exc)
        return ""

    if not transcript:
        logger.warning("Empty transcript from: %s", file_path)
        return ""

    logger.info("Local transcription complete (%d chars): %s", len(transcript), os.path.basename(file_path))
    return transcript


def is_low_confidence_transcript(transcript: str) -> bool:
    """Returns True if the transcript is too short to be useful."""
    if len(transcript.strip()) < MIN_TRANSCRIPT_LENGTH:
        logger.warning(
            "Low-confidence transcript (%d chars < %d threshold).",
            len(transcript.strip()), MIN_TRANSCRIPT_LENGTH,
        )
        return True
    return False
