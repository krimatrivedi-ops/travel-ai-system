"""
LLM-assisted preference extraction with heuristic fallback when no API key.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from agents.persona_agent import PersonaAgent
from core.config import settings
from core.preference_schema import (
    FIELD_PROMPTS,
    TRAVEL_STYLES,
    first_missing_field,
    missing_required,
)

SYSTEM_PROMPT = """You are a travel preference assistant for a sales demo product.
Extract and merge user preferences from the conversation into a JSON object.

Required persona fields (all must be present before you set complete=true):
- destination: string, city or region name
- trip_duration: string (e.g. "3 days", "long weekend")
- travel_style: exactly one of: luxury, adventure, cultural, balanced
- food_priority: integer 1-10
- walking_tolerance: exactly one of: low, medium, high
- pace: exactly one of: relaxed, moderate, intensive
- budget_sensitivity: exactly one of: low, medium, high

Optional: party_size (integer), accessibility_notes (string)

Rules:
- Merge the latest user message into persona; keep prior values unless updated.
- NEVER infer, guess, or "silently invent" values for required fields. If a field has not been explicitly provided by the user, leave it null or unchanged.
- If any required field is still unknown, missing, or vague, set complete=false and provide ONE short, friendly next_question targeting that specific gap.
- Set complete=true ONLY when every required field has been explicitly and confidently provided by the user.
- Respond with ONLY valid JSON, no markdown, in this shape:
{"persona":{...},"complete":true|false,"next_question":string|null}
"""


def _openai_turn(
    messages: List[Dict[str, str]], partial: Dict[str, Any]
) -> Tuple[Dict[str, Any], bool, str | None]:
    # 1. Check for Groq installation
    try:
        from groq import Groq
    except ImportError:
        raise RuntimeError("groq package not installed. Run 'pip install groq'")

    # 2. Check for the specific Groq key in settings
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is missing in settings or .env")

    # 3. Initialize Groq Client
    client = Groq(api_key=settings.groq_api_key)
    model = settings.llm_model # e.g., "llama-3.3-70b-versatile"

    # 4. Prepare payload and messages
    payload_hint = json.dumps(partial, ensure_ascii=False)
    convo = [
        {
            "role": "system",
            "content": f"{SYSTEM_PROMPT}\n\n**IMPORTANT**: Respond ONLY with a valid JSON object.\n\nCurrent merged persona JSON:\n{payload_hint}",
        }
    ]
    for m in messages:
        role = m.get("role", "user")
        if role not in ("user", "assistant"):
            role = "user"
        convo.append({"role": role, "content": m.get("content", "")})

    resp = client.chat.completions.create(
        model=model,
        messages=convo,
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)
    persona = data.get("persona") or {}
    complete = bool(data.get("complete"))
    nq = data.get("next_question")
    if isinstance(nq, str) and not nq.strip():
        nq = None
    merged = {**partial, **persona}
    if not complete and not nq:
        # Model forgot to ask; use heuristic question
        miss = missing_required(merged)
        if miss:
            nq = FIELD_PROMPTS.get(miss[0], "Could you share a bit more about your trip?")
    return merged, complete, nq


_heuristic_agent = PersonaAgent()


def _heuristic_merge(user_text: str, partial: Dict[str, Any]) -> Dict[str, Any]:
    """Use keyword persona agent + simple destination/duration regex hints."""
    h = _heuristic_agent.execute({"user_input": user_text}, {})
    merged = {**partial}
    for k, v in h.items():
        if v is not None:
            merged[k] = v
    # crude destination: "to X", "in X", "visit X"
    low = user_text.lower()
    for pat in (
        r"\bto\s+([A-Za-z][A-Za-z\s\-]{1,40}?)(?:\s+for|\s+next|,|\.|$)",
        r"\bin\s+([A-Za-z][A-Za-z\s\-]{1,40}?)(?:\s+for|\s+next|,|\.|$)",
        r"\bvisit\s+([A-Za-z][A-Za-z\s\-]{1,40}?)(?:\s+for|,|\.|$)",
    ):
        m = re.search(pat, low, re.I)
        if m:
            cand = m.group(1).strip()
            if len(cand) > 1 and merged.get("destination") in (None, "", "Paris"):
                merged["destination"] = cand.title()
            break
    # duration hints
    if not merged.get("trip_duration"):
        dm = re.search(
            r"\b(\d+\s*(?:days?|nights?)|weekend|one week|a week|long weekend)\b",
            low,
            re.I,
        )
        if dm:
            merged["trip_duration"] = dm.group(1)
    return merged


def process_turn(
    messages: List[Dict[str, str]], partial_persona: Dict[str, Any]
) -> Tuple[Dict[str, Any], bool, str | None]:
    """
    Returns: updated_partial_persona, complete, next_question_or_none
    """
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = m.get("content", "")
            break

    # Try OpenAI first
    try:
        merged, complete, nq = _openai_turn(messages, dict(partial_persona))
        merged = _heuristic_merge(last_user, merged)
        if complete and missing_required(merged):
            complete = False
            miss = missing_required(merged)[0]
            nq = FIELD_PROMPTS.get(miss, nq)
        if not complete:
            return merged, False, nq
        return merged, True, None
    except Exception:
        pass

    merged = _heuristic_merge(last_user, dict(partial_persona))
    merged = _apply_direct_answer(merged, last_user)
    miss = missing_required(merged)
    if not miss:
        return merged, True, None
    field = miss[0]
    return merged, False, FIELD_PROMPTS[field]


def _apply_direct_answer(merged: Dict[str, Any], last_user: str) -> Dict[str, Any]:
    """Map short replies to the next missing field (heuristic path only)."""
    t = last_user.strip()
    if not t:
        return merged
    miss = first_missing_field(merged)
    if not miss:
        return merged
    low = t.lower()
    if miss == "food_priority" and t.isdigit():
        merged["food_priority"] = int(t)
        return merged
    if miss == "travel_style":
        for s in TRAVEL_STYLES:
            if s in low:
                merged["travel_style"] = s
                return merged
    if miss == "walking_tolerance" and low in ("low", "medium", "high"):
        merged["walking_tolerance"] = low
        return merged
    if miss == "pace" and any(
        x in low for x in ("relaxed", "moderate", "intensive")
    ):
        for x in ("relaxed", "moderate", "intensive"):
            if x in low:
                merged["pace"] = x
                return merged
    if miss == "budget_sensitivity" and low in ("low", "medium", "high"):
        merged["budget_sensitivity"] = low
        return merged
    if miss == "destination" and len(t) > 1 and len(t) < 60:
        merged["destination"] = t.strip().title()
        return merged
    if miss == "trip_duration" and len(t) < 80:
        merged["trip_duration"] = t
        return merged
    return merged
