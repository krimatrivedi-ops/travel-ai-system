import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from core.contracts import Agent
from services.llm_service import call_llm
from services.osm_service import _nominatim_center
import math

logger = logging.getLogger(__name__)

class PersonalizationAgent(Agent):
    """
    Exhaustively analyzes an itinerary for every possible logistical detail ("gaps")
    from leaving home to returning home. Suggests button-based options to simplify 
    user decisions so they don't have to think about small details.
    """

    def name(self) -> str:
        return "personalization_agent"

    def execute(self, input_data: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        mode = input_data.get("mode", "analyze")
        itinerary = input_data.get("itinerary")
        persona = input_data.get("persona", {})

        if mode == "analyze":
            return self._analyze_gaps(itinerary, persona)
        elif mode == "apply":
            gap_id = input_data.get("gap_id")
            option_value = input_data.get("option_value")
            return self._apply_option(itinerary, persona, gap_id, option_value)
        
        return {"error": "Invalid mode"}

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Distance in kilometers."""
        R = 6371
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _get_distance_hint(self, from_loc: str, to_loc: str) -> str:
        if not from_loc or not to_loc:
            return ""
        p1 = _nominatim_center(from_loc)
        p2 = _nominatim_center(to_loc)
        if p1 and p2:
            dist = self._haversine_distance(p1[0], p1[1], p2[0], p2[1])
            # Road distance is typically 1.3x to 1.4x the haversine distance
            est_km = dist * 1.4
            # 1.8 mins per km ~= 33 km/h average (more realistic for long hauls in traffic/India)
            # This makes 600km ~ 10.8 hours
            est_mins = est_km * 1.8
            hours = int(est_mins // 60)
            minutes = int(est_mins % 60)
            return f"Approx. {est_km:.0f} km, {hours}h {minutes}m"
        return ""

    def _analyze_gaps(self, itinerary: Dict[str, Any], persona: Dict[str, Any]) -> Dict[str, Any]:
        # Check if home location is known
        home = persona.get("home_location")
        destination = persona.get("destination")
        distance_context = ""
        if home and destination:
            distance_context = self._get_distance_hint(home, destination)

        system_prompt = f"""
You are a meticulous Travel Logistics Architect. Your mission is to examine a travel itinerary and identify EVERY single missing detail from leaving home to returning home.

The user should NOT have to think. If a detail is missing, you must ask.

CRITICAL LOGIC FOR REALISM:
1. CONTEXT AWARENESS: If the user already answered a question (check Persona/Itinerary), do NOT ask it again or ask contradictory follow-ups.
   - Example: If the user says "Private Car", do NOT ask "How will you reach the train station?".
2. REALISTIC TIMING: Use the provided distance context. If the journey takes 10 hours, do NOT suggest 5-hour arrival times.
3. OPTIONS: Provide 5-6 extremely realistic options for each gap. 
4. CUSTOM INPUT: Always allow a "Custom" option if the provided chips don't fit the user's specific plan.

{f"DISTANCE CONTEXT: The distance between {home} and {destination} is {distance_context}." if distance_context else ""}

Exhaustive list of gap categories to check:
- Departure from home: Mode (Private Car, Uber, Train, Flight), Starting Time, and Arrival expectations.
- Buffer/Layovers: Logistical gaps at hubs.
- Last-mile: Arrival hub to final hotel/destination.
- Daily logistics: Morning routine, transit between POIs, evening returns.
- Return trip: Home-bound logistics.

For each gap:
1. "id": Unique string ID.
2. "type": Category.
3. "prompt": Friendly, specific question.
4. "options": 5-6 realistic options. Each with "label", "value", and "description" (time/price).
5. "allow_custom": Boolean.

Return ONLY valid JSON:
{{
  "gaps": [
    {{
      "id": "...",
      "type": "...",
      "prompt": "...",
      "options": [...],
      "allow_custom": true
    }}
  ]
}}
"""

        user_prompt = f"""
Persona: {json.dumps(persona)}
Itinerary: {json.dumps(itinerary, ensure_ascii=False)}
"""

        response_json = call_llm(system_prompt, user_prompt)

        try:
            return json.loads(response_json)
        except json.JSONDecodeError:
            logger.error("Failed to parse PersonalizationAgent gaps JSON")
            return {"gaps": []}

    def _apply_option(self, itinerary: Dict[str, Any], persona: Dict[str, Any], gap_id: str, option_value: str) -> Dict[str, Any]:
        system_prompt = """
You are a precise Travel Itinerary Editor. Integrate a user's logistical choice into their itinerary bundle.

Instructions:
1. Insert the choice as a new segment or modify an existing one.
2. Maintain logical timeline flow.
3. Update "time_label", "title", "description", and "transport_note".
4. If the choice implies a long-term preference OR if it's the 'home_location', update the "updated_persona" object.
   - For 'home_location' gap, the 'option_value' is the location string.
5. For pricing, use the value from the selected option or a realistic estimate. Label variable costs as "Est. Market Rate" if uncertain.

Return ONLY valid JSON:
{
  "updated_itinerary": { ... },
  "updated_persona": { ... }
}
"""

        user_prompt = f"""
Gap ID: {gap_id}
Selected Option: {option_value}
Persona: {json.dumps(persona)}
Itinerary: {json.dumps(itinerary, ensure_ascii=False)}
"""

        response_json = call_llm(system_prompt, user_prompt)

        try:
            data = json.loads(response_json)
            return {
                "itinerary": data.get("updated_itinerary", itinerary),
                "persona": data.get("updated_persona", persona)
            }
        except json.JSONDecodeError:
            logger.error("Failed to parse PersonalizationAgent apply JSON")
            return {"itinerary": itinerary, "persona": persona, "error": "Failed to apply option"}
