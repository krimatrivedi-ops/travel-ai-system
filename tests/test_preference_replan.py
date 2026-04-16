"""Story 3.2 — preference snapshot merge and replan persistence."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from core.itinerary_schema import ITINERARY_VERSION
from core.preference_schema import merge_trip_snapshot_with_partial
from services import itinerary_store


@pytest.fixture
def db_path(tmp_path) -> str:
    p = str(tmp_path / "pref_replan.sqlite3")
    itinerary_store.set_database_path_for_tests(p)
    yield p
    itinerary_store.set_database_path_for_tests(None)


def _full_persona() -> dict:
    return {
        "destination": "Lisbon",
        "trip_duration": "3 days",
        "travel_style": "cultural",
        "food_priority": 7,
        "walking_tolerance": "medium",
        "pace": "moderate",
        "budget_sensitivity": "medium",
    }


def _minimal_bundle() -> dict:
    return {
        "itinerary_version": ITINERARY_VERSION,
        "days": [
            {
                "day": 1,
                "title": "D1",
                "summary": "S",
                "segments": [
                    {
                        "time_label": "AM",
                        "title": "Walk",
                        "place_name": "Park",
                        "description": "x",
                        "pricing": {
                            "availability": "unavailable",
                            "reason": "Price not available from integrated sources",
                        },
                    }
                ],
            }
        ],
    }


def test_merge_trip_snapshot_with_partial_fills_from_snapshot() -> None:
    snap = _full_persona()
    out = merge_trip_snapshot_with_partial(snap, {})
    assert out["destination"] == "Lisbon"
    assert out["pace"] == "moderate"


def test_merge_trip_snapshot_with_partial_session_overrides() -> None:
    snap = _full_persona()
    out = merge_trip_snapshot_with_partial(snap, {"pace": "relaxed", "food_priority": 9})
    assert out["destination"] == "Lisbon"
    assert out["pace"] == "relaxed"
    assert out["food_priority"] == 9


def test_merge_without_snapshot_is_partial_only() -> None:
    out = merge_trip_snapshot_with_partial(None, {"destination": "Porto"})
    assert out == {"destination": "Porto"}


def test_merge_blank_partial_values_do_not_wipe_snapshot() -> None:
    snap = _full_persona()
    out = merge_trip_snapshot_with_partial(
        snap,
        {"destination": "   ", "pace": "relaxed", "food_priority": None},
    )
    assert out["destination"] == "Lisbon"
    assert out["pace"] == "relaxed"
    assert out["food_priority"] == 7


def test_update_saved_itinerary_after_replan_roundtrip(db_path: str) -> None:
    p0 = _full_persona()
    b0 = _minimal_bundle()
    sid = itinerary_store.save_generated_itinerary(p0, b0)
    p1 = {**p0, "pace": "relaxed"}
    b1 = _minimal_bundle()
    b1["days"][0]["title"] = "Replanned day"
    itinerary_store.update_saved_itinerary_after_replan(sid, p1, b1)
    row = itinerary_store.get_saved_itinerary(sid)
    assert row is not None
    assert row["persona_snapshot"]["pace"] == "relaxed"
    assert row["itinerary_bundle"]["days"][0]["title"] == "Replanned day"


def test_conversation_message_unknown_saved_id_returns_404(db_path: str) -> None:
    from app import app

    with TestClient(app) as client:
        res = client.post(
            "/conversation/message",
            json={
                "message": "hello",
                "saved_itinerary_id": "00000000-0000-4000-8000-000000000099",
            },
        )
    assert res.status_code == 404


@patch("app.engine.generate_from_structured_persona")
@patch("app.process_turn")
def test_conversation_replan_updates_same_row(
    mock_turn, mock_gen, db_path: str
) -> None:
    from app import app
    from state.store import reset_state

    reset_state()
    persona = _full_persona()
    bundle0 = _minimal_bundle()
    sid = itinerary_store.save_generated_itinerary(persona, bundle0)
    mock_turn.return_value = (persona, True, None)
    bundle1 = _minimal_bundle()
    bundle1["days"][0]["title"] = "AI replanned"
    mock_gen.return_value = {
        "success": True,
        "current_itinerary": bundle1,
        "persona": persona,
    }
    with TestClient(app) as client:
        res = client.post(
            "/conversation/message",
            json={"message": "more relaxed pace please", "saved_itinerary_id": sid},
        )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "generated"
    assert data["saved_itinerary_id"] == sid
    assert data.get("replan_from_saved") is True
    assert data.get("preference_scope") == "trip_saved"
    row = itinerary_store.get_saved_itinerary(sid)
    assert row is not None
    assert row["itinerary_bundle"]["days"][0]["title"] == "AI replanned"
    rows = itinerary_store.list_saved_itinerary_summaries()
    assert len(rows) == 1
    reset_state()
