"""
evaluator.py — LLM-based candidate evaluation for the AI HR Screening pipeline.

Sends the cleaned transcript to an Ollama-compatible endpoint and returns
a structured JSON hiring decision.

Key design choices:
  - Temperature 0.2 for near-deterministic outputs.
  - Strict system prompt that forbids hallucination.
  - Automatic retry on transient failures.
  - JSON-only output with validation.
"""

import json
import logging
import os
import re

import requests

try:
    from utils import detect_transcription_uncertainty
except ImportError:
    from ai_apps.ai_screening.utils import detect_transcription_uncertainty

logger = logging.getLogger(__name__)

# ── LLM endpoint configuration ──────────────────────────────────────────────
try:
    import frappe
    _site_config = frappe.get_site_config()
except ImportError:
    _site_config = {}

LLM_BASE_URL = _site_config.get("llm_base_url") or os.getenv("LLM_BASE_URL", "https://oma.novelinfra.com")
LLM_API_KEY = _site_config.get("llm_api_key") or os.getenv("LLM_API_KEY")
LLM_MODEL = _site_config.get("llm_model") or os.getenv("LLM_MODEL", "glm-5.2-cloud")
FALLBACK_MODEL = _site_config.get("llm_fallback_model") or os.getenv("LLM_FALLBACK_MODEL", "glm-5.2-cloud")
TEMPERATURE = 0.1
MAX_RETRIES = 2          # 1 initial attempt + 1 retry (now using fallback)
TIMEOUT = 30             # 30 seconds timeout

# ── Frappe-aligned tag taxonomy ─────────────────────────────────────────────
# Sub tags: exactly as stored in Frappe Trait Tags doctype (Tag Type = Sub)
ALLOWED_TAGS = {
    "communication_traits": [
        "Very Unclear", "Cannot Express Ideas", "Broken Responses",
        "Often Pauses", "Low Energy", "Hard to Follow",
        "Basic Structure", "Some Hesitation",
        "Gets Ideas Across", "Stays on Point", "Good Pace", "Easy to Follow",
        "Words Flow Well", "Holds Attention",
        "Speaks Clearly",
    ],
    "behavioral_indicators": [
        "Low Initiative", "Avoids Responsibility", "Seems Nervous",
        "Task Focused", "Holds Back",
        "Eager to Learn", "Team Minded", "Takes Ownership",
    ],
    "experience_assessment": [
        "Knowledge Only", "Minimal Hands-On Work", "Weak Role Fit",
        "Some Relevant Background", "Skills Can Transfer", "Partial Role Fit",
        "Deep Domain Knowledge", "Proven Results", "Strong Role Fit",
        "Handles Stakeholders Well", "Cross-Domain Exposure", "Led Teams or Projects",
    ],
    "professional_readiness": [
        "Needs More Confidence", "Needs Role Exposure", "Needs Coaching",
        "Shows Promise", "Willing to Learn", "Open to Feedback",
        "Handles Responsibility", "Professional Attitude", "Ready to Contribute",
    ],
    "ai_flags": [
        "Needs Human Review", "Incomplete Recording", "Poor Audio Quality",
        "Long Delays", "Uneven Delivery", "Very Hesitant",
        "Rehearsed Answers", "Possible AI Help", "Sounds Scripted",
    ],
}

# ── Main tag derivation maps ──────────────────────────────────────────────────
# Maps sub-tag → its correct Main tag in Frappe.
# Used by frappe_integration.py to write exactly ONE main tag per category.

COMM_SUB_TO_MAIN = {
    "Very Unclear":          "Poor",
    "Cannot Express Ideas":  "Poor",
    "Broken Responses":      "Poor",
    "Often Pauses":          "Below Average",
    "Low Energy":            "Below Average",
    "Hard to Follow":        "Below Average",
    "Basic Structure":       "Average",
    "Some Hesitation":       "Average",
    "Gets Ideas Across":     "Average",
    "Stays on Point":        "Above Average",
    "Good Pace":             "Above Average",
    "Easy to Follow":        "Above Average",
    "Words Flow Well":       "Excellent Communication",
    "Holds Attention":       "Excellent Communication",
    "Speaks Clearly":        "Excellent Communication",
}

BEHAVIORAL_SUB_TO_MAIN = {
    "Low Initiative":        "Risk",
    "Avoids Responsibility": "Risk",
    "Seems Nervous":         "Risk",
    "Holds Back":            "Neutral",
    "Task Focused":          "Neutral",
    "Eager to Learn":        "Positive",
    "Team Minded":           "Positive",
    "Takes Ownership":       "Positive",
}

EXPERIENCE_SUB_TO_MAIN = {
    "Knowledge Only":            "Limited Relevant",
    "Minimal Hands-On Work":     "Limited Relevant",
    "Weak Role Fit":             "Limited Relevant",
    "Some Relevant Background":  "Moderately Relevant",
    "Skills Can Transfer":       "Moderately Relevant",
    "Partial Role Fit":          "Moderately Relevant",
    "Deep Domain Knowledge":     "Highly Relevant",
    "Proven Results":            "Highly Relevant",
    "Strong Role Fit":           "Highly Relevant",
    "Handles Stakeholders Well": "Additional Strengths",
    "Cross-Domain Exposure":     "Additional Strengths",
    "Led Teams or Projects":     "Additional Strengths",
}

PROFESSIONAL_SUB_TO_MAIN = {
    "Needs More Confidence":  "Development Required",
    "Needs Role Exposure":    "Development Required",
    "Needs Coaching":         "Development Required",
    "Shows Promise":          "Growth Potential",
    "Willing to Learn":       "Growth Potential",
    "Open to Feedback":       "Growth Potential",
    "Handles Responsibility": "Workplace Ready",
    "Professional Attitude":  "Workplace Ready",
    "Ready to Contribute":    "Workplace Ready",
}

AIFLAG_SUB_TO_MAIN = {
    "Needs Human Review":    "Technical Review",
    "Incomplete Recording":  "Technical Review",
    "Poor Audio Quality":    "Technical Review",
    "Long Delays":           "Confidence & Delivery",
    "Uneven Delivery":       "Confidence & Delivery",
    "Very Hesitant":         "Confidence & Delivery",
    "Rehearsed Answers":     "Content Authenticity",
    "Possible AI Help":      "Content Authenticity",
    "Sounds Scripted":       "Content Authenticity",
}

# Single lookup used by frappe_integration.py
CATEGORY_SUB_TO_MAIN = {
    "communication_traits":   COMM_SUB_TO_MAIN,
    "behavioral_indicators":  BEHAVIORAL_SUB_TO_MAIN,
    "experience_assessment":  EXPERIENCE_SUB_TO_MAIN,
    "professional_readiness": PROFESSIONAL_SUB_TO_MAIN,
    "ai_flags":               AIFLAG_SUB_TO_MAIN,
}

# ── System prompt (strict, unbiased) ────────────────────────────────────────
SYSTEM_PROMPT = """You are an intelligent HR screening assistant.

Evaluate the candidate using ONLY the spoken introduction transcript below.
Do NOT use any resume or JD context for scoring.


FAIRNESS RULES

- The candidate may be an Indian English speaker. Do NOT penalize accent, grammar, or informal language.
- If the transcript appears broken or mis-transcribed, do NOT assume the candidate is weak — reduce confidence instead.
- Audio quality issues (cuts, noise) must NOT result in harsh score penalties.


SCRIPTED / AI-GENERATED RESPONSE DETECTION

Carefully assess whether the candidate appears to be reading from a prepared script or using AI.

Signs to watch for:
- Pauses at grammatically wrong places suggesting line-by-line reading.
- Word-by-word delivery inconsistent with natural speech rhythm.
- Perfectly structured answers with no hesitation, no personal anecdotes.
- Generic HR buzzwords with no personal substance.
- Extremely formal vocabulary inconsistent with audio delivery.
- No specific personal details — no company names, college names, stories.

How to handle:
- STRONGLY confident scripted: reduce communication and professionalism –0.5 to –1.5, state it in reason.
- PARTIALLY suspicious: reduce minimally –0.3 to –0.5, note it in reason.
- Do NOT reject solely for this.


EVALUATION CRITERIA (transcript only)

Score the candidate (1–10) on:

1. Communication Clarity — are ideas understandable?
2. Structure of Thought — logical flow (intro → details → conclusion)?
3. Confidence (Speech Delivery) — use speech features as secondary signals only.
4. Relevance to Role — does their stated background suit a professional role?
   - If no specific role mentioned, infer from what they described.
   - Credit self-awareness about how background connects to work.
5. Awareness Professional genuine intent, career goals, understanding of working in an organisation? 


UNCERTAINTY HANDLING

If transcript is broken or ASR errors detected:
- Set evaluation_confidence to "low" or "medium".
- Keep scores moderate (5–6). Avoid extreme low scores.
- Route to "Consider" unless clearly poor.


SCORING GUIDELINES

- Use the full 10 range where evidence supports it.1
- Do NOT cluster in the 5–7 band without justification.
- Do NOT score below 4 without strong, clear evidence.
- If genuinely unsure, prefer 5–6 as safe and neutral.


DECISION RULE

Only three decisions:
- "Reject"              → Clearly weak AND transcript is reliable. Use sparingly.
- "Consider"            → Moderate, uncertain, or reasonable. Default for most.
- "Needs Human Review"  → Transcript too broken, audio too poor, signals too mixed.


REASONING REQUIREMENT

- Always reference at least one specific detail from the transcript.
- If scripted response suspected, state it clearly.
- If uncertainty exists due to audio, state: "Some parts appear unclear, possibly due to audio quality."


ACCENT & MOTHER TONGUE INFLUENCE (MTI) DETECTION

Evaluate the candidate's spoken accent and the influence of their native mother tongue (MTI):
- "accent": Identify the specific accent (e.g. "Indian English (South Indian)", "Indian English (North Indian)", "Indian English (Neutral)", "Neutral / Global English", "American English", "British English").
- "mother_tongue_influence": A concise explanation in MAXIMUM 140 CHARACTERS explaining how mother tongue influence affects their spoken delivery, phonetics, intonation, or pacing.
  CRITICAL: Must strictly be ≤ 140 characters.
- "mother_tongue_influence_percentage": An estimated percentage rating of MTI intensity (e.g. "15%", "35%", "55%"):
  * 0%–15%: Negligible / Neutral English (minimal to no regional phonetics)
  * 16%–35%: Mild MTI (clear, easy to follow, subtle regional cadence)
  * 36%–60%: Moderate MTI (noticeable regional inflection or pronunciation, good intelligibility)
  * 61%–100%: Heavy MTI (strong regional accent, noticeable pronunciation shifts)


OUTPUT FORMAT (JSON ONLY — no markdown, no preamble)

{
  "scores": {
    "communication": float,
    "confidence": float,
    "structure": float,
    "relevance": float,
    "professionalism": float
  },
  "final_score": float,
  "decision": "Reject | Consider | Needs Human Review",
  "reason": "...",
  "evaluation_confidence": "low | medium | high",
  "accent": "...",
  "mother_tongue_influence": "... (max 140 chars)",
  "mother_tongue_influence_percentage": "XX%"
}"""

#---

TAG_SYSTEM_PROMPT = """You are an HR tag classifier. You will receive:
1. A candidate's spoken transcript (already scored separately — do NOT re-score).
2. A Job Description (JD) — may be absent.
3. A structured Resume Summary — may be absent.

Your ONLY task: select sub-tags from the predefined lists below.

─────────────────────────────────────────
SELECTION RULES
─────────────────────────────────────────
RULE 1 — Evidence required.
Select a sub-tag ONLY when you have clear evidence from the transcript, JD match, or resume.
Do NOT select tags as defaults or because they seem neutral.

RULE 2 — Communication tier: ONE tier only, anchored to acoustic evidence.
The 15 communication sub-tags are grouped into 5 tiers:
  Tier 1 (Poor):          Very Unclear, Cannot Express Ideas, Broken Responses,
                          Often Pauses, Low Energy, Hard to Follow
  Tier 2 (Below Average): Basic Structure, Some Hesitation
  Tier 3 (Average):       Gets Ideas Across, Stays on Point, Good Pace, Easy to Follow
  Tier 4 (Above Average): Words Flow Well, Holds Attention
  Tier 5 (Excellent):     Speaks Clearly

CRITICAL TIER ANCHORING RULES:
- If speech features show high pause_ratio OR low energy OR low speaking_rate
  → stay in Tier 1 or Tier 2. Do NOT select Tier 4 or 5.
- If the transcript is hesitant, broken, or contains filler words
  → stay in Tier 1 or Tier 2.
- Tier 4 (Above Average) requires: fluent delivery + good pace + easy to follow.
  All three must be present. One positive signal alone is NOT sufficient.
- Tier 5 (Excellent) requires: exceptionally clear, confident, well-structured delivery.
  This should be rare — fewer than 10% of candidates qualify.
- Select sub-tags from ONE tier only.
  Do NOT mix tiers under any circumstance.

RULE 3 — Experience: ONE fit verdict only.
The experience sub-tags have three fit tiers:
  Weak fit:     Knowledge Only, Minimal Hands-On Work, Weak Role Fit
  Moderate fit: Some Relevant Background, Skills Can Transfer, Partial Role Fit
  Strong fit:   Deep Domain Knowledge, Proven Results, Strong Role Fit
  Strengths:    Handles Stakeholders Well, Cross-Domain Exposure, Led Teams or Projects

Pick ONE fit tier (weak / moderate / strong) based on resume + JD evidence.
You may additionally add Strengths sub-tags if the resume explicitly supports them.
Do NOT mix fit tiers (e.g. "Weak Role Fit" + "Strong Role Fit" is invalid).

RULE 4 — Behavioral: transcript signals only.
Only select behavioral sub-tags when the transcript itself shows behavioral signals.
Resume alone is not sufficient evidence for behavioral tags.

RULE 5 — AI Flags: only when clearly warranted.
Apply AI flag sub-tags only when the transcript or audio delivery clearly shows the signal.
Do NOT apply speculatively.

RULE 6 — Minimum is zero.
Returning an empty array [] for any category is valid when evidence is absent.

─────────────────────────────────────────
ALLOWED SUB-TAGS (exact strings — no paraphrasing, no new tags)
─────────────────────────────────────────
communication_traits:
["Very Unclear", "Cannot Express Ideas", "Broken Responses", "Often Pauses", "Low Energy",
 "Hard to Follow", "Basic Structure", "Some Hesitation", "Gets Ideas Across", "Stays on Point",
 "Good Pace", "Easy to Follow", "Words Flow Well", "Holds Attention", "Speaks Clearly"]

behavioral_indicators:
["Low Initiative", "Avoids Responsibility", "Seems Nervous", "Task Focused", "Holds Back",
 "Eager to Learn", "Team Minded", "Takes Ownership"]

experience_assessment:
["Knowledge Only", "Minimal Hands-On Work", "Weak Role Fit",
 "Some Relevant Background", "Skills Can Transfer", "Partial Role Fit",
 "Deep Domain Knowledge", "Proven Results", "Strong Role Fit",
 "Handles Stakeholders Well", "Cross-Domain Exposure", "Led Teams or Projects"]

professional_readiness:
["Needs More Confidence", "Needs Role Exposure", "Needs Coaching",
 "Shows Promise", "Willing to Learn", "Open to Feedback",
 "Handles Responsibility", "Professional Attitude", "Ready to Contribute"]

ai_flags:
["Needs Human Review", "Incomplete Recording", "Poor Audio Quality",
 "Long Delays", "Uneven Delivery", "Very Hesitant",
 "Rehearsed Answers", "Possible AI Help", "Sounds Scripted"]

─────────────────────────────────────────
OUTPUT FORMAT (JSON ONLY — no markdown, no preamble)
─────────────────────────────────────────
{
  "communication_traits": [...],
  "behavioral_indicators": [...],
  "experience_assessment": [...],
  "professional_readiness": [...],
  "ai_flags": [...]
}"""


def _build_user_prompt(transcript: str, low_confidence: bool = False) -> str:
    """Build the user message containing the transcript."""
    prefix = ""
    if low_confidence:
        prefix = (
            "[NOTE: This transcript is very short and may indicate low audio quality. "
            "Evaluate only what is present; do not speculate.]\n\n"
        )
    
    return f"{prefix}Candidate Transcript:\n\n{transcript}"


def _build_user_prompt_with_speech(transcript: str, speech_features: dict, low_confidence: bool = False) -> str:
    """Build the user message containing the transcript and speech metadata."""
    prefix = ""
    if low_confidence:
        prefix = (
            "[NOTE: This transcript is very short and may indicate low audio quality. "
            "Evaluate only what is present; do not speculate.]\n\n"
        )
    
    features_str = (
        f"Speech Delivery Indicators:\n"
        f"- Energy: {speech_features.get('energy')}\n"
        f"- Speaking Rate: {speech_features.get('speaking_rate')}\n"
        f"- Pause Ratio: {speech_features.get('pause_ratio')}\n\n"
    )
    
    return f"{prefix}{features_str}Candidate Transcript:\n\n{transcript}"


def _extract_json(text: str) -> dict | None:
    """
    Extract the first valid JSON object from the LLM response.
    Handles cases where the model wraps JSON in markdown fences or adds preamble.
    """
    # Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Try to find JSON within markdown code fences
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find any JSON object in the text
    json_match = re.search(r'\{[^{}]*"scores"[^{}]*\{[^{}]*\}[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _validate_result(result: dict) -> bool:
    """
    Validate the structure of the LLM evaluation result.
    Returns True if the result has all required fields with correct types, including recruiter tag arrays.
    """
    # Guarantee accent and MTI fields with strict 140 character limit
    accent = str(result.get("accent") or "Indian (Neutral)").strip()
    result["accent"] = accent[:140]

    mti = str(result.get("mother_tongue_influence") or "Mild regional cadence with good overall intelligibility.").strip()
    if len(mti) > 140:
        mti = mti[:137] + "..."
    result["mother_tongue_influence"] = mti

    pct = str(result.get("mother_tongue_influence_percentage") or "20%").strip()
    if not pct.endswith("%") and pct.isdigit():
        pct = f"{pct}%"
    result["mother_tongue_influence_percentage"] = pct

    if result.get("decision") == "Needs Human Review":
        return True

    required_scores = ["communication", "confidence", "structure", "relevance", "professionalism"]

    if "scores" not in result or not isinstance(result["scores"], dict):
        return False

    for key in required_scores:
        val = result["scores"].get(key)
        if val is None or not isinstance(val, (int, float)):
            return False
        if not (0 <= val <= 10):
            return False

    if "final_score" not in result or not isinstance(result["final_score"], (int, float)):
        return False

    if "decision" not in result or result["decision"] not in ("Reject", "Consider", "Needs Human Review"):
        return False

    if "reason" not in result or not isinstance(result["reason"], str):
        return False

    return True


def _build_result(candidate_result: dict) -> dict:
    """
    Map the pipeline output dict to the shape expected by the caller, including recruiter tag arrays.
    """
    evaluation = candidate_result.get("evaluation") or {}
    return {
        "transcript":          candidate_result.get("transcript"),
        "cleaned_transcript":  candidate_result.get("cleaned_transcript"),
        "evaluation":          evaluation,
        "calibrated_score":    candidate_result.get("calibrated_score"),
        "decision":            candidate_result.get("calibrated_decision") or evaluation.get("decision"),
        "confidence":          candidate_result.get("evaluation_confidence"),
        # Recruiter tags – ensure defaults to empty list if missing
        "communication_traits": candidate_result.get("communication_traits", []),
        "behavioral_indicators": candidate_result.get("behavioral_indicators", []),
        "experience_assessment": candidate_result.get("experience_assessment", []),
        "professional_readiness": candidate_result.get("professional_readiness", []),
        "ai_flags":              candidate_result.get("ai_flags", []),
        # Populated by format_output() in run_ai_screening()
        "ai_remarks":          None,
        "ai_priority":         None,
    }


def _recalculate_score(result: dict) -> dict:
    """
    Recalculate the final score as the true average of the five sub-scores
    and re-derive the decision.  This guards against LLM arithmetic errors.
    """
    scores = result["scores"]
    # Clamping and rounding sub-scores
    for key in scores:
        scores[key] = round(max(1.0, min(10.0, float(scores[key]))), 1)

    avg = round(
        (
            scores["communication"]
            + scores["confidence"]
            + scores["structure"]
            + scores["relevance"]
            + scores["professionalism"]
        ) / 5,
        1,
    )
    result["final_score"] = avg

    # Re-derive decision from the corrected average
    if result.get("decision") == "Needs Human Review":
        pass  # Keep as is
    elif avg < 5:
        result["decision"] = "Reject"
    else:
        result["decision"] = "Consider"  # Scores above 7.2 are still "Consider" — score speaks for itself

    return result


def compute_evaluation_confidence(transcript: str, quality: dict) -> str:
    """Determine confidence level based on transcript length and quality score."""
    if quality["length"] < 20:
        return "low"
    if quality["quality_score"] <= 3:
        return "low"
    if quality["quality_score"] <= 5:
        return "medium"
    return "high"


def _enforce_tag_hierarchy(result: dict) -> dict:
    """
    Deterministic post-processing:
    1. Communication — keep only the single dominant tier's sub-tags.
    2. Experience — keep only one fit tier's sub-tags (Strengths are additive).
    3. Behavioral — remove contradicting polarity tags.
    4. Professional Readiness — remove contradicting readiness tags.
    """
    # ── 1. Communication: enforce single tier ────────────────────────────────
    comm_tags = result.get("communication_traits", [])
    if comm_tags:
        tier_groups = [
            ["Very Unclear", "Cannot Express Ideas", "Broken Responses",
             "Often Pauses", "Low Energy", "Hard to Follow"],          # Poor
            ["Basic Structure", "Some Hesitation"],                     # Below Average
            ["Gets Ideas Across", "Stays on Point",
             "Good Pace", "Easy to Follow"],                            # Average
            ["Words Flow Well", "Holds Attention"],                     # Above Average
            ["Speaks Clearly"],                                         # Excellent
        ]
        tier_sets = [set(t) for t in tier_groups]
        tier_counts = [len(set(comm_tags) & t) for t in tier_sets]
        best = tier_counts.index(max(tier_counts))
        result["communication_traits"] = [
            t for t in comm_tags if t in tier_sets[best]
        ]

    # ── 2. Experience: enforce single fit tier (Strengths additive) ──────────
    exp_tags = result.get("experience_assessment", [])
    if exp_tags:
        fit_tiers = [
            {"Knowledge Only", "Minimal Hands-On Work", "Weak Role Fit"},
            {"Some Relevant Background", "Skills Can Transfer", "Partial Role Fit"},
            {"Deep Domain Knowledge", "Proven Results", "Strong Role Fit"},
        ]
        strengths = {"Handles Stakeholders Well", "Cross-Domain Exposure", "Led Teams or Projects"}

        tier_counts = [len(set(exp_tags) & t) for t in fit_tiers]
        best = tier_counts.index(max(tier_counts))

        # Keep only best fit tier + any strengths
        result["experience_assessment"] = [
            t for t in exp_tags
            if t in fit_tiers[best] or t in strengths
        ]

    # ── 3. Behavioral: remove contradicting polarity ──────────────────────────
    beh_tags = result.get("behavioral_indicators", [])
    risk_tags     = {"Low Initiative", "Avoids Responsibility", "Seems Nervous", "Holds Back"}
    positive_tags = {"Eager to Learn", "Team Minded", "Takes Ownership"}
    has_risk     = bool(set(beh_tags) & risk_tags)
    has_positive = bool(set(beh_tags) & positive_tags)
    if has_risk and has_positive:
        # Conservative: keep risk, drop positive
        result["behavioral_indicators"] = [
            t for t in beh_tags if t not in positive_tags
        ]

    # ── 4. Professional Readiness: remove contradicting readiness ────────────
    prof_tags = result.get("professional_readiness", [])
    if "Ready to Contribute" in prof_tags and (
        "Needs Coaching" in prof_tags or "Needs Role Exposure" in prof_tags
    ):
        result["professional_readiness"] = [
            t for t in prof_tags if t != "Ready to Contribute"
        ]

    return result





def _build_tag_prompt(transcript: str, jd_text: str = None, resume_summary: str = None, speech_features: dict = None) -> str:
    parts = [f"Candidate Transcript:\n\n{transcript}"]
    if speech_features:
        parts.append(f"Acoustic Delivery Signals (Use these to strictly cap communication tiers!):\n"
                     f"- Pause Ratio (higher = hesitant): {speech_features.get('pause_ratio', 0):.2f}\n"
                     f"- Speaking Rate (words/min, <130 = slow): {speech_features.get('speaking_rate', 0):.0f}\n"
                     f"- Low Energy Detected: {'Yes' if speech_features.get('low_energy') else 'No'}")
    if jd_text:
        parts.append(f"Job Description:\n\n{jd_text}")
    if resume_summary:
        parts.append(f"Resume Summary:\n\n{resume_summary}")
    if not jd_text and not resume_summary:
        parts.append("[No JD or Resume provided. Use transcript only for tag selection.]")
    return "\n\n".join(parts)


def evaluate_tags(
    transcript: str,
    jd_text: str = None,
    resume_summary: str = None,
    speech_features: dict = None,
) -> dict:
    """
    Separate LLM pass for tag selection only.
    Uses transcript + JD + resume + acoustic signals. Does NOT influence scores or priority.
    Returns a dict with the five tag arrays. Falls back to empty lists on failure.
    """
    EMPTY_TAGS = {
        "communication_traits": [],
        "behavioral_indicators": [],
        "experience_assessment": [],
        "professional_readiness": [],
        "ai_flags": [],
    }

    if not transcript or not transcript.strip():
        return EMPTY_TAGS

    user_prompt = _build_tag_prompt(
        transcript, 
        jd_text=jd_text, 
        resume_summary=resume_summary, 
        speech_features=speech_features
    )

    payload = {
        "messages": [
            {"role": "system", "content": TAG_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,   # more deterministic for classification
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
        payload["model"] = current_model
        if attempt > 1:
            logger.info("evaluate_tags: switching to fallback model %s", current_model)

        logger.info("Tag evaluation attempt %d/%d with model %s…", attempt, MAX_RETRIES, current_model)

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
            response.raise_for_status()

            data = response.json()
            raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not raw_content:
                logger.warning("evaluate_tags: empty response (attempt %d).", attempt)
                continue

            result = _extract_json(raw_content)
            if not result or not isinstance(result, dict):
                logger.warning("evaluate_tags: could not parse JSON (attempt %d).", attempt)
                continue

            # Hard enforce closed tag lists — exact match only
            cleaned = {}
            for tag_key, allowed_list in ALLOWED_TAGS.items():
                raw_tags = result.get(tag_key, [])
                if not isinstance(raw_tags, list):
                    cleaned[tag_key] = []
                    continue
                cleaned[tag_key] = [
                    t.strip() for t in raw_tags
                    if isinstance(t, str) and t.strip() in allowed_list
                ]

            cleaned = _enforce_tag_hierarchy(cleaned)  # reuse existing hierarchy rules

            logger.info("Tag evaluation complete: %s", cleaned)
            return cleaned

        except requests.exceptions.Timeout:
            logger.warning("evaluate_tags: timed out (attempt %d).", attempt)
        except Exception as exc:
            logger.error("evaluate_tags: unexpected error (attempt %d): %s", attempt, exc)

    logger.error("evaluate_tags: failed after %d attempts — returning empty tags.", MAX_RETRIES)
    return EMPTY_TAGS


def evaluate_candidate(
    transcript: str,
    quality: dict,
    speech_features: dict = None,
    jd_text: str = None,
    resume_summary: str = None,
) -> dict | None:
    """
    Send the transcript to the LLM for evaluation.
    """
    if not transcript or not transcript.strip():
        logger.error("Cannot evaluate an empty transcript.")
        return None

    # Handle very short transcripts — route to Consider with low confidence rather than hard-blocking
    if quality["length"] < 15:
        logger.info("Very short transcript detected (length < 15 words) — routing to Consider with low confidence.")
        return {
            "scores": {},
            "final_score": 0,
            "decision": "Needs Human Review",
            "reason": "Candidate response too short to reliably evaluate. A human should review the original audio.",
            "evaluation_confidence": "low",
            "accent": "Unclear / Incomplete",
            "mother_tongue_influence": "Audio too short to evaluate mother tongue influence.",
            "mother_tongue_influence_percentage": "N/A",
        }

    # Handle Transcription Uncertainty (Fairness Override)
    if detect_transcription_uncertainty(transcript):
        logger.warning("Transcription uncertainty detected → routed to human review: %s...", transcript[:50])
        return {
            "scores": {},
            "final_score": 0,
            "decision": "Needs Human Review",
            "reason": "Potential transcription error detected (red-flag patterns found). Evaluation may be unreliable.",
            "evaluation_confidence": "low",
            "accent": "Unclear / Audio Artifacts",
            "mother_tongue_influence": "Audio clarity uncertain; MTI could not be evaluated reliably.",
            "mother_tongue_influence_percentage": "N/A",
        }

    if speech_features:
        user_prompt = _build_user_prompt_with_speech(transcript, speech_features, low_confidence=False)
    else:
        user_prompt = _build_user_prompt(transcript, low_confidence=False)

    confidence = compute_evaluation_confidence(transcript, quality)

    # Base payload structure
    base_payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": TEMPERATURE,
        "top_p": 0.9,
        "frequency_penalty": 0.1,
        "seed": 42,
    }

    url = f"{LLM_BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }

    for attempt in range(1, MAX_RETRIES + 1):
        # Switch to fallback model on retry
        current_model = LLM_MODEL if attempt == 1 else FALLBACK_MODEL
        if attempt > 1:
            logger.info("Using fallback model: %s", current_model)

        logger.info("LLM evaluation attempt %d/%d with model %s…", attempt, MAX_RETRIES, current_model)
        
        payload = base_payload.copy()
        payload["model"] = current_model

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
            response.raise_for_status()

            data = response.json()
            raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not raw_content:
                logger.warning("Empty LLM response on attempt %d.", attempt)
                continue

            # Extract and validate JSON
            result = _extract_json(raw_content)
            if result is None:
                logger.warning(
                    "Could not parse JSON from LLM response (attempt %d):\n%s",
                    attempt, raw_content[:500],
                )
                continue

            if not _validate_result(result):
                logger.warning(
                    "Invalid result structure (attempt %d): %s",
                    attempt, json.dumps(result, indent=2)[:500],
                )
                continue

            # Recalculate score to prevent LLM arithmetic mistakes
            if result["decision"] != "Needs Human Review":
                result = _recalculate_score(result)
            else:
                result["final_score"] = result.get("final_score", 0)
            
            result["evaluation_confidence"] = confidence

            # (Tag validation removed since this pass no longer selects tags)

            logger.info(
                "Evaluation complete — Score: %.2f  Decision: %s  Confidence: %s",
                result.get("final_score", 0) or 0, result["decision"], confidence,
            )
            return result

        except requests.exceptions.Timeout:
            logger.warning("LLM request timed out (attempt %d).", attempt)
        except requests.exceptions.ConnectionError:
            logger.error("Cannot reach LLM endpoint: %s", url)
        except requests.exceptions.HTTPError as exc:
            logger.error("LLM HTTP error (attempt %d): %s", attempt, exc)
        except Exception as exc:
            logger.error("Unexpected error during LLM evaluation (attempt %d): %s", attempt, exc)

    logger.error("LLM evaluation failed after %d attempts.", MAX_RETRIES)
    return None


# ── Output Formatter ──────────────────────────────────────────────────────────

def is_us_process_role(*role_strings) -> bool:
    """
    Check if any given role/position/JD strings indicate a US-process / US-facing voice role.
    """
    keywords = [
        "us process", "bdm us", "us bdm", "us sales", "us shift",
        "international voice", "us it recruiter", "us recruiter",
        "us staffing", "us account", "us client", "(us", "- us", "us -"
    ]
    for r in role_strings:
        if not r:
            continue
        r_lower = str(r).lower()
        if any(k in r_lower for k in keywords):
            return True
    return False


REMARKS_SYSTEM_PROMPT = """You are a senior HR evaluator writing a formal candidate screening note.

You will receive a structured evaluation summary of a candidate (score, decision, confidence, reasoning, applied_role, accent, and mother tongue influence).
Your task: write a cohesive, professional HR screening paragraph and assign a priority tier.
OUTPUT FORMAT (strict JSON only — no markdown, no explanation, no preamble):
{
  "ai_remarks": "<A single cohesive paragraph of HR evaluation>",
  "ai_priority": "P1 | P2 | P3 | P4 | P5"
}

─────────────────────────────────────────
REMARKS RULES
─────────────────────────────────────────
- 5–7 lines maximum. No repetition. No filler phrases.
- Do NOT copy or quote the reason text directly — synthesize it into HR language.
- Write like a senior HR professional, not an AI system.
- Avoid all technical terms (e.g. "evaluation_confidence", "LLM", "score", "float").

STRUCTURE (follow this order):
1. Brief candidate profile summary (education, experience level — inferred from reason)
2. Key strengths (communication, relevance, skills demonstrated)
3. Key concerns (gaps, delivery issues, uncertainty flags)
4. Final decision insight (overall fit and readiness, including role-specific voice fit)
5. FINAL LINE (mandatory): "Priority: PX — <short justification>"

─────────────────────────────────────────
ROLE-AWARE ACCENT & MTI PRIORITY ADJUSTMENT (CRITICAL)
─────────────────────────────────────────
Check if the candidate's applied role/position is US-process based (e.g., "BDM US", "Business Development Manager (US Process)", "International Voice Process", "US Sales", "US IT Recruiter", etc.):
- IF APPLIED ROLE IS US PROCESS BASED:
  Communication clarity, pronunciation, and accent intelligibility are decisive for client-facing conversions.
  * Heavy / High MTI (≥ 45% or strong regional accent):
    -> DECREASE priority by 1 tier (e.g. P1 → P2, P2 → P3, P3 → P4).
    -> In remarks, explicitly state that the accent / elevated mother tongue influence (XX%) poses an intelligibility barrier for US client-facing calls.
  * Low / Clean MTI (≤ 25%, neutral, global, or clear North American-friendly diction) with solid communication:
    -> IMPROVE priority by 1 tier (e.g. P3 → P2, or P2 → P1).
    -> In remarks, explicitly highlight that the clear accent and low mother tongue influence (XX%) provide strong voice suitability for US client calls.
  * Moderate MTI (30%–40%):
    -> Maintain baseline priority, noting cadence suitability for client interaction.
- IF ROLE IS NOT US PROCESS BASED (domestic, technical, back-office):
  * Do NOT penalize or boost priority based on accent/MTI as long as general intelligibility is acceptable.

─────────────────────────────────────────
SCRIPT / AI DETECTION
─────────────────────────────────────────
If the evaluation reason mentions a scripted or AI-generated response:
- Insert this line (soft phrasing only): "Response appears partially structured or externally assisted."
- NEVER use definitive accusations. NEVER say "candidate used AI" or "cheated".
- Keep it professional and neutral.

─────────────────────────────────────────
PRIORITY MAPPING
─────────────────────────────────────────
P1 → Strong Hire: confidence=high AND score ≥ 8.0
P2 → Good Candidate: minor gaps, score 6.5–7.9
P3 → Average: needs further evaluation, score 5.0–6.4
P4 → Needs Human Review: decision is "Needs Human Review" OR confidence is "low"
P5 → Reject: score < 5.0 AND decision is "Reject"

STRICT OVERRIDE RULES (apply in this order, highest priority first):
1. If decision is "Needs Human Review" → always P4 (ignore score)
2. If confidence is "low"             → never P1 or P2 → minimum P4
3. If score < 5.0                     → P5
4. If score 5.0–6.4                   → P3
5. If score 6.5–7.9                   → P2
6. If score ≥ 8.0 AND confidence=high → P1

─────────────────────────────────────────
TONE
─────────────────────────────────────────
Professional. Neutral. Non-judgmental. Actionable.
No AI/technical language. No overly harsh language.

Do NOT include any text outside the JSON object."""


def format_output(
    decision: str,
    final_score: float,
    confidence: str,
    reason: str,
    applied_role: str | None = None,
    accent: str | None = None,
    mother_tongue_influence: str | None = None,
    mother_tongue_influence_percentage: str | None = None,
) -> dict | None:
    """
    Make a lightweight second LLM call to convert the raw evaluation into a
    professional HR-grade remark and priority tier (P1–P5), taking into account
    role-specific accent and mother tongue influence criteria.

    Parameters
    ----------
    decision : str
        Calibrated decision: "Consider", "Reject", or "Needs Human Review".
    final_score : float
        Calibrated final score (0–10).
    confidence : str
        Evaluation confidence level: "low", "medium", or "high".
    reason : str
        The original LLM evaluation reason/explanation text.
    applied_role : str, optional
        Target role applied for (e.g. "Business Development Manager (US Process)").
    accent : str, optional
        Detected accent name.
    mother_tongue_influence : str, optional
        Description of mother tongue influence.
    mother_tongue_influence_percentage : str, optional
        Percentage rating of MTI (e.g. "40%").

    Returns
    -------
    dict | None
        {"ai_remarks": "...", "ai_priority": "PX"}, or None on failure.
    """
    import json as _json

    context_dict = {
        "decision": decision,
        "final_score": round(float(final_score or 0), 2),
        "confidence": confidence,
        "reason": reason,
    }
    if applied_role:
        context_dict["applied_role"] = applied_role
    if accent:
        context_dict["accent"] = accent
    if mother_tongue_influence:
        context_dict["mother_tongue_influence"] = mother_tongue_influence
    if mother_tongue_influence_percentage:
        context_dict["mother_tongue_influence_percentage"] = mother_tongue_influence_percentage

    context = _json.dumps(context_dict, indent=2)

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": REMARKS_SYSTEM_PROMPT},
            {"role": "user", "content": f"Candidate Evaluation Summary:\n\n{context}"},
        ],
        "temperature": 0.3,
        "top_p": 0.9,
        "seed": 42,
    }

    url = f"{LLM_BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    VALID_PRIORITIES = {"P1", "P2", "P3", "P4", "P5"}

    for attempt in range(1, MAX_RETRIES + 1):
        current_model = LLM_MODEL if attempt == 1 else FALLBACK_MODEL
        if attempt > 1:
            payload["model"] = current_model
            logger.info("format_output: switching to fallback model %s", current_model)

        logger.info("format_output: attempt %d/%d with model %s…", attempt, MAX_RETRIES, current_model)

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
            response.raise_for_status()

            data = response.json()
            raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not raw_content:
                logger.warning("format_output: empty LLM response (attempt %d).", attempt)
                continue

            result = _extract_json(raw_content)
            if result is None:
                logger.warning(
                    "format_output: could not parse JSON (attempt %d): %s",
                    attempt, raw_content[:300],
                )
                continue

            ai_remarks = result.get("ai_remarks", "")
            ai_priority = str(result.get("ai_priority", "")).strip()

            if ai_priority not in VALID_PRIORITIES:
                logger.warning(
                    "format_output: invalid priority value '%s' (attempt %d).",
                    ai_priority, attempt,
                )
                continue

            if not ai_remarks or not isinstance(ai_remarks, str):
                logger.warning("format_output: missing or invalid ai_remarks (attempt %d).", attempt)
                continue

            # Deterministic enforcement for US Process roles
            if is_us_process_role(applied_role):
                try:
                    pct_val = float(str(mother_tongue_influence_percentage or "").replace("%", "").strip())
                except (ValueError, TypeError):
                    pct_val = 30.0

                p_order = ["P1", "P2", "P3", "P4", "P5"]
                current_idx = p_order.index(ai_priority) if ai_priority in p_order else 2

                if pct_val >= 45.0:
                    # Downgrade by 1 tier if not already downgraded
                    if current_idx < 3:
                        ai_priority = p_order[current_idx + 1]
                    if "US" not in ai_remarks and "accent" not in ai_remarks.lower() and "mother tongue" not in ai_remarks.lower():
                        ai_remarks = ai_remarks.rstrip() + f" Regional mother tongue influence ({pct_val:.0f}%) presents an intelligibility consideration for a US-facing process."
                elif pct_val <= 25.0 and decision == "Consider" and confidence == "high":
                    # Upgrade by 1 tier
                    if current_idx > 0 and current_idx <= 2:
                        ai_priority = p_order[current_idx - 1]
                    if "US" not in ai_remarks and "accent" not in ai_remarks.lower() and "mother tongue" not in ai_remarks.lower():
                        ai_remarks = ai_remarks.rstrip() + f" Clear accent with minimal mother tongue influence ({pct_val:.0f}%) is well-suited for US client-facing calls."

            logger.info(
                "format_output complete — Priority: %s | Remarks preview: %.80s",
                ai_priority, ai_remarks,
            )
            return {"ai_remarks": ai_remarks.strip(), "ai_priority": ai_priority}

        except requests.exceptions.Timeout:
            logger.warning("format_output: request timed out (attempt %d).", attempt)
        except requests.exceptions.ConnectionError:
            logger.error("format_output: cannot reach LLM endpoint: %s", url)
        except requests.exceptions.HTTPError as exc:
            logger.error("format_output: HTTP error (attempt %d): %s", attempt, exc)
        except Exception as exc:
            logger.error("format_output: unexpected error (attempt %d): %s", attempt, exc)

    logger.error("format_output: failed after %d attempts.", MAX_RETRIES)
    return None
