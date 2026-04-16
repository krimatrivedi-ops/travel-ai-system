"""App-layer tests: persistence hooks on conversation success vs failure."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.itinerary_schema import new_empty_bundle
from state.store import reset_state


@pytest.fixture(autouse=True)
def clean_state() -> None:
    reset_state()
    yield
    reset_state()


@patch("app.save_generated_itinerary")
@patch("app.engine.generate_from_structured_persona")
@patch("app.process_turn")
def test_failed_generation_does_not_call_save(
    mock_process_turn: MagicMock,
    mock_generate: MagicMock,
    mock_save: MagicMock,
) -> None:
    """When orchestration fails (no POIs / planner), no SQLite insert."""
    from app import _handle_conversation_message

    persona = {
        "destination": "NowhereLand",
        "trip_duration": "3 days",
        "travel_style": "cultural",
        "food_priority": 7,
        "walking_tolerance": "medium",
        "pace": "moderate",
        "budget_sensitivity": "medium",
    }
    mock_process_turn.return_value = (persona, True, None)
    mock_generate.return_value = {
        "success": False,
        "failure": "no_pois",
        "persona": persona,
        "current_itinerary": new_empty_bundle(),
    }

    out = _handle_conversation_message("final prefs message")

    assert out["status"] == "need_more"
    assert out.get("failure") == "no_pois"
    mock_save.assert_not_called()
