"""Tests for saved itinerary list API and store summaries."""
from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

import pytest

from services import itinerary_store


@pytest.fixture
def db_path(tmp_path) -> str:
    p = str(tmp_path / "list_test.sqlite3")
    itinerary_store.set_database_path_for_tests(p)
    yield p
    itinerary_store.set_database_path_for_tests(None)


def test_list_summaries_order_and_shape(db_path: str) -> None:
    """Newest first; keys match GET /saved contract."""
    p1 = {
        "destination": "Alpha",
        "trip_duration": "2 days",
        "trip_start_date": "2026-06-01",
        "travel_style": "cultural",
        "food_priority": 5,
        "walking_tolerance": "medium",
        "pace": "moderate",
        "budget_sensitivity": "medium",
    }
    b1 = {"itinerary_version": 2, "days": [{"day": 1, "title": "First day theme", "segments": []}]}
    id1 = itinerary_store.save_generated_itinerary(p1, b1)

    p2 = {
        "destination": "Beta",
        "trip_duration": "1 day",
        "trip_start_date": "2026-07-01",
        "travel_style": "cultural",
        "food_priority": 5,
        "walking_tolerance": "medium",
        "pace": "moderate",
        "budget_sensitivity": "medium",
    }
    b2 = {"itinerary_version": 2, "days": [{"day": 1, "title": "Second trip", "segments": []}]}
    id2 = itinerary_store.save_generated_itinerary(p2, b2)

    # Same-second timestamps can tie-break unpredictably; force strict newest-first.
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE saved_itineraries SET created_at = ? WHERE id = ?",
        ("2099-12-31T00:00:00+00:00", id2),
    )
    conn.commit()
    conn.close()

    rows = itinerary_store.list_saved_itinerary_summaries()
    assert len(rows) == 2
    assert rows[0]["id"] == id2
    assert rows[1]["id"] == id1
    assert rows[0]["title"] == "Second trip"
    assert rows[0]["destination"] == "Beta"
    for r in rows:
        assert set(r.keys()) == {
            "id",
            "title",
            "destination",
            "trip_date_start",
            "trip_date_end",
            "created_at",
        }


def test_get_saved_route_returns_json_array(db_path: str) -> None:
    from app import app

    persona = {
        "destination": "Gamma",
        "trip_duration": "1 day",
        "trip_start_date": "2026-08-01",
        "travel_style": "cultural",
        "food_priority": 5,
        "walking_tolerance": "medium",
        "pace": "moderate",
        "budget_sensitivity": "medium",
    }
    bundle = {"itinerary_version": 2, "days": []}
    itinerary_store.save_generated_itinerary(persona, bundle)

    with TestClient(app) as client:
        res = client.get("/saved")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["destination"] == "Gamma"
