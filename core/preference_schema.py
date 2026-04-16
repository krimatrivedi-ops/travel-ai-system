"""
Structured travel preferences aligned with PersonaAgent / PlannerAgent and PO flow.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Required before itinerary generation (POC scope).
REQUIRED_FIELDS: Tuple[str, ...] = (
    "destination",
    "trip_duration",
    "travel_style",
    "food_priority",
    "walking_tolerance",
    "pace",
    "budget_sensitivity",
)

TRAVEL_STYLES = frozenset({"luxury", "adventure", "cultural", "balanced"})
WALKING = frozenset({"low", "medium", "high"})
PACE = frozenset({"relaxed", "moderate", "intensive"})
BUDGET = frozenset({"low", "medium", "high"})

# Short prompts for heuristic fallback when LLM is unavailable.
FIELD_PROMPTS: Dict[str, str] = {
    "destination": "Which city or region are you traveling to?",
    "trip_duration": "How long is your trip (e.g. 3 days, weekend, one week)?",
    "travel_style": "What travel style fits you best: cultural, luxury, adventure, or balanced?",
    "food_priority": "How important are restaurants and food on this trip? Reply with a number from 1 (low) to 10 (high).",
    "walking_tolerance": "How much walking are you comfortable with: low, medium, or high?",
    "pace": "Preferred pace: relaxed, moderate, or intensive?",
    "budget_sensitivity": "Budget sensitivity: low (splurge okay), medium, or high (budget-conscious)?",
}


def _coerce_int_food(v: Any) -> int:
    try:
        n = int(float(str(v).strip()))
        return max(1, min(10, n))
    except (TypeError, ValueError):
        return 7


def trip_anchor_date(persona: Dict[str, Any]) -> date:
    """
    First calendar day of the trip for weather forecasts.
    Uses optional persona['trip_start_date'] as YYYY-MM-DD; otherwise today (generation date).
    """
    raw = persona.get("trip_start_date")
    if raw:
        try:
            s = str(raw).strip()[:10]
            return date.fromisoformat(s)
        except ValueError:
            logger.warning(
                "Invalid trip_start_date %r; using today for weather anchor",
                raw,
            )
    return date.today()


def _strip_absent_overrides(p: Dict[str, Any]) -> Dict[str, Any]:
    """
    Drop None and blank-string values so they do not erase snapshot defaults.
    """
    out: Dict[str, Any] = {}
    for k, v in p.items():
        if v is None:
            continue
        if isinstance(v, str) and not str(v).strip():
            continue
        out[k] = v
    return out


def merge_trip_snapshot_with_partial(
    trip_snapshot: Optional[Dict[str, Any]], partial: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Effective preference base for the next preference LLM turn.

    Precedence: normalized trip snapshot provides defaults; keys present in ``partial``
    (from session or from the last ``process_turn`` merge) override the snapshot.
    Use when replanning from a saved row so empty/stale session state does not drop
    stored preferences.
    """
    p = _strip_absent_overrides(dict(partial) if partial else {})
    if not trip_snapshot:
        return p
    base = normalize_persona(trip_snapshot)
    return {**base, **p}


def normalize_persona(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Merge partial persona with safe defaults for planner compatibility."""
    ts = str(raw.get("travel_style", "balanced")).lower()
    if ts not in TRAVEL_STYLES:
        ts = "balanced"
    wt = str(raw.get("walking_tolerance", "medium")).lower()
    if wt not in WALKING:
        wt = "medium"
    pace = str(raw.get("pace", "moderate")).lower()
    if pace not in PACE:
        pace = "moderate"
    budget = str(raw.get("budget_sensitivity", "medium")).lower()
    if budget not in BUDGET:
        budget = "medium"
    dest = str(raw.get("destination", "")).strip() or "Paris"
    duration = str(raw.get("trip_duration", "")).strip() or "3 days"
    dc = str(raw.get("display_currency") or "USD").strip().upper()[:3]
    if len(dc) != 3 or not dc.isalpha():
        dc = "USD"
    return {
        "destination": dest,
        "trip_duration": duration,
        "travel_style": ts,
        "food_priority": _coerce_int_food(raw.get("food_priority", 7)),
        "walking_tolerance": wt,
        "pace": pace,
        "budget_sensitivity": budget,
        "party_size": raw.get("party_size"),
        "accessibility_notes": raw.get("accessibility_notes"),
        "trip_start_date": raw.get("trip_start_date"),
        "display_currency": dc,
    }


def missing_required(persona: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for key in REQUIRED_FIELDS:
        val = persona.get(key)
        if key == "food_priority":
            if val is None or (isinstance(val, str) and not str(val).strip()):
                out.append(key)
            continue
        if val is None or (isinstance(val, str) and not str(val).strip()):
            out.append(key)
    return out


def first_missing_field(persona: Dict[str, Any]) -> str | None:
    m = missing_required(persona)
    return m[0] if m else None
