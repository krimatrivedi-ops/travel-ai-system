from typing import Dict, Any
from events.event_bus import emit_event, EventType

def check_and_emit_events(last_weather: Dict[str, Any], current_weather: Dict[str, Any]):
    """
    Checks for weather changes and emits events if specific conditions (like rain) are met.
    """
    if last_weather.get("condition") != current_weather.get("condition"):
        if current_weather.get("condition") == "rain":
            emit_event(
                EventType.WEATHER_CHANGE,
                {
                    "severity": "high",
                    "condition": "rain",
                    "previous_condition": last_weather.get("condition")
                },
                source="WeatherWatcher"
            )
