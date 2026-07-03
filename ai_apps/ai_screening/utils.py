"""
utils.py — Text cleaning utilities for the AI HR Screening pipeline.

Handles transcript post-processing: filler removal, slang normalization,
and broken sentence repair — while preserving the speaker's original intent.
"""

import re
import logging

logger = logging.getLogger(__name__)

# ── Filler words and phrases to strip ────────────────────────────────────────
FILLER_PATTERNS = [
    r'\b(uh+)\b',
    r'\b(um+)\b',
    r'\b(hmm+)\b',
    r'\b(ah+)\b',
    r'\b(er+)\b',
    r'\b(like,?\s)',          # "like" used as filler (comma-adjacent)
    r'\b(you know,?\s)',
    r'\b(i mean,?\s)',
    r'\b(sort of)\b',
    r'\b(kind of)\b',
    r'\b(basically)\b',
    r'\b(actually)\b',
    r'\b(literally)\b',
    r'\b(right\??\s)',        # trailing "right" used as filler
    r'\b(okay so)\b',
    r'\b(so yeah)\b',
    r'\b(yeah so)\b',
]

# ── Slang → Professional normalizations ─────────────────────────────────────
# Maps informal / Hinglish / internet slang to professional equivalents.
# Order matters: longer phrases first to avoid partial matches.
SLANG_MAP = [
    # Hinglish / code-mixed
    (r'\baccha\b', 'okay'),
    (r'\btheek hai\b', 'alright'),
    (r'\bhaan\b', 'yes'),
    (r'\bnahi\b', 'no'),
    (r'\bkya\b', 'what'),
    (r'\bbhut\b', 'very'),
    (r'\bbahut\b', 'very'),
    (r'\bmatlb\b', 'meaning'),
    (r'\bmatlab\b', 'meaning'),

    # Common English slang
    (r'\bgonna\b', 'going to'),
    (r'\bwanna\b', 'want to'),
    (r'\bgotta\b', 'got to'),
    (r'\bkinda\b', 'kind of'),
    (r'\bsorta\b', 'sort of'),
    (r'\bdunno\b', "don't know"),
    (r'\blemme\b', 'let me'),
    (r'\bcuz\b', 'because'),
    (r'\bcause\b', 'because'),
    (r"\by'all\b", 'you all'),
    (r'\bain\'t\b', 'is not'),
    (r'\bidk\b', "I don't know"),
    (r'\btbh\b', 'to be honest'),
    (r'\bimo\b', 'in my opinion'),
    (r'\bimho\b', 'in my humble opinion'),
    (r'\bbtw\b', 'by the way'),
    (r'\bfyi\b', 'for your information'),
    (r'\basap\b', 'as soon as possible'),
]

# ── Indian Context Corrections ──────────────────────────────────────────────
# Fixes specific regional misinterpretations common in Indian English speech.
INDIAN_CORRECTIONS = {
    "up tech": "B.Tech",
    "you p tech": "B.Tech",
    "be tech": "B.Tech",
    "m tech": "M.Tech",
    "mba": "MBA",
    "bcom": "B.Com",
    "bsc": "B.Sc",
}


def remove_fillers(text: str) -> str:
    """Remove conversational filler words / phrases."""
    for pattern in FILLER_PATTERNS:
        text = re.sub(pattern, ' ', text, flags=re.IGNORECASE)
    return text


def normalize_slang(text: str) -> str:
    """Replace slang and informal language with professional equivalents."""
    for pattern, replacement in SLANG_MAP:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def fix_whitespace(text: str) -> str:
    """Collapse multiple spaces, fix spacing around punctuation."""
    text = re.sub(r'\s+', ' ', text)                    # collapse runs of whitespace
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)        # no space before punctuation
    text = re.sub(r'([.,!?;:])(\w)', r'\1 \2', text)    # space after punctuation
    return text.strip()


def fix_broken_sentences(text: str) -> str:
    """
    Light heuristic to repair broken sentences:
      - Capitalize after sentence-ending punctuation.
      - Ensure the transcript starts with a capital letter.
    Does NOT rewrite content — only fixes casing / whitespace.
    """
    # Capitalize first character
    if text:
        text = text[0].upper() + text[1:]

    # Capitalize after sentence terminators
    text = re.sub(
        r'([.!?])\s+([a-z])',
        lambda m: m.group(1) + ' ' + m.group(2).upper(),
        text,
    )
    return text


def clean_transcript(text: str) -> str:
    """
    Master cleaning function.  Pipeline order:
      1. Remove fillers
      2. Normalize slang → professional language
      3. Fix whitespace
      4. Fix broken sentence casing

    Intent and meaning are preserved throughout.
    """
    if not text or not text.strip():
        logger.warning("Received empty transcript for cleaning.")
        return ""

    logger.info("Cleaning transcript (%d chars)…", len(text))

    text = remove_fillers(text)
    text = normalize_slang(text)

    # Apply Indian Context Corrections
    for wrong, correct in INDIAN_CORRECTIONS.items():
        # Case-insensitive replacement but preserving intent
        text = re.sub(rf'\b{wrong}\b', correct, text, flags=re.IGNORECASE)

    text = fix_whitespace(text)
    text = fix_broken_sentences(text)

    logger.info("Cleaned transcript (%d chars).", len(text))
    return text


def transcript_quality_score(text: str) -> dict:
    """Assess the quality of the transcript based on length and meaningful word ratio."""
    words = text.split()
    length = len(words)

    meaningful_words = [w for w in words if len(w) > 2]
    meaningful_ratio = len(meaningful_words) / max(length, 1)

    score = 0

    if length > 80:
        score += 4
    elif length > 40:
        score += 3
    elif length > 20:
        score += 2
    else:
        score += 1

    if meaningful_ratio > 0.7:
        score += 3
    elif meaningful_ratio > 0.5:
        score += 2
    else:
        score += 1

    return {
        "length": length,
        "meaningful_ratio": round(meaningful_ratio, 2),
        "quality_score": score  # out of 7
    }


def detect_transcription_uncertainty(text: str) -> bool:
    """
    Check for phrases that often indicate Whisper hallucination or errors 
    (e.g., nonsensical regional misinterpretations).
    """
    text_lower = text.lower()

    red_flag_patterns = [
        "up tech",          # likely "b tech"
        "saturday garage",  # nonsensical phrase
        "on october",       # context mismatch
        "nuclear family",   # often hallucinated when audio is low
        "self-reported person",
    ]

    matches = 0
    for phrase in red_flag_patterns:
        if phrase in text_lower:
            matches += 1

    # Trigger if multiple flags or a critical nonsensical phrase
    if matches >= 2 or ("saturday garage" in text_lower):
        return True

    return False


def test_candidates():
    import frappe
    import traceback
    try:
        doc = frappe.get_doc("DocType", "Candidates")
        print("DOC OWNER BEFORE SAVE:", repr(doc.owner))
        doc.save()
        print("Save succeeded!")
    except Exception as e:
        traceback.print_exc()


