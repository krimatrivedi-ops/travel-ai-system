from agents.persona_agent import PersonaAgent
from agents.planner_agent import PlannerAgent
from agents.replanner_agent import ReplannerAgent
from agents.destination_agent import DestinationAgent
from services.osm_service import fetch_pois
from state.store import update_state, get_state
from events.event_bus import emit_event, EventType
from typing import Dict, Any
from core.preference_schema import normalize_persona
from core.itinerary_schema import (
    itinerary_has_content,
    new_empty_bundle,
    parse_trip_duration_days,
    validate_itinerary_bundle,
)

class Orchestrator:
    """
    Orchestrator manages the multi-agent execution pipeline, 
    distinguishing between initial planning and follow-up updates.
    """

    def __init__(self):
        self.persona_agent = PersonaAgent()
        self.planner_agent = PlannerAgent()
        self.replanner_agent = ReplannerAgent()
        self.destination_agent = DestinationAgent()

    def run(self, user_input: str) -> Dict[str, Any]:
        """
        Executes the agent pipeline, branching for follow-up requests.
        """
        state = get_state()

        # Check if this is a follow-up (itinerary exists)
        if itinerary_has_content(state.itinerary):
            # 1. Update Persona
            persona = self.persona_agent.execute({"user_input": user_input}, {"persona": state.persona})

            # 2. Emit update event
            emit_event(EventType.USER_EDIT, {"input": user_input}, source="Orchestrator")

            # 3. Replanning
            replanning = self.replanner_agent.execute({"itinerary": state.itinerary}, {"persona": persona})

            # 4. Store
            final_state = update_state({
                "user_input": user_input,
                "persona": persona,
                "itinerary": replanning["updated_itinerary"]
            })

            return {
                "persona": persona,
                "itinerary": replanning["updated_itinerary"],
                "last_updated": final_state.last_updated.isoformat()
            }

        # Check for Destination Selection follow-up
        if state.conversation_phase == "destination_selection":
            persona = self.persona_agent.execute({"user_input": user_input}, {})
            persona["destination"] = user_input
            # Continue to Planning
            location = persona["destination"]
            pois, _osm = fetch_pois(location)
            itinerary = self.planner_agent.execute({"persona": persona, "pois": pois}, {})
            bundle = itinerary.get("itinerary") or new_empty_bundle()

            final_state = update_state({
                "user_input": user_input,
                "persona": persona,
                "itinerary": bundle,
                "pois": pois,
                "conversation_phase": "generated"
            })

            return {
                "persona": persona,
                "itinerary": bundle,
                "last_updated": final_state.last_updated.isoformat()
            }

        # 1. Resolve Destination
        dest_result = self.destination_agent.execute({"user_input": user_input}, {})
        if dest_result["status"] == "needs_selection":
            update_state({"conversation_phase": "destination_selection"})
            return dest_result
        if dest_result["status"] == "unclear":
            return dest_result

        # 2. Persona Transformation
        persona = self.persona_agent.execute({"user_input": user_input}, {})
        persona["destination"] = dest_result["destination"]
        
        # 3. Planning
        location = persona["destination"]
        pois, _osm = fetch_pois(location)
        itinerary = self.planner_agent.execute({"persona": persona, "pois": pois}, {})
        bundle = itinerary.get("itinerary") or new_empty_bundle()

        # 4. State
        final_state = update_state({
            "user_input": user_input,
            "persona": persona,
            "itinerary": bundle,
            "pois": pois,
            "conversation_phase": "generated"
        })

        return {
            "persona": persona,
            "itinerary": bundle,
            "last_updated": final_state.last_updated.isoformat()
        }

    def generate_from_structured_persona(self, persona: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """
        Generates an itinerary from a finalized structured persona.
        If no POIs / empty plan, does not mark conversation as generated.
        """
        persona = normalize_persona(persona)
        location = (persona.get("destination") or "Paris").strip() or "Paris"
        pois, osm_status = fetch_pois(location)

        if not pois:
            fail = "no_pois"
            if osm_status in ("timeout", "http_error"):
                fail = "overpass_unavailable"
            final_state = update_state(
                {
                    "user_input": user_input,
                    "persona": persona,
                    "itinerary": new_empty_bundle(),
                    "pois": [],
                    "conversation_phase": "collecting_preferences",
                    "partial_persona": persona,
                    "pending_question": None,
                }
            )
            return {
                "success": False,
                "failure": fail,
                "persona": persona,
                "current_itinerary": new_empty_bundle(),
                "last_updated": final_state.last_updated.isoformat(),
            }

        itinerary = self.planner_agent.execute({"persona": persona, "pois": pois}, {})
        bundle = itinerary.get("itinerary")
        expected = parse_trip_duration_days(str(persona.get("trip_duration", "")))
        ok = (
            isinstance(bundle, dict)
            and validate_itinerary_bundle(bundle, expected_days=expected)
        )

        if not ok:
            final_state = update_state(
                {
                    "user_input": user_input,
                    "persona": persona,
                    "itinerary": new_empty_bundle(),
                    "pois": pois,
                    "conversation_phase": "collecting_preferences",
                    "partial_persona": persona,
                    "pending_question": None,
                }
            )
            return {
                "success": False,
                "failure": "planner_failed",
                "persona": persona,
                "current_itinerary": new_empty_bundle(),
                "last_updated": final_state.last_updated.isoformat(),
            }

        final_state = update_state(
            {
                "user_input": user_input,
                "persona": persona,
                "itinerary": bundle,
                "pois": pois,
                "conversation_phase": "generated",
                "partial_persona": persona,
                "pending_question": None,
            }
        )
        return {
            "success": True,
            "persona": persona,
            "current_itinerary": bundle,
            "last_updated": final_state.last_updated.isoformat(),
        }
