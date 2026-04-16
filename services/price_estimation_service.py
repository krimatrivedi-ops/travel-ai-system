import logging
import time
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from groq import Groq
from core.config import settings

logger = logging.getLogger(__name__)

# Simple in-memory cache for price estimates
# Key: (city, country, segment_type, budget_level)
# Value: (timestamp, estimate_dict)
_price_cache: Dict[Tuple[str, str, str, str], Tuple[float, Dict[str, Any]]] = {}
CACHE_TTL = 86400  # 24 hours

def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def estimate_price(segment: Dict[str, Any], persona: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates a price estimate for a segment using LLM (Groq).
    Uses caching to avoid repeated calls.
    """
    # Extract fields for caching and prompt
    destination = persona.get("destination", "Unknown")
    # Try to split destination into city/country if possible
    parts = [p.strip() for p in destination.split(",")]
    city = parts[0] if len(parts) > 0 else "Unknown"
    country = parts[1] if len(parts) > 1 else city
    
    segment_type = segment.get("type", segment.get("title", "Activity"))
    budget_level = persona.get("budget_level", "medium")
    name = segment.get("place_name", segment.get("title", "Unknown"))
    description = segment.get("description", "")

    cache_key = (city, country, segment_type, budget_level)
    now_m = time.monotonic()
    
    if cache_key in _price_cache:
        ts, cached_val = _price_cache[cache_key]
        if now_m - ts < CACHE_TTL:
            return cached_val

    # Call LLM for estimate
    client = Groq(api_key=settings.groq_api_key)
    model = settings.llm_model

    system_prompt = """You are a global travel pricing estimation engine.

Estimate a realistic price range.

Rules:
- Do NOT invent extreme values
- Use general real-world knowledge
- Return conservative ranges if unsure
- Output ONLY JSON"""

    user_prompt = f"""INPUT:
- Segment type: {segment_type}
- Name: {name}
- Location: {city}, {country}
- Budget level: {budget_level}
- Notes: {description}

OUTPUT:
{{
  "min_amount": number,
  "max_amount": number,
  "currency": "ISO_CODE",
  "confidence": "low|medium|high"
}}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        estimate = json.loads(content)
        
        # Validation and Normalization
        estimate = validate_and_normalize_estimate(estimate)
        
        # Add metadata
        estimate["source"] = "llm_estimate"
        estimate["last_updated_at"] = _now_iso_utc()
        
        # Cache result
        _price_cache[cache_key] = (now_m, estimate)
        return estimate
        
    except Exception as e:
        logger.error(f"Error estimating price: {e}")
        return get_fallback_estimate()

def validate_and_normalize_estimate(estimate: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensures min_amount > 0, max_amount >= min_amount, and clamps extreme ratios.
    """
    try:
        min_amt = float(estimate.get("min_amount", 0))
        max_amt = float(estimate.get("max_amount", 0))
        
        if min_amt <= 0:
            return get_fallback_estimate()
            
        if max_amt < min_amt:
            max_amt = min_amt
            
        # Clamp extreme ratios (max <= 10x min)
        if max_amt > min_amt * 10:
            max_amt = min_amt * 10
            
        return {
            "min_amount": min_amt,
            "max_amount": max_amt,
            "currency": str(estimate.get("currency", "USD")).upper(),
            "confidence": estimate.get("confidence", "low")
        }
    except (ValueError, TypeError):
        return get_fallback_estimate()

def get_fallback_estimate() -> Dict[str, Any]:
    """Returns a safe default range if LLM fails or returns invalid data."""
    return {
        "min_amount": 10.0,
        "max_amount": 50.0,
        "currency": "USD",
        "confidence": "low",
        "source": "fallback",
        "last_updated_at": _now_iso_utc()
    }
