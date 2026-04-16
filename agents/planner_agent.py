import json
from datetime import timedelta
from typing import Any, Dict, List

from core.contracts import Agent
from core.preference_schema import trip_anchor_date
from core.itinerary_schema import (
    new_empty_bundle,
    normalize_bundle_from_llm,
    parse_trip_duration_days,
    validate_itinerary_bundle,
)
from services.llm_service import call_llm
from services.pricing_service import enrich_itinerary_pricing
from services.weather_service import fetch_daily_weather


class PlannerAgent(Agent):
    """
    Builds a multi-day, travel-agent-quality itinerary (v2) from OSM candidates + LLM.
    Now includes weather information for each segment.
    """

    def name(self) -> str:
        return "planner_agent"

    def execute(self, input_data: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        persona = input_data.get("persona", {})
        pois = input_data.get("pois", [])

        if not pois:
            return {"itinerary": new_empty_bundle()}

        num_days = parse_trip_duration_days(str(persona.get("trip_duration", "")))
        candidates = self._get_top_candidates(pois, persona, count=min(30, len(pois)))

        system_prompt = f"""
You are an expert boutique travel agent producing a {num_days}-day trip plan.

Return ONLY valid JSON (no markdown) with this exact top-level shape:
{{
  "days": [ /* exactly {num_days} day objects */ ]
}}

Each element of "days" MUST include:
- "day": integer (1..{num_days})
- "title": short evocative theme for that day
- "summary": 1-2 sentences for a summary table row
- "segments": array of at least 3 items for that day (morning through evening)
- "accommodation": string or null (where to stay that night — area or hotel class)
- "dining_highlight": string or null (signature meal focus)
- "estimated_daily_budget_note": string or null (qualitative pacing/budget *feel* only — NO numeric currency amounts, NO dollar/euro/rupee figures; phrase as "budget-conscious day" style, not a quote)

Each segment MUST include:
- "time_label": e.g. "8:00–10:00" or "Morning"
- "title": short activity title
- "place_name": MUST use real names; prefer names from the Candidates list when they fit
- "description": 2-4 sentences: what to do, why it matches the traveler, pacing
- "meal_suggestion": string or null
- "transport_note": string or null (rideshare, walk, rickshaw, etc.)
- "local_tip": string or null
- "lat": latitude if known from candidate list
- "lon": longitude if known from candidate list

Hard rule: Do NOT put numeric currency amounts, fares, or hotel prices in any JSON field — integration layer supplies money facts; you supply qualitative itinerary text only.
"""

        user_prompt = f"""NUM_DAYS: {num_days}
Destination context: {persona.get("destination", "")}
Persona: {json.dumps(persona, ensure_ascii=False)}
Candidates (from OpenStreetMap — use these names when possible): {json.dumps(candidates, ensure_ascii=False)}
"""

        response_json = call_llm(system_prompt, user_prompt)

        try:
            data = json.loads(response_json)
        except json.JSONDecodeError:
            return {"itinerary": new_empty_bundle()}

        raw_days = data.get("days") if isinstance(data, dict) else None
        if raw_days is None and isinstance(data, dict):
            raw_days = data.get("itinerary", {}).get("days") if isinstance(data.get("itinerary"), dict) else None

        raw_obj: Dict[str, Any] = {"days": raw_days if isinstance(raw_days, list) else []}

        bundle = normalize_bundle_from_llm(raw_obj, num_days, candidates)

        if not validate_itinerary_bundle(bundle, expected_days=num_days):
            return {"itinerary": new_empty_bundle()}

        # Attach live weather per segment (Open-Meteo daily), aligned to trip calendar days
        anchor = trip_anchor_date(persona)
        for day_offset, day in enumerate(bundle.get("days", [])):
            forecast_date = anchor + timedelta(days=day_offset)
            for segment in day.get("segments", []):
                w = fetch_daily_weather(
                    segment.get("lat"), segment.get("lon"), forecast_date
                )
                for key, val in w.items():
                    segment[key] = val
                if w.get("weather_availability") == "ok":
                    segment["weather"] = w.get("condition")
                    segment["temp"] = w.get("temp")
                else:
                    segment["weather"] = None
                    segment["temp"] = None

        enrich_itinerary_pricing(bundle, persona, run_price_agent=True, force_price_agent=False)

        return {"itinerary": bundle}

    def _get_top_candidates(
        self, pois: List[Dict[str, Any]], persona: Dict[str, Any], count: int
    ) -> List[Dict[str, Any]]:
        scored_pois = []
        for poi in pois:
            score = 1.0
            if persona.get("travel_style") == "cultural" and poi.get("type") in [
                "museum",
                "gallery",
            ]:
                score += 5.0
            if persona.get("travel_style") == "cultural" and "attraction" in str(
                poi.get("type", "")
            ).lower():
                score += 2.0
            scored_pois.append({**poi, "score": score})
        return sorted(scored_pois, key=lambda x: x["score"], reverse=True)[:count]
