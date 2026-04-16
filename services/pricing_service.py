"""
Reference exchange rates via Frankfurter (ECB) — HTTPS only, no static price catalogs.

Venue/activity line prices are not integrated here; segment `pricing` defaults stay unavailable
until a future integration maps API responses. See docs/pricing-integration.md.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

import requests

from core.itinerary_schema import compute_pricing_rollups, ensure_segment_pricing_defaults

logger = logging.getLogger(__name__)


def _attach_fx_for_persona(bundle: Dict[str, Any], persona: Dict[str, Any]) -> None:
    display = str(persona.get("display_currency") or "USD").strip().upper()[:3]
    if not display or not display.isalpha():
        display = "USD"
    targets = [display]
    if display != "GBP":
        targets.append("GBP")
    if display != "USD" and "USD" not in targets:
        targets.append("USD")
    bundle["pricing_reference_fx"] = fetch_reference_rates("EUR", targets)

FRANKFURTER_BASE = "https://api.frankfurter.dev/v1"
PRICING_SOURCE_FRANKFURTER = "frankfurter"

PRICING_HTTP_TIMEOUT = float(os.environ.get("PRICING_HTTP_TIMEOUT", "10"))
PRICING_CACHE_TTL_SECONDS = int(os.environ.get("PRICING_CACHE_TTL_SECONDS", "3600"))
PRICING_MAX_RETRIES = int(os.environ.get("PRICING_MAX_RETRIES", "2"))

_fx_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_fx_lock = Lock()


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_reference_rates(
    base_currency: str,
    target_currencies: List[str],
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """
    Latest ECB reference rates from Frankfurter (GET /latest).
    Returns a payload suitable for bundle['pricing_reference_fx'].
    """
    base = str(base_currency or "EUR").strip().upper()[:3] or "EUR"
    targets = [str(c).strip().upper()[:3] for c in target_currencies if c]
    targets = [c for c in targets if c and c != base]
    if not targets:
        targets = ["USD"]

    cache_key = f"{base}:{','.join(sorted(targets))}"
    now_m = time.monotonic()
    with _fx_lock:
        hit = _fx_cache.get(cache_key)
        if hit is not None:
            ts, payload = hit
            if now_m - ts < PRICING_CACHE_TTL_SECONDS:
                return dict(payload)

    sess = session or requests.Session()
    url = f"{FRANKFURTER_BASE}/latest"
    params = {"from": base, "to": ",".join(targets)}
    for attempt in range(PRICING_MAX_RETRIES + 1):
        try:
            r = sess.get(url, params=params, timeout=PRICING_HTTP_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            break
        except (requests.RequestException, ValueError) as e:
            logger.warning("Frankfurter request failed (attempt %s): %s", attempt + 1, e)
            if attempt < PRICING_MAX_RETRIES:
                time.sleep(0.25 * (attempt + 1))
    else:
        payload = {
            "availability": "unavailable",
            "source_id": PRICING_SOURCE_FRANKFURTER,
            "error_code": "api_failure",
            "reason": "Could not load reference exchange rates.",
            "fetched_at": _now_iso_utc(),
            "disclaimer": (
                "ECB reference rates would appear here — not ticket, hotel, or activity prices."
            ),
        }
        with _fx_lock:
            _fx_cache[cache_key] = (time.monotonic(), dict(payload))
        return payload

    rates = data.get("rates") or {}
    rate_date = data.get("date")
    fetched = _now_iso_utc()
    payload = {
        "availability": "ok",
        "source_id": PRICING_SOURCE_FRANKFURTER,
        "fetched_at": fetched,
        "base_currency": data.get("base") or base,
        "rate_date": rate_date,
        "rates": rates,
        "disclaimer": (
            "ECB reference exchange rates (Frankfurter) — not ticket, hotel, or activity prices."
        ),
    }
    with _fx_lock:
        _fx_cache[cache_key] = (time.monotonic(), dict(payload))
    return payload


def enrich_itinerary_pricing(
    bundle: Dict[str, Any],
    persona: Dict[str, Any],
    *,
    run_price_agent: bool = True,
    force_price_agent: bool = False,
) -> None:
    """
    Ensure segment pricing defaults, API rollups, optional PricingAgent (estimated ranges),
    estimated rollups, and reference FX. Mutates bundle in place.

    Order: defaults → API rollups → PricingAgent (fills estimated_pricing) → estimated rollups → FX.
    """
    ensure_segment_pricing_defaults(bundle)
    compute_pricing_rollups(bundle)
    if run_price_agent:
        from agents.pricing_agent import PricingAgent

        PricingAgent().run(bundle, persona, force=force_price_agent)
    compute_estimated_pricing_rollups(bundle)
    _attach_fx_for_persona(bundle, persona)


def compute_estimated_pricing_rollups(bundle: Dict[str, Any]) -> None:
    """
    Sums estimated_pricing (min_amount and max_amount) across segments.
    Provides day_estimated_cost and trip_estimated_cost.
    """
    if not isinstance(bundle, dict) or "days" not in bundle:
        return

    trip_min = 0.0
    trip_max = 0.0
    trip_currency = None

    for day in bundle.get("days", []):
        day_min = 0.0
        day_max = 0.0
        day_currency = None

        for segment in day.get("segments", []):
            est = segment.get("estimated_pricing")
            if est:
                try:
                    day_min += float(est.get("min_amount", 0))
                    day_max += float(est.get("max_amount", 0))
                    if not day_currency:
                        day_currency = est.get("currency")
                except (ValueError, TypeError):
                    pass

        day["estimated_pricing_rollups"] = {
            "day_estimated_cost": {
                "min_amount": day_min,
                "max_amount": day_max,
                "currency": day_currency or "USD"
            }
        }
        
        trip_min += day_min
        trip_max += day_max
        if not trip_currency:
            trip_currency = day_currency

    bundle["estimated_pricing_rollups"] = {
        "trip_estimated_cost": {
            "min_amount": trip_min,
            "max_amount": trip_max,
            "currency": trip_currency or "USD"
        }
    }
