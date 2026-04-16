"""Tests for optimization merge / segment patch."""
from __future__ import annotations

from unittest.mock import patch

from core.itinerary_schema import ITINERARY_VERSION
from core.optimization_merge import (
    apply_recommendation_to_bundle,
    fuzzy_match_candidate,
    patch_segment_with_place,
)


def test_patch_segment_appends_description_for_food() -> None:
    seg: dict = {
        "description": "Original plan text.",
        "title": "Lunch",
        "place_name": "Old Place",
        "meal_suggestion": None,
        "lat": 1.0,
        "lon": 1.0,
    }
    place = {"name": "New Cafe", "lat": "48.0", "lon": "2.0", "type": "restaurant"}
    patch_segment_with_place(seg, place, "New Cafe")
    assert "Original plan text." in seg["description"]
    assert "Stop updated to: New Cafe" in seg["description"]
    assert seg["place_name"] == "New Cafe"


def test_patch_culture_sets_visit_title() -> None:
    seg: dict = {
        "description": "",
        "title": "Morning",
        "place_name": "TBD",
        "meal_suggestion": None,
    }
    place = {"name": "City Museum", "lat": "1", "lon": "2", "type": "museum"}
    patch_segment_with_place(seg, place, "City Museum")
    assert seg["title"] == "Visit City Museum"
    assert "City Museum" in seg["description"]


def test_apply_recommendation_updates_segment() -> None:
    bundle = {
        "itinerary_version": ITINERARY_VERSION,
        "days": [
            {
                "day": 1,
                "segments": [
                    {
                        "time_label": "12:00",
                        "title": "Lunch",
                        "place_name": "Any",
                        "description": "x",
                        "meal_suggestion": None,
                        "lat": 1.0,
                        "lon": 1.0,
                    }
                ],
            }
        ],
    }
    recs = [{"name": "Pick Me"}]
    cands = [{"name": "Pick Me", "lat": "10", "lon": "20", "type": "restaurant"}]
    snap = {"meal_edit": {"flat_segment_index": 0}}
    out = apply_recommendation_to_bundle(bundle, 0, recs, cands, snap)
    seg = out["days"][0]["segments"][0]
    assert seg["place_name"] == "Pick Me"
    assert "Stop updated" in seg["description"]


def test_apply_recommendation_prefers_explicit_target() -> None:
    bundle = {
        "itinerary_version": ITINERARY_VERSION,
        "days": [
            {
                "day": 1,
                "segments": [
                    {
                        "time_label": "Morning",
                        "title": "Walk",
                        "place_name": "Keep1",
                        "description": "a",
                        "meal_suggestion": None,
                    },
                    {
                        "time_label": "Noon",
                        "title": "Lunch",
                        "place_name": "Keep2",
                        "description": "b",
                        "meal_suggestion": None,
                    },
                ],
            }
        ],
    }
    recs = [{"name": "Target Cafe"}]
    cands = [{"name": "Target Cafe", "lat": "1", "lon": "2", "type": "restaurant"}]
    snap = {"meal_edit": {"flat_segment_index": 1}}
    out = apply_recommendation_to_bundle(
        bundle,
        0,
        recs,
        cands,
        snap,
        target_day_index=0,
        target_segment_index=0,
    )
    assert out["days"][0]["segments"][0]["place_name"] == "Target Cafe"
    assert out["days"][0]["segments"][1]["place_name"] == "Keep2"


def test_apply_recommendation_invalid_explicit_target_raises() -> None:
    bundle = {
        "itinerary_version": ITINERARY_VERSION,
        "days": [{"day": 1, "segments": [{"title": "A", "place_name": "Old", "description": "x"}]}],
    }
    recs = [{"name": "Target"}]
    cands = [{"name": "Target", "type": "restaurant"}]
    try:
        apply_recommendation_to_bundle(
            bundle,
            0,
            recs,
            cands,
            None,
            target_day_index=2,
            target_segment_index=0,
        )
    except ValueError as e:
        assert "target_day_index" in str(e)
    else:
        raise AssertionError("Expected ValueError for invalid target_day_index")


def test_fuzzy_match_no_unsafe_first_candidate_fallback() -> None:
    cands = [
        {"name": "Spice Court", "lat": "1", "lon": "2", "type": "restaurant"},
        {"name": "Other Cafe", "lat": "3", "lon": "4", "type": "restaurant"},
    ]
    assert fuzzy_match_candidate("Amer Fort", cands) is None


def test_apply_recommendation_geocode_fallback() -> None:
    bundle = {
        "itinerary_version": ITINERARY_VERSION,
        "days": [
            {
                "day": 1,
                "segments": [
                    {
                        "time_label": "12:00",
                        "title": "Lunch",
                        "place_name": "Any",
                        "description": "x",
                        "meal_suggestion": None,
                        "lat": 1.0,
                        "lon": 1.0,
                    }
                ],
            }
        ],
    }
    recs = [{"name": "Amer Fort"}]
    cands = [
        {"name": "Spice Court", "lat": "10", "lon": "20", "type": "restaurant"},
    ]
    snap = {"meal_edit": {"flat_segment_index": 0}}

    def _geo(name: str, hint: object) -> dict:
        assert name == "Amer Fort"
        return {"name": "Amer Fort", "lat": "26.98", "lon": "75.85", "type": "attraction"}

    with patch("core.optimization_merge.geocode_place_candidate", side_effect=_geo):
        out = apply_recommendation_to_bundle(
            bundle, 0, recs, cands, snap, destination_hint="Jaipur"
        )
    seg = out["days"][0]["segments"][0]
    assert seg["place_name"] == "Amer Fort"
    assert abs(float(seg["lat"]) - 26.98) < 0.01


def test_fetch_optimization_candidates_unified_mode() -> None:
    import services.osm_service as osm_mod

    with patch.object(
        osm_mod,
        "fetch_unified_optimization_pois",
        return_value=([{"name": "A", "lat": "1", "lon": "2", "type": "museum"}], "ok"),
    ):
        c, st, label = osm_mod.fetch_optimization_candidates("Paris", "ignored")
    assert label == "unified"
    assert st == "ok"
    assert len(c) == 1
    assert c[0]["name"] == "A"
