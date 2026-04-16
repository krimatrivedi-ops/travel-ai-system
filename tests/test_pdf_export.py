"""Tests for PDF export of saved itineraries."""
from __future__ import annotations

from fastapi.testclient import TestClient

import pytest

from services import itinerary_store
from services.pdf_export import build_itinerary_pdf_bytes
from core.itinerary_schema import ITINERARY_VERSION


@pytest.fixture
def db_path(tmp_path) -> str:
    p = str(tmp_path / "pdf_test.sqlite3")
    itinerary_store.set_database_path_for_tests(p)
    yield p
    itinerary_store.set_database_path_for_tests(None)


def test_build_pdf_bytes_starts_with_pdf_header(db_path: str) -> None:
    persona = {
        "destination": "TestCity",
        "trip_duration": "1 day",
        "trip_start_date": "2026-06-01",
        "travel_style": "cultural",
        "food_priority": 5,
        "walking_tolerance": "medium",
        "pace": "moderate",
        "budget_sensitivity": "medium",
    }
    bundle = {
        "itinerary_version": ITINERARY_VERSION,
        "days": [
            {
                "day": 1,
                "title": "City stroll",
                "summary": "Walk the old town.",
                "segments": [
                    {
                        "time_label": "Morning",
                        "title": "Explore",
                        "place_name": "Old Town",
                        "description": "Coffee and sights.",
                        "meal_suggestion": "Pastry at the square",
                        "transport_note": "Walk",
                        "local_tip": "Arrive early.",
                        "weather_availability": "unavailable",
                        "weather_error": "missing_coordinates",
                        "pricing": {
                            "availability": "unavailable",
                            "reason": "Price not available from integrated sources",
                        },
                    }
                ],
            }
        ],
    }
    sid = itinerary_store.save_generated_itinerary(persona, bundle)
    row = itinerary_store.get_saved_itinerary(sid)
    assert row is not None
    raw = build_itinerary_pdf_bytes(row)
    assert raw.startswith(b"%PDF")
    assert len(raw) > 200
    # Segment extras use v2 keys (meal_suggestion, transport_note, local_tip); PDF bytes may not
    # contain plain-text substrings depending on fpdf2 stream encoding.


def test_get_saved_pdf_404_unknown_id(db_path: str) -> None:
    from app import app

    with TestClient(app) as client:
        res = client.get(
            "/saved/00000000-0000-4000-8000-000000000001/pdf",
        )
    assert res.status_code == 404


def test_get_saved_pdf_ok(db_path: str) -> None:
    from app import app

    persona = {
        "destination": "PDFDest",
        "trip_duration": "1 day",
        "trip_start_date": "2026-06-01",
        "travel_style": "cultural",
        "food_priority": 5,
        "walking_tolerance": "medium",
        "pace": "moderate",
        "budget_sensitivity": "medium",
    }
    bundle = {"itinerary_version": ITINERARY_VERSION, "days": []}
    sid = itinerary_store.save_generated_itinerary(persona, bundle)

    with TestClient(app) as client:
        res = client.get(f"/saved/{sid}/pdf")
    assert res.status_code == 200
    assert res.headers.get("content-type", "").startswith("application/pdf")
    cd = res.headers.get("content-disposition", "")
    assert "attachment" in cd.lower()
    assert ".pdf" in cd
    body = res.content
    assert body.startswith(b"%PDF")
