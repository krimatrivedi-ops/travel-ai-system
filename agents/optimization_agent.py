import json
from typing import Any, Dict, List, Optional
from core.contracts import Agent
from services.llm_service import call_llm
from core.geometry import haversine_distance, estimate_travel_time

class OptimizationAgent(Agent):
    """
    Dynamically updates and optimizes a user's itinerary when they modify any segment,
    considering time, cost, distance, and user preferences.
    """

    def name(self) -> str:
        return "optimization_agent"

    def execute(self, input_data: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes an itinerary change request and returns an optimized itinerary with recommendations.
        """
        current_itinerary = input_data.get("current_itinerary", [])
        user_request = input_data.get("user_request", "")
        user_preferences = input_data.get("user_preferences", {})
        candidate_places = input_data.get("candidate_places", [])

        # STEP 1 & 2: Intent Understanding & Dish Detection (LLM)
        # We also let the LLM handle Step 5 (Ranking) and Step 6 (Response) 
        # but we provide it with calculated distances and times for better accuracy.

        # Prepare candidates with distance info for the LLM
        enriched_candidates = self._enrich_candidates(candidate_places, current_itinerary, user_preferences)

        system_prompt = """
You are an intelligent travel itinerary optimization engine.
Your task is to update a user's itinerary based on a request. Candidates may be restaurants/cafes OR culture POIs (museums, galleries, attractions) from OpenStreetMap — use ENRICHED_CANDIDATE_PLACES as given.
For dining intents: consider dish matches from reviews. For museum/attraction intents: consider relevance, ratings, and fit with the request.

RULES:
1. STEP 1: Extract intent (meal vs sight, cuisine, budget, vibe).
2. STEP 2: For food venues, infer dish/cuisine fit from reviews; for culture venues, infer topic fit from name/type/reviews.
3. STEP 5: Rank top 3 options using the formula (use dish_match_score as "fit score" for non-food POIs):
   score = (dish_match_score * 0.4) + (rating * 0.2 normalized) + (distance_score * 0.2) + (price_match * 0.1) + (vibe_match * 0.1)
4. STEP 6: Return JSON only.
5. STEP 7: SMART UX BEHAVIOR:
   - LOW impact (<15 min delay): auto-adjust silently.
   - MEDIUM impact (15–40 min): show warning but proceed.
   - HIGH impact (>40 min): require confirmation tone.
6. Recommendation-first behavior: always return ranked recommendations for user selection; do not treat USER_REQUEST as an immediate direct command mutation.

OUTPUT JSON FORMAT:
{
  "meal_edit": {
    "flat_segment_index": 0,
    "reason": "short string — which segment is the meal swap (0-based index into CURRENT_ITINERARY array order)"
  },
  "recommendations": [
    {
      "name": "string",
      "why": "string",
      "dish_confidence": "string",
      "estimated_cost": "string",
      "travel_time": "string"
    }
  ],
  "selected_option_preview": {
    "new_timing": ["string"],
    "cost_change": "string",
    "delay": "string",
    "impact_level": "LOW|MEDIUM|HIGH"
  },
  "warning_message": "string (only if impact is MEDIUM or HIGH)",
  "updated_itinerary": [ /* full array of updated segments */ ]
}

flat_segment_index MUST match the segment in CURRENT_ITINERARY you would replace (meal stop or sightseeing slot — same order as the array).
"""

        user_prompt = f"""
CURRENT_ITINERARY: {json.dumps(current_itinerary, ensure_ascii=False)}
USER_REQUEST: {user_request}
USER_PREFERENCES: {json.dumps(user_preferences, ensure_ascii=False)}
ENRICHED_CANDIDATE_PLACES: {json.dumps(enriched_candidates, ensure_ascii=False)}
"""

        response_json = call_llm(system_prompt, user_prompt)

        try:
            return json.loads(response_json)
        except json.JSONDecodeError:
            # Fallback or error handling
            return {
                "recommendations": [],
                "error": "Failed to parse optimization response"
            }

    def _enrich_candidates(self, candidates: List[Dict[str, Any]], itinerary: List[Dict[str, Any]], preferences: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculates travel times and distances for candidates relative to the itinerary.
        """
        if not itinerary:
            return candidates

        # Find the segment that is being modified or the last relevant one
        # For simplicity, we compare to the "previous" segment if we can identify it,
        # otherwise we compare to the first segment's location as a placeholder.
        prev_lat = float(itinerary[0].get("lat", 0))
        prev_lon = float(itinerary[0].get("lon", 0) or itinerary[0].get("lng", 0))

        transport_mode = preferences.get("transport_mode", "taxi")
        
        enriched = []
        for cand in candidates:
            cand_lat = float(cand.get("lat", 0))
            cand_lon = float(cand.get("lon", 0) or cand.get("lng", 0))
            
            dist = haversine_distance(prev_lat, prev_lon, cand_lat, cand_lon)
            travel_time = estimate_travel_time(dist, transport_mode)
            
            # Normalize rating (0-5) to 0-1 for distance_score later if needed, 
            # but we'll let LLM handle the scoring as per prompt.
            
            enriched.append({
                **cand,
                "distance_km": round(dist, 2),
                "estimated_travel_time_min": travel_time
            })
            
        return enriched
