import re
import sys

with open('/home/frappe/frappe-bench/apps/ai_apps/ai_apps/ai_screening/evaluator.py', 'r') as f:
    content = f.read()

# 1. Replace SYSTEM_PROMPT and add TAG_SYSTEM_PROMPT
system_prompt_pattern = re.compile(r'SYSTEM_PROMPT = """You are an intelligent HR screening assistant\..*?Do NOT include any text outside the JSON object\. No markdown fences, no explanation, no preamble\."""', re.DOTALL)

NEW_PROMPTS = '''SYSTEM_PROMPT = """You are an intelligent HR screening assistant.

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
  "evaluation_confidence": "low | medium | high"
}"""


TAG_SYSTEM_PROMPT = """You are an HR tag classifier. You will receive:
1. A candidate's spoken transcript (already evaluated for scores separately).
2. A Job Description (JD) — may be absent.
3. A structured Resume Summary — may be absent.

Your task: select tags from the predefined taxonomy below.


RULES

- Select tags ONLY when you have clear evidence from at least one of: transcript, JD match, or resume facts.
- Do NOT select a tag as a default or because it is neutral.
- Do NOT select contradicting tier tags together (e.g. "Strong Role Fit" AND "Weak Role Fit").
- Communication trait tier: select ONE tier only — the one best supported by the transcript.
  Tiers: Low (Very Unclear / Cannot Express / Broken / Often Pauses / Low Energy / Hard to Follow),
         Mid (Basic Structure / Some Hesitation / Gets Ideas Across / Stays on Point / Good Pace / Easy to Follow),
         High (Words Flow Well / Holds Attention / Speaks Clearly).
- Experience tags: only apply higher-tier tags (Deep Domain Knowledge, Strong Role Fit, Led Teams)
  when resume AND transcript both support it, or resume alone provides hard evidence.
- Behavioral tags: only when the transcript contains behavioral signals. Resume alone is not enough.
- AI flags: only apply when the transcript or audio signals clearly warrant it.
- Minimum: 0 tags per category is valid if there is no evidence.


ALLOWED TAGS (exact strings only — no paraphrasing, no new tags)

communication_traits:
["Very Unclear", "Cannot Express Ideas", "Broken Responses", "Often Pauses", "Low Energy",
 "Hard to Follow", "Basic Structure", "Some Hesitation", "Gets Ideas Across", "Stays on Point",
 "Good Pace", "Easy to Follow", "Words Flow Well", "Holds Attention", "Speaks Clearly"]

behavioral_indicators:
["Low Initiative", "Avoids Responsibility", "Seems Nervous", "Task Focused", "Holds Back",
 "Eager to Learn", "Team Minded", "Takes Ownership"]

experience_assessment:
["Handles Stakeholders Well", "Cross-Domain Exposure", "Led Teams or Projects",
 "Knowledge Only", "Minimal Hands-On Work", "Weak Role Fit",
 "Some Relevant Background", "Skills Can Transfer", "Partial Role Fit",
 "Deep Domain Knowledge", "Proven Results", "Strong Role Fit"]

professional_readiness:
["Needs More Confidence", "Needs Role Exposure", "Needs Coaching",
 "Shows Promise", "Willing to Learn", "Open to Feedback",
 "Handles Responsibility", "Professional Attitude", "Ready to Contribute"]

ai_flags:
["Needs Human Review", "Incomplete Recording", "Poor Audio Quality",
 "Long Delays", "Uneven Delivery", "Very Hesitant",
 "Rehearsed Answers", "Possible AI Help", "Sounds Scripted"]


OUTPUT FORMAT (JSON ONLY — no markdown, no preamble)

{
  "communication_traits": [...],
  "behavioral_indicators": [...],
  "experience_assessment": [...],
  "professional_readiness": [...],
  "ai_flags": [...]
}"""'''

content = system_prompt_pattern.sub(NEW_PROMPTS, content)

# 2. Update _build_user_prompt
content = content.replace(
'''def _build_user_prompt(transcript: str, low_confidence: bool = False, resume_summary: str = None) -> str:
    """Build the user message containing the transcript."""
    prefix = ""
    if low_confidence:
        prefix = (
            "[NOTE: This transcript is very short and may indicate low audio quality. "
            "Evaluate only what is present; do not speculate.]\\n\\n"
        )
    
    resume_block = f"Candidate Resume Summary:\\n\\n{resume_summary}\\n\\n" if resume_summary else ""
    return f"{prefix}{resume_block}Candidate Transcript:\\n\\n{transcript}"''',
'''def _build_user_prompt(transcript: str, low_confidence: bool = False) -> str:
    """Build the user message containing the transcript."""
    prefix = ""
    if low_confidence:
        prefix = (
            "[NOTE: This transcript is very short and may indicate low audio quality. "
            "Evaluate only what is present; do not speculate.]\\n\\n"
        )
    
    return f"{prefix}Candidate Transcript:\\n\\n{transcript}"''')

# 3. Update _build_user_prompt_with_speech
content = content.replace(
'''def _build_user_prompt_with_speech(transcript: str, speech_features: dict, low_confidence: bool = False, resume_summary: str = None) -> str:
    """Build the user message containing the transcript and speech metadata."""
    prefix = ""
    if low_confidence:
        prefix = (
            "[NOTE: This transcript is very short and may indicate low audio quality. "
            "Evaluate only what is present; do not speculate.]\\n\\n"
        )
    
    resume_block = f"Candidate Resume Summary:\\n\\n{resume_summary}\\n\\n" if resume_summary else ""
    
    features_str = (
        f"Speech Delivery Indicators:\\n"
        f"- Energy: {speech_features.get('energy')}\\n"
        f"- Speaking Rate: {speech_features.get('speaking_rate')}\\n"
        f"- Pause Ratio: {speech_features.get('pause_ratio')}\\n\\n"
    )
    
    return f"{prefix}{features_str}{resume_block}Candidate Transcript:\\n\\n{transcript}"''',
'''def _build_user_prompt_with_speech(transcript: str, speech_features: dict, low_confidence: bool = False) -> str:
    """Build the user message containing the transcript and speech metadata."""
    prefix = ""
    if low_confidence:
        prefix = (
            "[NOTE: This transcript is very short and may indicate low audio quality. "
            "Evaluate only what is present; do not speculate.]\\n\\n"
        )
    
    features_str = (
        f"Speech Delivery Indicators:\\n"
        f"- Energy: {speech_features.get('energy')}\\n"
        f"- Speaking Rate: {speech_features.get('speaking_rate')}\\n"
        f"- Pause Ratio: {speech_features.get('pause_ratio')}\\n\\n"
    )
    
    return f"{prefix}{features_str}Candidate Transcript:\\n\\n{transcript}"''')

# 4. Remove tags from _validate_result
content = content.replace(
'''    required_scores = ["communication", "confidence", "structure", "relevance", "professionalism"]
    required_tags = [
        "communication_traits",
        "behavioral_indicators",
        "experience_assessment",
        "professional_readiness",
        "ai_flags",
    ]

    if "scores" not in result or not isinstance(result["scores"], dict):
        return False

    for key in required_scores:
        val = result["scores"].get(key)
        if val is None or not isinstance(val, (int, float)):
            return False
        if not (0 <= val <= 10):
            return False

    # Ensure all tag fields are present and are lists of strings
    for tag_key in required_tags:
        tag_val = result.get(tag_key)
        if tag_val is None or not isinstance(tag_val, list):
            return False
        if not all(isinstance(item, str) for item in tag_val):
            return False''',
'''    required_scores = ["communication", "confidence", "structure", "relevance", "professionalism"]

    if "scores" not in result or not isinstance(result["scores"], dict):
        return False

    for key in required_scores:
        val = result["scores"].get(key)
        if val is None or not isinstance(val, (int, float)):
            return False
        if not (0 <= val <= 10):
            return False''')

# 5. Add new functions before evaluate_candidate
new_funcs = '''# Tier groupings — only one tier's tags should appear
_COMM_TIERS = [
    {"Very Unclear", "Cannot Express Ideas", "Broken Responses", "Often Pauses", "Low Energy", "Hard to Follow"},
    {"Basic Structure", "Some Hesitation", "Gets Ideas Across", "Stays on Point", "Good Pace", "Easy to Follow"},
    {"Words Flow Well", "Holds Attention", "Speaks Clearly"},
]

def _enforce_comm_tier(tags: list[str]) -> list[str]:
    """Keep only tags from the single most-represented communication tier."""
    if not tags:
        return tags

    tier_counts = [len(set(tags) & tier) for tier in _COMM_TIERS]
    best_tier_idx = tier_counts.index(max(tier_counts))
    return [t for t in tags if t in _COMM_TIERS[best_tier_idx]]


def _build_tag_prompt(transcript: str, jd_text: str = None, resume_summary: str = None) -> str:
    parts = [f"Candidate Transcript:\\n\\n{transcript}"]
    if jd_text:
        parts.append(f"Job Description:\\n\\n{jd_text}")
    if resume_summary:
        parts.append(f"Resume Summary:\\n\\n{resume_summary}")
    if not jd_text and not resume_summary:
        parts.append("[No JD or Resume provided. Use transcript only for tag selection.]")
    return "\\n\\n".join(parts)


def evaluate_tags(
    transcript: str,
    jd_text: str = None,
    resume_summary: str = None,
) -> dict:
    """
    Separate LLM pass for tag selection only.
    Uses transcript + JD + resume. Does NOT influence scores or priority.
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

    user_prompt = _build_tag_prompt(transcript, jd_text=jd_text, resume_summary=resume_summary)

    payload = {
        "messages": [
            {"role": "system", "content": TAG_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,   # more deterministic for classification
            "top_p": 0.9,
            "seed": 42,
        },
    }

    url = f"{OLLAMA_BASE_URL}/api/chat"

    for attempt in range(1, MAX_RETRIES + 1):
        current_model = OLLAMA_MODEL if attempt == 1 else FALLBACK_MODEL
        payload["model"] = current_model
        if attempt > 1:
            logger.info("evaluate_tags: switching to fallback model %s", current_model)

        logger.info("Tag evaluation attempt %d/%d with model %s…", attempt, MAX_RETRIES, current_model)

        try:
            response = requests.post(url, json=payload, timeout=TIMEOUT)
            response.raise_for_status()

            raw_content = response.json().get("message", {}).get("content", "")
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

            # Communication trait tier enforcement — only ONE tier
            cleaned["communication_traits"] = _enforce_comm_tier(cleaned.get("communication_traits", []))

            cleaned = _enforce_tag_hierarchy(cleaned)  # reuse existing hierarchy rules

            logger.info("Tag evaluation complete: %s", cleaned)
            return cleaned

        except requests.exceptions.Timeout:
            logger.warning("evaluate_tags: timed out (attempt %d).", attempt)
        except Exception as exc:
            logger.error("evaluate_tags: unexpected error (attempt %d): %s", attempt, exc)

    logger.error("evaluate_tags: failed after %d attempts — returning empty tags.", MAX_RETRIES)
    return EMPTY_TAGS


def evaluate_candidate('''
content = content.replace('def evaluate_candidate(', new_funcs)

# 6. Update evaluate_candidate body
content = content.replace(
'''def evaluate_candidate(
    transcript: str,
    quality: dict,
    speech_features: dict = None,
    jd_text: str = None,
    resume_summary: str = None,
) -> dict | None:''',
'''def evaluate_candidate(
    transcript: str,
    quality: dict,
    speech_features: dict = None,
    jd_text: str = None,
    resume_summary: str = None,
) -> dict | None:''')

content = content.replace(
'''    if speech_features:
        user_prompt = _build_user_prompt_with_speech(transcript, speech_features, low_confidence=False, resume_summary=resume_summary)
    else:
        user_prompt = _build_user_prompt(transcript, low_confidence=False, resume_summary=resume_summary)

    confidence = compute_evaluation_confidence(transcript, quality)
    
    # Inject JD Context
    dynamic_system_prompt = SYSTEM_PROMPT
    if jd_text:
\\nROLE CONTEXT (JOB \\n────────────────────────)DESCRIPTION\\n{jd_text}\\n\\nAnchor Relevance/experience tag evaluation on this. Reward matches with higher Relevance/experience tags (e.g., 'Strong Role Fit'). Only penalize mismatch if BOTH resume AND transcript confirm it."        f"\\n\\n─ role_context =
        dynamic_system_prompt dynamic_system_prompt.replace\\nEVALUATION CRITERIA", role_context + "\\n───────────────────\\nEVALUATION CRITERIA") =("────

    # Add Tag Hierarchy Enforcement to System Prompt
\\nMULTI-SIGNAL TAG SELECTION RULES\\n─────────────────────────────────────────\\nTag selection must be grounded in cross-signal evidence (audio + resume + JD), not any single input alone. Cross-validate behavioral tags against resume evidence. Anchor professional tags to resume facts."    "\\n\\n────────────────────────── tag_rules =
    dynamic_system_prompt dynamic_system_prompt.replace\\nRECRUITER TAG OUTPUT", tag_rules + "\\n─────\\nRECRUITER TAG OUTPUT") =("──────────────────────────────────────

    # Base payload structure
    base_payload = {
        "messages": [
            {"role": "system", "content": dynamic_system_prompt},
            {"role": "user", "content": user_prompt},
        ],''',
'''    if speech_features:
        user_prompt = _build_user_prompt_with_speech(transcript, speech_features, low_confidence=False)
    else:
        user_prompt = _build_user_prompt(transcript, low_confidence=False)

    confidence = compute_evaluation_confidence(transcript, quality)
    
    # Base payload structure
    base_payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],''')

content = content.replace(
'''            # HARD VALIDATION: Enforce strict closed tag selection by exact match only
            for tag_key, allowed_list in ALLOWED_TAGS.items():
                if tag_key in result and isinstance(result[tag_key], list):
                    # Strip whitespace to handle minor formatting issues, but require exact string match
                    normalized_tags = [str(t).strip() for t in result[tag_key]]
                    result[tag_key] = [t for t in normalized_tags if t in allowed_list]

            result = _enforce_tag_hierarchy(result)''',
'''            # (Tag validation removed since this pass no longer selects tags)''')


with open('/home/frappe/frappe-bench/apps/ai_apps/ai_apps/ai_screening/evaluator.py', 'w') as f:
    f.write(content)

