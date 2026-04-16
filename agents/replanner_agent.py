import json
from typing import Any, Dict, List
from core.contracts import Agent
from services.llm_service import call_llm
from events.event_bus import EventType, get_events
from core.itinerary_schema import ITINERARY_VERSION, new_empty_bundle


class ReplannerAgent(Agent):
    """
    Patch-based updates on a v2 multi-day itinerary (days[]), using the LLM.
    """

    def name(self) -> str:
        return "replanner_agent"

    def execute(self, input_data: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        itinerary = input_data.get("itinerary")
        persona = state.get("persona", {})
        events = get_events()

        if not events:
            return {"updated_itinerary": itinerary, "changes": []}

        event = events[-1]

        if not isinstance(itinerary, dict) or itinerary.get("itinerary_version") != ITINERARY_VERSION:
            return {"updated_itinerary": itinerary if itinerary is not None else new_empty_bundle(), "changes": []}

        system_prompt = f"""
You are a travel replanning agent. The itinerary uses structure version {ITINERARY_VERSION}.

The JSON must have exactly this shape:
{{
  "updated_itinerary": {{
    "itinerary_version": {ITINERARY_VERSION},
    "days": [ /* same length as input; each day has day, title, summary, segments[], optional accommodation, dining_highlight, estimated_daily_budget_note */ ]
  }},
  "changes": [ "short bullet strings describing what you changed" ]
}}

Rules:
- Modify ONLY what the event requires (e.g. move indoor if rain; small time shifts for USER_EDIT).
- If USER_EDIT has action="add", insert the specified place into the most logical time slot for that day/itinerary.
- Preserve days[].day numbering and overall length of days array.
- Keep each segment with: time_label, title, place_name, description, and optional meal_suggestion, transport_note, local_tip, lat, lon, weather fields, and pricing objects if present.
- Do NOT invent numeric currency amounts, fares, or hotel prices — preserve existing pricing metadata or omit; never add fake prices.
- estimated_daily_budget_note must stay qualitative only (no numeric money amounts).
- Return ONLY valid JSON.
"""

        user_prompt = f"""
Persona: {json.dumps(persona)}
Current itinerary: {json.dumps(itinerary, ensure_ascii=False)}
Event: {event.type.value} — {json.dumps(event.payload, ensure_ascii=False)}
"""

        response_json = call_llm(system_prompt, user_prompt)

        try:
            out = json.loads(response_json)
        except json.JSONDecodeError:
            return {"updated_itinerary": itinerary, "changes": []}

        updated = out.get("updated_itinerary")
        if isinstance(updated, dict) and updated.get("itinerary_version") == ITINERARY_VERSION:
            return {
                "updated_itinerary": updated,
                "changes": out.get("changes") or [],
            }
        return {"updated_itinerary": itinerary, "changes": []}
