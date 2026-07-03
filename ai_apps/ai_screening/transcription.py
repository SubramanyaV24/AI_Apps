"""
transcription.py — Speech-to-text module for the AI HR Screening pipeline.

Uses faster-whisper (CTranslate2-backed Whisper) to transcribe audio files
locally. Handles low-quality audio, partial silence, and Indian English
(including Hinglish) inputs gracefully.
"""

import os
import logging

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
DEFAULT_MODEL_SIZE  = "medium"
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_DEVICE      = "cpu"
MIN_TRANSCRIPT_LENGTH = 20   # chars — below this is considered unusable

# ── Module-level model cache ───────────────────────────────────────────────────
_model_cache = None
_model_cache_key: str = ""


def _get_model(
    model_size: str = DEFAULT_MODEL_SIZE,
    device: str = DEFAULT_DEVICE,
    compute_type: str = DEFAULT_COMPUTE_TYPE,
) -> 'Any':
    """Load (or return cached) faster-whisper model."""
    from faster_whisper import WhisperModel
    
    global _model_cache, _model_cache_key

    cache_key = f"{model_size}:{device}:{compute_type}"
    if _model_cache is not None and _model_cache_key == cache_key:
        return _model_cache

    logger.info(
        "Loading Whisper model: size=%s  device=%s  compute=%s",
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
    Transcribe a single audio file using faster-whisper.

    Parameters
    ----------
    file_path : str
        Path to the WAV file to transcribe.

    Returns
    -------
    str
        Full transcript text. Empty string if transcription fails.
    """
    if not os.path.isfile(file_path):
        logger.error("Audio file not found: %s", file_path)
        return ""

    model = _get_model(model_size, device, compute_type)
    logger.info("Transcribing: %s", os.path.basename(file_path))

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
            initial_prompt=(
                "This is an Indian English speaker. Common terms include "
                "B.Tech, M.Tech, Indian city and village names, and Hinglish phrases."
            ),
        )

        transcript = " ".join(seg.text.strip() for seg in segments).strip()

        logger.info(
            "Detected language: %s (probability: %.2f)",
            info.language, info.language_probability,
        )

    except Exception as exc:
        logger.error("Transcription failed for %s: %s", file_path, exc)
        return ""

    if not transcript:
        logger.warning("Empty transcript from: %s", file_path)
        return ""

    logger.info("Transcription complete (%d chars): %s", len(transcript), os.path.basename(file_path))
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
