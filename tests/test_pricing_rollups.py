"""Rollup logic for itinerary pricing."""
from __future__ import annotations

from core.itinerary_schema import (
    ITINERARY_VERSION,
    compute_pricing_rollups,
    default_segment_pricing,
    ensure_segment_pricing_defaults,
)


def test_rollups_sum_only_api_lines() -> None:
    bundle = {
        "itinerary_version": ITINERARY_VERSION,
        "days": [
            {
                "day": 1,
                "segments": [
                    {
                        "place_name": "A",
                        "time_label": "m",
                        "pricing": {
                            "availability": "ok",
                            "amount": 10.0,
                            "currency": "EUR",
                            "source_id": "test",
                            "fetched_at": "2026-01-01T00:00:00Z",
                        },
                    },
                    {
                        "place_name": "B",
                        "time_label": "a",
                        "pricing": default_segment_pricing(),
                    },
                ],
            }
        ],
    }
    compute_pricing_rollups(bundle)
    assert bundle["pricing_rollups"]["trip"]["api_backed_subtotal"] == 10.0
    assert bundle["pricing_rollups"]["trip"]["currency"] == "EUR"
    assert bundle["pricing_rollups"]["trip"]["lines_with_api_price"] == 1
    assert bundle["pricing_rollups"]["trip"]["lines_total"] == 2


def test_rollups_mixed_currency_omits_trip_sum() -> None:
    bundle = {
        "itinerary_version": ITINERARY_VERSION,
        "days": [
            {
                "day": 1,
                "segments": [
                    {
                        "place_name": "A",
                        "time_label": "m",
                        "pricing": {
                            "availability": "ok",
                            "amount": 10.0,
                            "currency": "EUR",
                            "source_id": "t",
                            "fetched_at": "x",
                        },
                    },
                    {
                        "place_name": "B",
                        "time_label": "a",
                        "pricing": {
                            "availability": "ok",
                            "amount": 5.0,
                            "currency": "USD",
                            "source_id": "t",
                            "fetched_at": "x",
                        },
                    },
                ],
            }
        ],
    }
    compute_pricing_rollups(bundle)
    assert bundle["pricing_rollups"]["trip"]["api_backed_subtotal"] is None
    assert "mixed" in (bundle["pricing_rollups"]["trip"]["coverage_note"] or "").lower()


def test_normalize_bundle_includes_default_pricing() -> None:
    from core.itinerary_schema import normalize_bundle_from_llm

    raw = {
        "days": [
            {
                "day": 1,
                "title": "T",
                "summary": "S",
                "segments": [
                    {
                        "time_label": "Morning",
                        "title": "X",
                        "place_name": "Place",
                        "description": "D",
                    },
                    {
                        "time_label": "Noon",
                        "title": "Y",
                        "place_name": "Place2",
                        "description": "E",
                    },
                    {
                        "time_label": "Eve",
                        "title": "Z",
                        "place_name": "Place3",
                        "description": "F",
                    },
                ],
            }
        ]
    }
    b = normalize_bundle_from_llm(raw, 1, [{"name": "Place", "lat": 1, "lon": 2}])
    seg = b["days"][0]["segments"][0]
    assert seg["pricing"]["availability"] == "unavailable"
    assert seg["pricing"]["amount"] is None


def test_ensure_segment_pricing_strips_untrusted_llm_amounts() -> None:
    """Replanner-style bundles cannot keep fake API line prices without an allowlisted source_id."""
    bundle = {
        "itinerary_version": ITINERARY_VERSION,
        "days": [
            {
                "day": 1,
                "segments": [
                    {
                        "place_name": "A",
                        "time_label": "m",
                        "pricing": {
                            "availability": "ok",
                            "amount": 999.0,
                            "currency": "EUR",
                            "source_id": "llm-hallucination",
                            "fetched_at": "2026-01-01T00:00:00Z",
                        },
                    },
                ],
            }
        ],
    }
    ensure_segment_pricing_defaults(bundle)
    p = bundle["days"][0]["segments"][0]["pricing"]
    assert p["availability"] == "unavailable"
    assert p["amount"] is None
