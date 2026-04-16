"""Tests for services.pricing_service (Frankfurter mocked)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services import pricing_service


@pytest.fixture(autouse=True)
def clear_fx_cache() -> None:
    with pricing_service._fx_lock:
        pricing_service._fx_cache.clear()
    yield
    with pricing_service._fx_lock:
        pricing_service._fx_cache.clear()


@patch.object(pricing_service.requests, "Session")
def test_fetch_reference_rates_success(mock_session_cls: MagicMock) -> None:
    mock_sess = MagicMock()
    mock_session_cls.return_value = mock_sess
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "amount": 1.0,
        "base": "EUR",
        "date": "2026-04-14",
        "rates": {"USD": 1.1, "GBP": 0.9},
    }
    mock_sess.get.return_value = mock_resp

    out = pricing_service.fetch_reference_rates("EUR", ["USD", "GBP"])

    assert out["availability"] == "ok"
    assert out["source_id"] == "frankfurter"
    assert out["rates"]["USD"] == 1.1
    assert "ECB reference" in out["disclaimer"]


@patch.object(pricing_service.requests, "Session")
def test_fetch_reference_rates_failure(mock_session_cls: MagicMock) -> None:
    mock_sess = MagicMock()
    mock_session_cls.return_value = mock_sess
    mock_sess.get.side_effect = pricing_service.requests.RequestException("x")

    out = pricing_service.fetch_reference_rates("EUR", ["USD"])
    assert out["availability"] == "unavailable"
    assert out["error_code"] == "api_failure"
