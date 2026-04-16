"""Unit tests for services.weather_service (mocked HTTP)."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from services import weather_service


@pytest.fixture(autouse=True)
def clear_weather_cache() -> None:
    with weather_service._cache_lock:
        weather_service._cache.clear()
    yield
    with weather_service._cache_lock:
        weather_service._cache.clear()


def _daily_payload(d_iso: str) -> dict:
    return {
        "daily": {
            "time": [d_iso],
            "temperature_2m_max": [22.0],
            "temperature_2m_min": [14.0],
            "precipitation_probability_max": [10],
            "weathercode": [0],
        }
    }


@patch.object(weather_service.requests, "Session")
def test_fetch_daily_weather_success(mock_session_cls: MagicMock) -> None:
    d = date(2026, 6, 1)
    mock_sess = MagicMock()
    mock_session_cls.return_value = mock_sess
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _daily_payload(d.isoformat())
    mock_sess.get.return_value = mock_resp

    out = weather_service.fetch_daily_weather(48.8566, 2.3522, d)

    assert out["weather_availability"] == "ok"
    assert out["weather_error"] is None
    assert out["weather_source"] == "open-meteo"
    assert out["forecast_date"] == d.isoformat()
    assert out["condition"] == "clear"
    assert "High" in (out["temp"] or "")
    assert out["weather_fetched_at"]
    mock_sess.get.assert_called()
    call_kw = mock_sess.get.call_args
    assert call_kw[0][0] == weather_service.OPEN_METEO_FORECAST_URL


def test_fetch_daily_weather_missing_coordinates() -> None:
    d = date(2026, 6, 1)
    out = weather_service.fetch_daily_weather(None, None, d)
    assert out["weather_availability"] == "unavailable"
    assert out["weather_error"] == "missing_coordinates"


@patch.object(weather_service.requests, "Session")
def test_fetch_daily_weather_api_failure(mock_session_cls: MagicMock) -> None:
    d = date(2026, 6, 1)
    mock_sess = MagicMock()
    mock_session_cls.return_value = mock_sess
    mock_sess.get.side_effect = weather_service.requests.RequestException("network")

    out = weather_service.fetch_daily_weather(10.0, 20.0, d)

    assert out["weather_availability"] == "unavailable"
    assert out["weather_error"] == "api_failure"
    assert out["weather_fetched_at"]


@patch.object(weather_service.requests, "Session")
def test_fetch_daily_weather_malformed_daily_fields(mock_session_cls: MagicMock) -> None:
    """HTTP 200 with non-numeric daily values must not crash the planner."""
    d = date(2026, 6, 1)
    mock_sess = MagicMock()
    mock_session_cls.return_value = mock_sess
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "daily": {
            "time": [d.isoformat()],
            "temperature_2m_max": ["not-a-number"],
            "temperature_2m_min": [14.0],
            "precipitation_probability_max": [10],
            "weathercode": [0],
        }
    }
    mock_sess.get.return_value = mock_resp

    out = weather_service.fetch_daily_weather(10.0, 20.0, d)
    assert out["weather_availability"] == "unavailable"
    assert out["weather_error"] == "parse_error"


@patch.object(weather_service.requests, "Session")
def test_fetch_daily_weather_parse_error(mock_session_cls: MagicMock) -> None:
    d = date(2026, 6, 1)
    mock_sess = MagicMock()
    mock_session_cls.return_value = mock_sess
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"daily": {"time": []}}
    mock_sess.get.return_value = mock_resp

    out = weather_service.fetch_daily_weather(10.0, 20.0, d)
    assert out["weather_availability"] == "unavailable"
    assert out["weather_error"] == "parse_error"


@patch.object(weather_service.requests, "Session")
def test_cache_second_call_skips_http(mock_session_cls: MagicMock) -> None:
    d = date(2026, 7, 15)
    mock_sess = MagicMock()
    mock_session_cls.return_value = mock_sess
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _daily_payload(d.isoformat())
    mock_sess.get.return_value = mock_resp

    weather_service.fetch_daily_weather(1.0, 2.0, d)
    weather_service.fetch_daily_weather(1.0, 2.0, d)
    assert mock_sess.get.call_count == 1
