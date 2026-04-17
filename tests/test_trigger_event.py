"""ReactiveEngine.trigger_event with client-provided itinerary when session is empty."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from agents.replanner_agent import ReplannerAgent
from core.itinerary_schema import ITINERARY_VERSION
from events.event_bus import EventType
from runtime.engine import ReactiveEngine
from runtime.orchestrator import Orchestrator
from state.store import get_state, reset_state


@pytest.fixture
def engine() -> ReactiveEngine:
    return ReactiveEngine(Orchestrator(), ReplannerAgent())


def minimal_v2_bundle() -> dict:
    return {
        "itinerary_version": ITINERARY_VERSION,
        "days": [
            {
                "day": 1,
                "title": "Day one",
                "summary": "Summary",
                "segments": [
                    {
                        "time_label": "9:00",
                        "title": "Visit",
                        "place_name": "Museum",
                        "description": "Indoor",
                    }
                ],
            }
        ],
    }


def test_trigger_event_uses_client_bundle_when_session_empty(engine: ReactiveEngine) -> None:
    reset_state()
    assert not (get_state().itinerary or {}).get("days")

    b = minimal_v2_bundle()

    def fake_execute(self, input_data, state):
        assert input_data["itinerary"] == b
        return {"updated_itinerary": input_data["itinerary"], "changes": ["Swapped for rain"]}

    with patch.object(ReplannerAgent, "execute", fake_execute):
        with patch("runtime.engine.enrich_itinerary_pricing"):
            out = engine.trigger_event(
                EventType.WEATHER_CHANGE,
                {"condition": "rain"},
                itinerary_bundle=b,
            )

    assert out["status"] == "updated"
    assert out["changes_applied"] == ["Swapped for rain"]
    assert get_state().itinerary.get("itinerary_version") == ITINERARY_VERSION


def test_trigger_event_ignored_without_bundle_when_session_empty(engine: ReactiveEngine) -> None:
    reset_state()

    def should_not_run(*_a, **_k):
        raise AssertionError("replanner should not run when no itinerary")

    with patch.object(ReplannerAgent, "execute", should_not_run):
        out = engine.trigger_event(EventType.WEATHER_CHANGE, {"condition": "rain"})

    assert out["status"] == "ignored"
    assert out.get("reason") == "itinerary_empty"
