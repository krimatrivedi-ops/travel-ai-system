"""
Live weather from Open-Meteo (HTTPS). Per-day forecast aligned to trip dates — no static climate tables.

See docs/weather-integration.md for provider terms, cache TTL, and environment variables.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any, Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_SOURCE_ID = "open-meteo"

# Tunable via env (documented in docs/weather-integration.md)
WEATHER_HTTP_TIMEOUT = float(os.environ.get("WEATHER_HTTP_TIMEOUT", "10"))
WEATHER_CACHE_TTL_SECONDS = int(os.environ.get("WEATHER_CACHE_TTL_SECONDS", "900"))
WEATHER_MAX_RETRIES = int(os.environ.get("WEATHER_MAX_RETRIES", "2"))

# In-process TTL cache: key (lat, lon, date_iso) -> (monotonic_time, payload)
_cache: Dict[Tuple[str, str, str], Tuple[float, Dict[str, Any]]] = {}
_cache_lock = Lock()


def _coerce_lat_lon(lat: Any, lon: Any) -> Optional[Tuple[float, float]]:
    try:
        if lat is None or lon is None:
            return None
        la = float(lat)
        lo = float(lon)
        if not (-90 <= la <= 90 and -180 <= lo <= 180):
            return None
        return (la, lo)
    except (TypeError, ValueError):
        return None


def _wmo_code_to_condition(code: Optional[float]) -> str:
    """Map WMO weathercode to a short English label (Open-Meteo daily)."""
    if code is None:
        return "unavailable"
    c = int(round(float(code)))
    if c == 0:
        return "clear"
    if c in (1, 2, 3):
        return "partly_cloudy"
    if c in (45, 48):
        return "fog"
    if 51 <= c <= 67:
        return "rain"
    if 71 <= c <= 77:
        return "snow"
    if 80 <= c <= 82 or c == 66 or c == 67:
        return "rain_showers"
    if 95 <= c <= 99:
        return "thunderstorm"
    return "cloudy"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _unavailable_payload(
    *,
    forecast_date: date,
    error_code: str,
    fetched_at: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "weather_availability": "unavailable",
        "weather_error": error_code,
        "weather_source": WEATHER_SOURCE_ID,
        "weather_fetched_at": fetched_at,
        "forecast_date": forecast_date.isoformat(),
        "forecast_window_note": f"Daily forecast for {forecast_date.isoformat()} (local calendar day).",
        "condition": None,
        "temp": None,
        "precipitation_probability_max": None,
    }


def fetch_daily_weather(
    lat: Any,
    lon: Any,
    forecast_date: date,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """
    Fetch one day of forecast from Open-Meteo for (lat, lon) on forecast_date.

    Returns a dict suitable for merging onto itinerary segments, including
    weather_availability, metadata, and display fields.
    """
    coords = _coerce_lat_lon(lat, lon)
    if coords is None:
        return _unavailable_payload(forecast_date=forecast_date, error_code="missing_coordinates")

    la, lo = coords
    lat_s = f"{la:.5f}"
    lon_s = f"{lo:.5f}"
    d_iso = forecast_date.isoformat()
    cache_key = (lat_s, lon_s, d_iso)

    now_m = time.monotonic()
    with _cache_lock:
        hit = _cache.get(cache_key)
        if hit is not None:
            ts, payload = hit
            if now_m - ts < WEATHER_CACHE_TTL_SECONDS:
                return dict(payload)

    sess = session or requests.Session()
    params = {
        "latitude": la,
        "longitude": lo,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
        "start_date": d_iso,
        "end_date": d_iso,
        "timezone": "auto",
    }
    url = OPEN_METEO_FORECAST_URL

    for attempt in range(WEATHER_MAX_RETRIES + 1):
        try:
            r = sess.get(url, params=params, timeout=WEATHER_HTTP_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            break
        except (requests.RequestException, ValueError) as e:
            logger.warning("Open-Meteo request failed (attempt %s): %s", attempt + 1, e)
            if attempt < WEATHER_MAX_RETRIES:
                time.sleep(0.3 * (attempt + 1))
    else:
        fetched = _now_iso()
        payload = _unavailable_payload(
            forecast_date=forecast_date,
            error_code="api_failure",
            fetched_at=fetched,
        )
        with _cache_lock:
            _cache[cache_key] = (time.monotonic(), dict(payload))
        return payload

    daily = data.get("daily") or {}
    times = daily.get("time") or []
    if not times or d_iso not in times:
        logger.warning("Open-Meteo response missing expected date %s: %s", d_iso, data)
        fetched = _now_iso()
        payload = _unavailable_payload(
            forecast_date=forecast_date,
            error_code="parse_error",
            fetched_at=fetched,
        )
        with _cache_lock:
            _cache[cache_key] = (time.monotonic(), dict(payload))
        return payload

    idx = times.index(d_iso)
    tmax = (daily.get("temperature_2m_max") or [None])[idx]
    tmin = (daily.get("temperature_2m_min") or [None])[idx]
    pprob = (daily.get("precipitation_probability_max") or [None])[idx]
    wcode = (daily.get("weathercode") or [None])[idx]

    try:
        condition = _wmo_code_to_condition(wcode)
        fetched = _now_iso()

        tmax_s = f"{float(tmax):.0f}°C" if tmax is not None else None
        tmin_s = f"{float(tmin):.0f}°C" if tmin is not None else None
        if tmax_s and tmin_s:
            temp_label = f"High {tmax_s} · Low {tmin_s}"
        elif tmax_s:
            temp_label = f"High {tmax_s}"
        else:
            temp_label = None

        payload = {
            "weather_availability": "ok",
            "weather_error": None,
            "weather_source": WEATHER_SOURCE_ID,
            "weather_fetched_at": fetched,
            "forecast_date": d_iso,
            "forecast_window_note": f"Daily aggregate for {d_iso} (Open-Meteo, timezone=auto).",
            "condition": condition,
            "temp": temp_label,
            "temperature_max_c": float(tmax) if tmax is not None else None,
            "temperature_min_c": float(tmin) if tmin is not None else None,
            "precipitation_probability_max": int(pprob) if pprob is not None else None,
            "weathercode": int(wcode) if wcode is not None else None,
        }
    except (TypeError, ValueError) as e:
        logger.warning("Open-Meteo daily field parse failed for %s: %s", d_iso, e)
        fetched = _now_iso()
        payload = _unavailable_payload(
            forecast_date=forecast_date,
            error_code="parse_error",
            fetched_at=fetched,
        )
        with _cache_lock:
            _cache[cache_key] = (time.monotonic(), dict(payload))
        return payload

    with _cache_lock:
        _cache[cache_key] = (time.monotonic(), dict(payload))
    return payload


def get_weather(lat: str, lon: str) -> Dict[str, Any]:
    """
    Backwards-compatible wrapper: current-day forecast at (lat, lon).
    Prefer fetch_daily_weather for trip-aligned data.
    """
    return fetch_daily_weather(lat, lon, date.today())
