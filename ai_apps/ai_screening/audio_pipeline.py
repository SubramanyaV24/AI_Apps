"""
audio_pipeline.py — Audio preprocessing for the AI HR Screening pipeline.

Responsibilities:
  1. Convert any audio format to mono WAV at 16 kHz (via ffmpeg).
  2. Normalize volume.
  3. Reduce background noise (via noisereduce).
  4. Uses the OS temp directory — no permanent folders required.
"""

import os
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
TARGET_SAMPLE_RATE = 16_000      # 16 kHz mono — optimal for Whisper
MIN_AUDIO_DURATION_SEC = 1.0     # skip files shorter than this


def _check_ffmpeg() -> None:
    """
    Ensure ffmpeg is available on PATH.
    If not found, auto-installs it via apt-get (Linux servers).
    This runs once — after installation ffmpeg is permanently on the system.
    """
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return  # already installed
    except FileNotFoundError:
        pass

    logger.info("ffmpeg not found — auto-installing via apt-get...")
    try:
        subprocess.run(
            ["sudo", "apt-get", "install", "-y", "ffmpeg"],
            check=True,
        )
        logger.info("ffmpeg installed successfully.")
    except Exception as exc:
        raise RuntimeError(
            "ffmpeg is not installed and auto-install failed.\n"
            "Fix manually with:  sudo apt install ffmpeg"
        ) from exc


def convert_to_wav(input_path: str, output_path: str) -> str:
    """
    Convert any audio file to mono WAV at 16 kHz using ffmpeg.
    Volume is normalized via the 'loudnorm' filter.
    Returns the output file path.
    """
    _check_ffmpeg()

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ac", "1",
        "-ar", str(TARGET_SAMPLE_RATE),
        "-acodec", "pcm_s16le",
        "-af", "loudnorm",
        output_path,
    ]

    logger.info("Converting → mono 16 kHz WAV: %s", os.path.basename(input_path))
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logger.error("ffmpeg error:\n%s", result.stderr)
        raise RuntimeError(f"ffmpeg conversion failed for {input_path}")

    return output_path


def reduce_noise(wav_path: str) -> str:
    """
    Apply spectral-gating noise reduction to a WAV file (in-place overwrite).
    Returns the same wav_path for chaining convenience.
    """
    from scipy.io import wavfile
    import numpy as np
    import noisereduce as nr
    
    logger.info("Reducing noise: %s", os.path.basename(wav_path))

    rate, data = wavfile.read(wav_path)
    data = data.astype(np.float32)

    reduced = nr.reduce_noise(
        y=data,
        sr=rate,
        stationary=True,
        prop_decrease=0.75,
    )

    reduced = np.clip(reduced, -32768, 32767).astype(np.int16)
    wavfile.write(wav_path, rate, reduced)

    return wav_path


def is_audio_empty(wav_path: str) -> bool:
    """
    Check whether the audio file is effectively silent / too short.
    Returns True if the file should be skipped.
    """
    from scipy.io import wavfile
    import numpy as np
    
    try:
        rate, data = wavfile.read(wav_path)
    except Exception as exc:
        logger.warning("Cannot read WAV file %s: %s", wav_path, exc)
        return True

    duration = len(data) / rate
    if duration < MIN_AUDIO_DURATION_SEC:
        logger.warning("Audio too short (%.2fs): %s", duration, wav_path)
        return True

    rms = np.sqrt(np.mean(data.astype(np.float64) ** 2))
    if rms < 10:
        logger.warning("Audio is silent (RMS=%.2f): %s", rms, wav_path)
        return True

    return False


def extract_speech_features(audio_path: str) -> dict:
    """
    Extract lightweight acoustic features to support communication evaluation.
    """
    import librosa
    import numpy as np
    
    try:
        y, sr = librosa.load(audio_path, sr=TARGET_SAMPLE_RATE)

        duration = librosa.get_duration(y=y, sr=sr)
        rms = np.mean(librosa.feature.rms(y=y))
        zcr = np.mean(librosa.feature.zero_crossing_rate(y))
        speaking_rate = float(zcr * 100)

        silence_threshold = 0.01
        silent_frames = np.sum(np.abs(y) < silence_threshold)
        pause_ratio = silent_frames / len(y) if len(y) > 0 else 0

        return {
            "duration": round(float(duration), 2),
            "energy": round(float(rms), 4),
            "speaking_rate": round(float(speaking_rate), 2),
            "pause_ratio": round(float(pause_ratio), 2)
        }
    except Exception as exc:
        logger.warning("Speech feature extraction failed for %s: %s", audio_path, exc)
        return {"duration": 0, "energy": 0, "speaking_rate": 0, "pause_ratio": 0}


def process_audio(input_path: str) -> str | None:
    """
    Full audio preprocessing pipeline for a single file.
    Uses OS temp directory — no permanent folder required.
    Caller is responsible for deleting the returned temp file after use.

    Returns path to a cleaned temp WAV file, or None if skipped/failed.
    """
    tmp_fd, cleaned_path = tempfile.mkstemp(suffix=".wav")
    os.close(tmp_fd)  # close fd — ffmpeg will write to the path

    try:
        convert_to_wav(input_path, cleaned_path)

        if is_audio_empty(cleaned_path):
            logger.warning("Skipping empty/silent audio: %s", input_path)
            os.remove(cleaned_path)
            return None

        reduce_noise(cleaned_path)

        logger.info("✔ Audio cleaned: %s", os.path.basename(input_path))
        return cleaned_path

    except Exception as exc:
        logger.error("Audio processing failed for %s: %s", input_path, exc)
        if os.path.exists(cleaned_path):
            os.remove(cleaned_path)
        return None
