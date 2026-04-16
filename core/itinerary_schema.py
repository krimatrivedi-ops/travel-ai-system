"""
Versioned multi-day itinerary structure (v2) for summary table + detail modal.
"""
from __future__ import annotations

import re
import copy
from typing import Any, Dict, FrozenSet, List, Optional

ITINERARY_VERSION = 2

# Segment line prices must come from merge code that sets source_id here (not LLM output).
ALLOWED_SEGMENT_PRICING_SOURCES: FrozenSet[str] = frozenset()
MIN_DAYS = 1
MAX_DAYS = 14


def parse_trip_duration_days(trip_duration: str) -> int:
    """
    Extract number of days from free text (e.g. '5 days', 'long weekend' -> 3, 'one week' -> 7).
    Clamped to MIN_DAYS..MAX_DAYS.
    """
    if not trip_duration:
        return 3
    s = trip_duration.strip().lower()
    m = re.search(r"(\d+)\s*(?:day|days|night|nights)\b", s)
    if m:
        return max(MIN_DAYS, min(MAX_DAYS, int(m.group(1))))
    if "weekend" in s or "long weekend" in s:
        return min(3, MAX_DAYS)
    if "week" in s or "7 day" in s:
        return min(7, MAX_DAYS)
    if "two week" in s or "2 week" in s or "14" in s:
        return min(14, MAX_DAYS)
    if "day trip" in s or "one day" in s or "1 day" in s:
        return 1
    return 3


def new_empty_bundle() -> Dict[str, Any]:
    return {"itinerary_version": ITINERARY_VERSION, "days": []}


def default_segment_pricing() -> Dict[str, Any]:
    """No LLM-invented amounts — only enrichment from HTTP integrations may set availability ok."""
    return {
        "availability": "unavailable",
        "source_id": None,
        "fetched_at": None,
        "amount": None,
        "currency": None,
        "error_code": "no_integration",
        "reason": "Price not available from integrated sources",
    }


def qualify_budget_note(note: Optional[str]) -> Optional[str]:
    """LLM budget lines are not authoritative pricing; prefix when not already qualified."""
    if not note or not str(note).strip():
        return None
    s = str(note).strip()
    if s.lower().startswith("non-binding"):
        return s
    return f"Non-binding (qualitative pacing only — not a price quote): {s}"


def _segment_pricing_must_reset_untrusted(p: Dict[str, Any]) -> bool:
    """True if this pricing dict claims API-backed money without a trusted integration source."""
    if p.get("availability") != "ok":
        return False
    if p.get("amount") is None:
        return False
    sid = p.get("source_id")
    return sid not in ALLOWED_SEGMENT_PRICING_SOURCES


def ensure_segment_pricing_defaults(bundle: Dict[str, Any]) -> None:
    """Ensure each segment has a pricing object; drop LLM-invented amounts (replanner path)."""
    if not isinstance(bundle, dict) or bundle.get("itinerary_version") != ITINERARY_VERSION:
        return
    for day in bundle.get("days") or []:
        if not isinstance(day, dict):
            continue
        for seg in day.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            if not isinstance(seg.get("pricing"), dict):
                seg["pricing"] = default_segment_pricing()
                continue
            if _segment_pricing_must_reset_untrusted(seg["pricing"]):
                seg["pricing"] = default_segment_pricing()


def compute_pricing_rollups(bundle: Dict[str, Any]) -> None:
    """
    Day and trip rollups: sums include only segments with pricing.availability == 'ok' and numeric amount.
    Mixed currencies on API-backed lines → trip subtotal omitted with coverage note.
    """
    if not isinstance(bundle, dict) or bundle.get("itinerary_version") != ITINERARY_VERSION:
        return

    days = bundle.get("days") or []
    trip_amounts: List[float] = []
    trip_currencies: List[str] = []
    lines_total = 0
    lines_ok = 0

    for day in days:
        if not isinstance(day, dict):
            continue
        d_amt: List[float] = []
        d_cur: List[str] = []
        for seg in day.get("segments") or []:
            lines_total += 1
            if not isinstance(seg, dict):
                continue
            p = seg.get("pricing") if isinstance(seg.get("pricing"), dict) else {}
            if p.get("availability") == "ok" and p.get("amount") is not None:
                try:
                    a = float(p["amount"])
                    c = str(p.get("currency") or "").strip().upper() or "EUR"
                    lines_ok += 1
                    d_amt.append(a)
                    d_cur.append(c)
                    trip_amounts.append(a)
                    trip_currencies.append(c)
                except (TypeError, ValueError):
                    pass

        day_cov: Optional[str] = None
        d_sub: Optional[float] = None
        d_cur_one: Optional[str] = None
        if d_amt:
            uniq = set(d_cur)
            if len(uniq) == 1:
                d_sub = sum(d_amt)
                d_cur_one = d_cur[0]
            else:
                day_cov = "Day total not shown — API-backed lines use mixed currencies."

        day["pricing_rollups"] = {
            "api_backed_subtotal": d_sub,
            "currency": d_cur_one,
            "lines_with_api_price": len(d_amt) if d_amt else 0,
            "lines_in_day": len(day.get("segments") or []),
            "coverage_note": day_cov,
        }

    trip_cov: Optional[str] = None
    trip_sub: Optional[float] = None
    trip_cur: Optional[str] = None
    if trip_amounts:
        uq = set(trip_currencies)
        if len(uq) == 1:
            trip_sub = sum(trip_amounts)
            trip_cur = trip_currencies[0]
        else:
            trip_cov = "Trip total not shown — API-backed lines use mixed currencies."
    elif lines_ok == 0 and lines_total > 0:
        trip_cov = (
            "Totals include only API-backed line prices. "
            "No line items have integrated prices yet."
        )

    bundle["pricing_rollups"] = {
        "trip": {
            "api_backed_subtotal": trip_sub,
            "currency": trip_cur,
            "lines_with_api_price": lines_ok,
            "lines_total": lines_total,
            "coverage_note": trip_cov,
        }
    }


def itinerary_has_content(itinerary: Any) -> bool:
    """True if we have a non-empty v2 bundle or legacy non-empty list."""
    if not itinerary:
        return False
    if isinstance(itinerary, list):
        return len(itinerary) > 0
    if isinstance(itinerary, dict):
        if itinerary.get("itinerary_version") == ITINERARY_VERSION:
            days = itinerary.get("days") or []
            return len(days) > 0
        return len(itinerary) > 0
    return False


def validate_itinerary_bundle(
    bundle: Any, expected_days: Optional[int] = None
) -> bool:
    """Validate v2 shape; optionally require len(days)==expected_days."""
    if not isinstance(bundle, dict):
        return False
    if bundle.get("itinerary_version") != ITINERARY_VERSION:
        return False
    days = bundle.get("days")
    if not isinstance(days, list) or len(days) == 0:
        return False
    if expected_days is not None and len(days) != expected_days:
        return False
    for d in days:
        if not isinstance(d, dict):
            return False
        segs = d.get("segments")
        if not isinstance(segs, list) or len(segs) == 0:
            return False
        for seg in segs:
            if not isinstance(seg, dict):
                return False
            if not str(seg.get("place_name", "")).strip():
                return False
            if not str(seg.get("time_label", "")).strip():
                return False
    return True


def validate_edited_itinerary_bundle(bundle: Any) -> List[str]:
    """
    Structural validation for user-edited v2 bundles. Returns a list of error messages;
    empty means valid. Minimum segment fields: time_label, title, place_name (non-empty).
    """
    errors: List[str] = []
    if not isinstance(bundle, dict):
        return ["itinerary must be an object"]
    if bundle.get("itinerary_version") != ITINERARY_VERSION:
        errors.append("itinerary_version must be 2")
    days = bundle.get("days")
    if not isinstance(days, list) or len(days) == 0:
        errors.append("days must be a non-empty array")
        return errors
    if len(days) > MAX_DAYS:
        errors.append(f"at most {MAX_DAYS} days allowed")
    for i, d in enumerate(days):
        if not isinstance(d, dict):
            errors.append(f"days[{i}] must be an object")
            continue
        segs = d.get("segments")
        if not isinstance(segs, list) or len(segs) == 0:
            errors.append(f"Day {i + 1} must have at least one segment")
            continue
        for j, seg in enumerate(segs):
            if not isinstance(seg, dict):
                errors.append(f"Day {i + 1}, segment {j + 1}: must be an object")
                continue
            if not str(seg.get("place_name", "")).strip():
                errors.append(f"Day {i + 1}, segment {j + 1}: place_name is required")
            if not str(seg.get("time_label", "")).strip():
                errors.append(f"Day {i + 1}, segment {j + 1}: time_label is required")
            if not str(seg.get("title", "")).strip():
                errors.append(f"Day {i + 1}, segment {j + 1}: title is required")
    return errors


def _clear_segment_api_weather_fields(seg: Dict[str, Any]) -> None:
    """Remove API snapshot fields when coordinates are absent (no invented forecasts)."""
    for key in (
        "condition",
        "temp",
        "precipitation_probability_max",
        "forecast_date",
        "weather_source",
        "weather_fetched_at",
    ):
        if key in seg:
            seg[key] = None


def ensure_segment_weather_consistency(bundle: Dict[str, Any]) -> None:
    """
    Segments without coordinates cannot have API-ok weather; force unavailable (Epic 1).
    """
    if not isinstance(bundle, dict) or bundle.get("itinerary_version") != ITINERARY_VERSION:
        return
    for day in bundle.get("days") or []:
        if not isinstance(day, dict):
            continue
        for seg in day.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            lat, lon = seg.get("lat"), seg.get("lon")
            has_coords = lat is not None and lon is not None
            if not has_coords:
                if seg.get("weather_availability") == "ok":
                    seg["weather_availability"] = "unavailable"
                    seg["weather_error"] = "missing_coordinates"
                _clear_segment_api_weather_fields(seg)


def normalize_day_indices(bundle: Dict[str, Any]) -> None:
    """Ensure day.day is 1..n in order (after edits)."""
    if not isinstance(bundle, dict) or bundle.get("itinerary_version") != ITINERARY_VERSION:
        return
    days = bundle.get("days")
    if not isinstance(days, list):
        return
    for i, day in enumerate(days):
        if isinstance(day, dict):
            day["day"] = i + 1


def finalize_edited_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep copy, normalize day numbers, weather/pricing consistency, recompute rollups.
    """
    out = copy.deepcopy(bundle)
    normalize_day_indices(out)
    ensure_segment_weather_consistency(out)
    ensure_segment_pricing_defaults(out)
    compute_pricing_rollups(out)
    return out


def normalize_bundle_from_llm(
    raw: Dict[str, Any], expected_days: int, candidates: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Ensure version, trim days, backfill missing place_name from OSM candidates by fuzzy match."""
    days_in = raw.get("days") if isinstance(raw, dict) else None
    if not isinstance(days_in, list):
        return new_empty_bundle()

    days_out: List[Dict[str, Any]] = []
    cand_names = [c.get("name") for c in candidates if c.get("name")]
    fallback_place = cand_names[0] if cand_names else "City center"

    for i, d in enumerate(days_in[:expected_days]):
        if not isinstance(d, dict):
            continue
        segs_in = d.get("segments") if isinstance(d.get("segments"), list) else []
        segs: List[Dict[str, Any]] = []
        for j, seg in enumerate(segs_in):
            if not isinstance(seg, dict):
                continue
            place = str(seg.get("place_name") or seg.get("place") or "").strip()
            if not place and cand_names:
                place = str(cand_names[j % len(cand_names)])
            if not place:
                place = fallback_place
            tl = str(seg.get("time_label") or seg.get("time") or "").strip()
            if not tl:
                tl = f"Block {j + 1}"
            segs.append(
                {
                    "time_label": tl,
                    "title": str(seg.get("title") or seg.get("activity") or "Activity").strip(),
                    "place_name": place,
                    "description": str(seg.get("description") or "").strip(),
                    "meal_suggestion": (str(seg.get("meal_suggestion") or "").strip() or None),
                    "transport_note": (str(seg.get("transport_note") or "").strip() or None),
                    "local_tip": (str(seg.get("local_tip") or "").strip() or None),
                    "lat": seg.get("lat"),
                    "lon": seg.get("lon"),
                    "pricing": default_segment_pricing(),
                }
            )
        if not segs:
            continue
        days_out.append(
            {
                "day": int(d.get("day", len(days_out) + 1)),
                "title": str(d.get("title") or d.get("theme") or f"Day {len(days_out) + 1}").strip(),
                "summary": str(d.get("summary") or "").strip(),
                "segments": segs,
                "accommodation": (str(d.get("accommodation") or "").strip() or None),
                "dining_highlight": (str(d.get("dining_highlight") or "").strip() or None),
                "estimated_daily_budget_note": qualify_budget_note(
                    str(d.get("estimated_daily_budget_note") or "").strip() or None
                ),
            }
        )

    # Pad missing days if short (shouldn't happen often)
    while len(days_out) < expected_days:
        idx = len(days_out)
        days_out.append(
            {
                "day": idx + 1,
                "title": f"Day {idx + 1}",
                "summary": "See destination highlights.",
                "segments": [
                    {
                        "time_label": "Daytime",
                        "title": "Explore the area",
                        "place_name": fallback_place,
                        "description": "Walk the main sights and local spots.",
                        "meal_suggestion": None,
                        "transport_note": None,
                        "local_tip": None,
                        "lat": None,
                        "lon": None,
                        "pricing": default_segment_pricing(),
                    }
                ],
                "accommodation": None,
                "dining_highlight": None,
                "estimated_daily_budget_note": None,
            }
        )

    return {"itinerary_version": ITINERARY_VERSION, "days": days_out[:expected_days]}
