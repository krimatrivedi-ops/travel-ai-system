import logging
import time
from typing import Any, Dict, Optional

from agents.replanner_agent import ReplannerAgent
from core.preference_schema import normalize_persona
from events.event_bus import EventType, emit_event, get_events
from core.itinerary_schema import itinerary_has_content
from runtime.orchestrator import Orchestrator
from services.pricing_service import enrich_itinerary_pricing
from state.store import get_state, update_state

logger = logging.getLogger(__name__)


class ReactiveEngine:
    """
    ReactiveEngine manages the event-driven lifecycle and continuous evolution of the system.
    """

    def __init__(self, orchestrator: Orchestrator, replanner: ReplannerAgent):
        self.orchestrator = orchestrator
        self.replanner = replanner

    def run_once(self, user_input: str) -> Dict[str, Any]:
        """Runs the initial generation pipeline (single-shot heuristic persona)."""
        result = self.orchestrator.run(user_input)
        return {
            "status": "initial_plan_generated",
            "current_itinerary": result.get("itinerary"),
            "persona": result.get("persona")
        }

    def generate_from_structured_persona(self, persona: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """Build itinerary from a completed structured persona (after preference collection)."""
        result = self.orchestrator.generate_from_structured_persona(persona, user_input)
        return {
            "success": result.get("success", False),
            "failure": result.get("failure"),
            "current_itinerary": result.get("current_itinerary"),
            "persona": result.get("persona"),
        }

    def trigger_event(
        self,
        event_type: EventType,
        payload: Dict[str, Any],
        *,
        itinerary_bundle: Optional[Dict[str, Any]] = None,
        persona_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Triggers the patch-based replanning process."""
        logger.debug("trigger_event: %s payload=%s", event_type, payload)
        emit_event(event_type, payload, source="ReactiveEngine")

        state = get_state()
        base_itinerary: Optional[Dict[str, Any]] = None
        if itinerary_bundle is not None and itinerary_has_content(itinerary_bundle):
            base_itinerary = itinerary_bundle
        elif itinerary_has_content(state.itinerary):
            base_itinerary = state.itinerary

        if base_itinerary is None:
            logger.warning("trigger_event: no itinerary (session empty and no client bundle)")
            return {
                "status": "ignored",
                "reason": "itinerary_empty",
                "event_processed": False,
            }

        state_payload = dict(state.__dict__)
        if persona_override:
            state_payload["persona"] = {
                **(state.persona or {}),
                **persona_override,
            }

        replanning_result = self.replanner.execute(
            {"itinerary": base_itinerary},
            state_payload,
        )

        new_itinerary = replanning_result["updated_itinerary"]
        logger.debug(
            "replanner returned itinerary has_content=%s",
            itinerary_has_content(new_itinerary),
        )

        if itinerary_has_content(new_itinerary):
            persona = normalize_persona(state_payload.get("persona") or state.persona or {})
            enrich_itinerary_pricing(
                new_itinerary, persona, run_price_agent=True, force_price_agent=True
            )
            update_payload: Dict[str, Any] = {"itinerary": new_itinerary}
            if persona_override and not (state.persona or {}):
                update_payload["persona"] = normalize_persona(
                    {**(state.persona or {}), **persona_override}
                )
            update_state(update_payload)

            return {
                "status": "updated",
                "event_processed": True,
                "current_itinerary": new_itinerary,
                "changes_applied": replanning_result.get("changes", []),
            }

        logger.warning("replanner returned empty itinerary")
        return {
            "status": "error",
            "reason": "replanner_returned_empty",
            "event_processed": False,
        }

    def reactive_loop(self):
        """
        Simulates the continuous event-driven loop.
        In a production system, this would be an async task or message queue consumer.
        """
        print("Starting reactive loop... (Ctrl+C to stop)")
        try:
            while True:
                events = get_events()
                # Simplified loop: if events exist, process the latest one
                if events:
                    # Logic to process pending events
                    pass
                
                time.sleep(5)
        except KeyboardInterrupt:
            print("Loop stopped.")

    def get_current_state(self) -> Dict[str, Any]:
        """Returns the current system state."""
        state = get_state()
        return {
            "itinerary": state.itinerary,
            "persona": state.persona,
            "events": [e.__dict__ for e in get_events()],
            "last_updated": state.last_updated.isoformat(),
            "conversation_phase": state.conversation_phase,
            "partial_persona": state.partial_persona,
            "pending_question": state.pending_question,
            "conversation_messages": state.conversation_messages,
        }
