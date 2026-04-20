import json
from typing import Any, Dict, List
from core.contracts import Agent
from core.itinerary_schema import (
    new_empty_bundle,
    normalize_bundle_from_llm,
    validate_itinerary_bundle,
)
from services.llm_service import call_llm
from services.pricing_service import enrich_itinerary_pricing
from services.weather_service import fetch_daily_weather
from datetime import date, timedelta

class YouTubeItineraryAgent(Agent):
    """
    Analyzes a YouTube video transcript to generate a structured travel itinerary.
    """

    def name(self) -> str:
        return "youtube_itinerary_agent"

    def execute(self, input_data: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        transcript = input_data.get("transcript", "")
        persona = input_data.get("persona", {})
        start_date_str = persona.get("trip_start_date")
        
        if not transcript:
            return {"itinerary": new_empty_bundle(), "error": "No transcript provided"}

        # Extract destination and duration from transcript first if not in persona
        # But for this POC, we'll assume the LLM can infer it or use persona if available.

        system_prompt = """
You are a travel expert. Analyze the provided YouTube transcript of a travel vlog.
Extract the travel itinerary mentioned in the video.

Rules:
- Identify the main destination(s).
- Identify the sequence of days and the activities for each day.
- Identify specific locations (restaurants, landmarks, hotels).
- Create a day-wise itinerary in the standard v2 format.
- If the video doesn't specify a day-wise split, logically group activities into days (e.g., 3-5 activities per day).

Return ONLY valid JSON (no markdown) with this exact top-level shape:
{
  "destination": "string",
  "num_days": integer,
  "days": [
    {
      "day": integer,
      "title": "short theme",
      "summary": "1-2 sentence summary",
      "segments": [
        {
          "time_label": "Morning/Afternoon/Evening",
          "title": "short activity title",
          "place_name": "real name of the place",
          "description": "2-4 sentences from the transcript context",
          "meal_suggestion": "string or null",
          "transport_note": "string or null",
          "local_tip": "string or null"
        }
      ],
      "accommodation": "string or null",
      "dining_highlight": "string or null"
    }
  ]
}

Hard rule: Do NOT put numeric currency amounts.
"""

        user_prompt = f"Transcript: {transcript[:15000]}" # Limit transcript size for LLM

        response_json = call_llm(system_prompt, user_prompt)

        try:
            data = json.loads(response_json)
        except json.JSONDecodeError:
            return {"itinerary": new_empty_bundle(), "error": "LLM failed to produce valid JSON"}

        raw_days = data.get("days", [])
        num_days = data.get("num_days", len(raw_days))
        destination = data.get("destination", persona.get("destination", "Unknown"))
        
        # We need candidates for normalize_bundle_from_llm to work well, 
        # but here the "candidates" are extracted from transcript.
        # We'll pass an empty list of candidates and let it use the extracted names.
        bundle = normalize_bundle_from_llm({"days": raw_days}, num_days, [])

        # Enrichment
        if start_date_str:
            try:
                anchor = date.fromisoformat(start_date_str)
            except:
                anchor = date.today()
        else:
            anchor = date.today()

        for day_offset, day in enumerate(bundle.get("days", [])):
            forecast_date = anchor + timedelta(days=day_offset)
            for segment in day.get("segments", []):
                # We don't have lat/lon from transcript easily, 
                # but we could try to look them up. For now, we'll skip live weather 
                # unless we add a geocoding step.
                segment["weather_availability"] = "unavailable"
                segment["weather_error"] = "missing_coordinates"

        enrich_itinerary_pricing(bundle, persona, run_price_agent=True, force_price_agent=False)

        return {"itinerary": bundle, "destination": destination, "num_days": num_days}
