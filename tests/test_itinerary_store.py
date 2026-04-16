"""Tests for services.itinerary_store."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services import itinerary_store


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    p = str(tmp_path / "test.sqlite3")
    itinerary_store.set_database_path_for_tests(p)
    yield p
    itinerary_store.set_database_path_for_tests(None)


def test_save_and_get_roundtrip(db_path: str) -> None:
    persona = {
        "destination": "Lisbon",
        "trip_duration": "3 days",
        "travel_style": "cultural",
        "food_priority": 7,
        "walking_tolerance": "medium",
        "pace": "moderate",
        "budget_sensitivity": "medium",
        "trip_start_date": "2026-05-01",
    }
    bundle = {
        "itinerary_version": 2,
        "days": [],
        "pricing_reference_fx": {"availability": "ok", "source_id": "frankfurter"},
    }
    sid = itinerary_store.save_generated_itinerary(persona, bundle)
    assert len(sid) == 36

    loaded = itinerary_store.get_saved_itinerary(sid)
    assert loaded is not None
    assert loaded["id"] == sid
    assert loaded["destination"] == "Lisbon"
    assert loaded["trip_date_start"] == "2026-05-01"
    assert loaded["persona_snapshot"]["destination"] == "Lisbon"
    assert loaded["itinerary_bundle"]["pricing_reference_fx"]["source_id"] == "frankfurter"


def test_get_saved_missing(db_path: str) -> None:
    assert itinerary_store.get_saved_itinerary("00000000-0000-0000-0000-000000000000") is None


def test_get_saved_corrupt_json_returns_none(db_path: str) -> None:
    persona = {"destination": "X", "trip_duration": "1 day"}
    bundle = {"itinerary_version": 2, "days": []}
    sid = itinerary_store.save_generated_itinerary(persona, bundle)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE saved_itineraries SET persona_snapshot = ? WHERE id = ?",
        ("NOT JSON", sid),
    )
    conn.commit()
    conn.close()
    assert itinerary_store.get_saved_itinerary(sid) is None


def test_save_includes_segment_enrichment_placeholders(db_path: str) -> None:
    """Ensure we do not strip weather/pricing fields from stored JSON."""
    persona = {"destination": "X", "trip_duration": "1 day"}
    bundle = {
        "itinerary_version": 2,
        "days": [
            {
                "day": 1,
                "title": "T",
                "summary": "S",
                "segments": [
                    {
                        "time_label": "Morning",
                        "title": "A",
                        "place_name": "P",
                        "description": "D",
                        "weather_source": "open-meteo",
                        "weather_fetched_at": "2026-01-01T00:00:00Z",
                        "pricing": {
                            "availability": "unavailable",
                            "source_id": None,
                        },
                    },
                    {
                        "time_label": "Noon",
                        "title": "B",
                        "place_name": "P2",
                        "description": "E",
                    },
                    {
                        "time_label": "Eve",
                        "title": "C",
                        "place_name": "P3",
                        "description": "F",
                    },
                ],
            }
        ],
    }
    sid = itinerary_store.save_generated_itinerary(persona, bundle)
    loaded = itinerary_store.get_saved_itinerary(sid)
    seg = loaded["itinerary_bundle"]["days"][0]["segments"][0]
    assert seg.get("weather_source") == "open-meteo"
    assert seg.get("pricing", {}).get("availability") == "unavailable"
