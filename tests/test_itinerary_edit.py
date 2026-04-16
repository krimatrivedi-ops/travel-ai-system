"""Tests for itinerary edit validation and persistence APIs."""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

import pytest

from core.itinerary_schema import ITINERARY_VERSION, finalize_edited_bundle, validate_edited_itinerary_bundle
from services import itinerary_store


@pytest.fixture
def db_path(tmp_path) -> str:
    p = str(tmp_path / "edit_test.sqlite3")
    itinerary_store.set_database_path_for_tests(p)
    yield p
    itinerary_store.set_database_path_for_tests(None)


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


def test_validate_edited_rejects_empty_place() -> None:
    b = _minimal_bundle()
    b["days"][0]["segments"][0]["place_name"] = "   "
    errs = validate_edited_itinerary_bundle(b)
    assert any("place_name" in e for e in errs)


def test_finalize_edited_bundle_rollups() -> None:
    b = _minimal_bundle()
    out = finalize_edited_bundle(b)
    assert out["pricing_rollups"]["trip"]["lines_total"] == 1


def test_finalize_clears_stale_weather_when_coords_removed() -> None:
    """Editing away lat/lon must not leave API-ok weather or snapshot fields (Epic 1)."""
    b = _minimal_bundle()
    seg = b["days"][0]["segments"][0]
    seg["lat"] = 48.8566
    seg["lon"] = 2.3522
    seg["weather_availability"] = "ok"
    seg["condition"] = "clear"
    seg["temp"] = "18°C"
    seg["weather_source"] = "open-meteo"
    seg["weather_fetched_at"] = "2026-04-15T12:00:00Z"
    del seg["lat"]
    del seg["lon"]
    out = finalize_edited_bundle(b)
    seg2 = out["days"][0]["segments"][0]
    assert seg2.get("weather_availability") == "unavailable"
    assert seg2.get("weather_error") == "missing_coordinates"
    assert seg2.get("condition") is None
    assert seg2.get("temp") is None
    assert seg2.get("weather_source") is None


def test_update_saved_roundtrip(db_path: str) -> None:
    persona = {
        "destination": "X",
        "trip_duration": "1 day",
        "trip_start_date": "2026-06-01",
        "travel_style": "cultural",
        "food_priority": 5,
        "walking_tolerance": "medium",
        "pace": "moderate",
        "budget_sensitivity": "medium",
    }
    bundle = _minimal_bundle()
    sid = itinerary_store.save_generated_itinerary(persona, bundle)
    b2 = _minimal_bundle()
    b2["days"][0]["summary"] = "Updated summary"
    fin = finalize_edited_bundle(b2)
    itinerary_store.update_saved_itinerary_bundle(sid, fin)
    row = itinerary_store.get_saved_itinerary(sid)
    assert row is not None
    assert row["itinerary_bundle"]["days"][0]["summary"] == "Updated summary"


def test_put_itinerary_400_invalid() -> None:
    from app import app

    bad = {"itinerary_version": 2, "days": []}
    with TestClient(app) as client:
        res = client.put("/itinerary", json={"itinerary": bad})
    assert res.status_code == 400
    assert "errors" in res.json()["detail"]


@patch("app.enrich_itinerary_pricing")
def test_put_itinerary_200(mock_enrich, db_path: str) -> None:
    from app import app
    from state.store import reset_state, update_state

    reset_state()
    b = _minimal_bundle()
    update_state({"itinerary": b})
    b2 = _minimal_bundle()
    b2["days"][0]["summary"] = "New"
    with TestClient(app) as client:
        res = client.put("/itinerary", json={"itinerary": b2})
    assert res.status_code == 200
    data = res.json()
    assert data["itinerary"]["days"][0]["summary"] == "New"
    reset_state()


def test_put_saved_404(db_path: str) -> None:
    from app import app

    b = _minimal_bundle()
    with TestClient(app) as client:
        res = client.put(
            "/saved/00000000-0000-4000-8000-000000000001",
            json={"itinerary_bundle": b},
        )
    assert res.status_code == 404


@patch("app.enrich_itinerary_pricing")
def test_put_saved_200(mock_enrich, db_path: str) -> None:
    from app import app

    persona = {
        "destination": "Y",
        "trip_duration": "1 day",
        "trip_start_date": "2026-06-01",
        "travel_style": "cultural",
        "food_priority": 5,
        "walking_tolerance": "medium",
        "pace": "moderate",
        "budget_sensitivity": "medium",
    }
    sid = itinerary_store.save_generated_itinerary(persona, _minimal_bundle())
    b2 = _minimal_bundle()
    b2["days"][0]["summary"] = "Edited saved"
    with TestClient(app) as client:
        res = client.put(f"/saved/{sid}", json={"itinerary_bundle": b2})
    assert res.status_code == 200
    row = itinerary_store.get_saved_itinerary(sid)
    assert row is not None
    assert row["itinerary_bundle"]["days"][0]["summary"] == "Edited saved"
