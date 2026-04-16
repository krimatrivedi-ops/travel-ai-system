"""Planner attaches weather fields when fetch_daily_weather is mocked."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from agents.planner_agent import PlannerAgent
from core.itinerary_schema import ITINERARY_VERSION


@patch("agents.planner_agent.enrich_itinerary_pricing")
@patch("agents.planner_agent.fetch_daily_weather")
def test_planner_merges_weather_metadata(mock_fetch: MagicMock, mock_enrich: MagicMock) -> None:
    mock_enrich.side_effect = lambda *_a, **_k: None
    mock_fetch.return_value = {
        "weather_availability": "ok",
        "weather_error": None,
        "weather_source": "open-meteo",
        "weather_fetched_at": "2026-04-15T12:00:00Z",
        "forecast_date": "2026-04-15",
        "forecast_window_note": "Daily aggregate",
        "condition": "clear",
        "temp": "High 20°C · Low 12°C",
        "precipitation_probability_max": 5,
    }

    agent = PlannerAgent()
    persona = {
        "destination": "TestCity",
        "trip_duration": "1 day",
        "travel_style": "cultural",
        "food_priority": 7,
        "walking_tolerance": "medium",
        "pace": "moderate",
        "budget_sensitivity": "medium",
        "trip_start_date": "2026-04-15",
    }
    pois = [
        {
            "name": "Museum One",
            "type": "museum",
            "lat": 48.0,
            "lon": 2.0,
        }
    ]

    llm_json = """
    {
      "days": [
        {
          "day": 1,
          "title": "Day one",
          "summary": "See the museum.",
          "segments": [
            {
              "time_label": "Morning",
              "title": "Visit",
              "place_name": "Museum One",
              "description": "Art.",
              "lat": 48.0,
              "lon": 2.0
            },
            {
              "time_label": "Afternoon",
              "title": "Walk",
              "place_name": "Museum One",
              "description": "More.",
              "lat": 48.0,
              "lon": 2.0
            },
            {
              "time_label": "Evening",
              "title": "Rest",
              "place_name": "Museum One",
              "description": "Rest.",
              "lat": 48.0,
              "lon": 2.0
            }
          ],
          "accommodation": null,
          "dining_highlight": null,
          "estimated_daily_budget_note": null
        }
      ]
    }
    """

    with patch("agents.planner_agent.call_llm", return_value=llm_json):
        out = agent.execute({"persona": persona, "pois": pois}, {})

    bundle = out.get("itinerary") or {}
    assert bundle.get("itinerary_version") == ITINERARY_VERSION
    day0 = bundle["days"][0]
    seg0 = day0["segments"][0]
    assert seg0.get("weather_availability") == "ok"
    assert seg0.get("weather_source") == "open-meteo"
    assert mock_fetch.called
    first_call = mock_fetch.call_args[0]
    assert first_call[0] == 48.0 and first_call[1] == 2.0
    assert first_call[2] == date(2026, 4, 15)
