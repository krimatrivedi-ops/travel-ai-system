"""
Apply a chosen optimization recommendation to a v2 itinerary bundle.
Flatten order matches app.optimize: for each day in order, each segment in order.
"""
from __future__ import annotations

import copy
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from services.osm_service import geocode_place_candidate


def flatten_segments(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for day in bundle.get("days") or []:
        for seg in day.get("segments") or []:
            out.append(seg)
    return out


def flat_index_to_day_segment(bundle: Dict[str, Any], flat_index: int) -> Optional[Tuple[int, int]]:
    idx = 0
    for di, day in enumerate(bundle.get("days") or []):
        segs = day.get("segments") or []
        for si in range(len(segs)):
            if idx == flat_index:
                return (di, si)
            idx += 1
    return None


_LUNCH_HINT = re.compile(
    r"lunch|noon|midday|\b12:|\b13:|\b14:|\b11:30|brunch|meal",
    re.IGNORECASE,
)


def infer_meal_flat_segment_index(
    bundle: Dict[str, Any], snapshot: Optional[Dict[str, Any]] = None
) -> int:
    """
    Prefer meal_edit.flat_segment_index from optimization snapshot (0-based).
    Else: first segment whose labels suggest lunch/meal.
    Else: middle segment of day 0, or floor(n/2) for single stream.
    """
    flat = flatten_segments(bundle)
    n = len(flat)
    if n == 0:
        return 0

    if snapshot:
        me = snapshot.get("meal_edit")
        if isinstance(me, dict):
            raw = me.get("flat_segment_index")
            try:
                i = int(raw)
                if 0 <= i < n:
                    return i
            except (TypeError, ValueError):
                pass

    for i, seg in enumerate(flat):
        blob = " ".join(
            [
                str(seg.get("time_label") or ""),
                str(seg.get("meal_suggestion") or ""),
                str(seg.get("title") or ""),
                str(seg.get("place_name") or ""),
            ]
        )
        if _LUNCH_HINT.search(blob):
            return i

    days = bundle.get("days") or []
    if days:
        segs0 = days[0].get("segments") or []
        if segs0:
            mid = max(0, min(len(segs0) - 1, len(segs0) // 2))
            return mid

    return min(n // 2, n - 1)


def fuzzy_match_candidate(
    rec_name: str, candidates: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    if not rec_name or not candidates:
        return None
    rec_norm = rec_name.strip().lower()
    best: Optional[Dict[str, Any]] = None
    best_score = 0.0
    for c in candidates:
        cn = str(c.get("name") or "").strip().lower()
        if not cn:
            continue
        if rec_norm == cn:
            return c
        if rec_norm in cn or cn in rec_norm:
            return c
        score = SequenceMatcher(None, rec_norm, cn).ratio()
        if score > best_score:
            best_score = score
            best = c
    # Keep threshold above incidental similarity between unrelated short names (e.g. ~0.5).
    if best is not None and best_score >= 0.55:
        return best
    return None


def _place_is_culture_poi(place: Dict[str, Any]) -> bool:
    ptype = str(place.get("type") or "").lower()
    return any(
        x in ptype
        for x in ("museum", "gallery", "attraction", "tourism", "monument", "historic")
    )


def patch_segment_with_place(seg: Dict[str, Any], place: Dict[str, Any], rec_name: str) -> None:
    pname = str(place.get("name") or rec_name).strip()
    seg["place_name"] = pname
    culture = _place_is_culture_poi(place)
    title = str(seg.get("title") or "").strip()
    tl = title.lower()
    if culture:
        seg["title"] = f"Visit {pname}"
    elif not title or "meal" in tl or "lunch" in tl or "dining" in tl:
        seg["title"] = f"Meal at {pname}"
    lat = place.get("lat")
    lon = place.get("lon")
    try:
        if lat is not None:
            seg["lat"] = float(lat)
        if lon is not None:
            seg["lon"] = float(lon)
    except (TypeError, ValueError):
        pass
    desc = str(seg.get("description") or "").strip()
    note = (
        f"Stop updated to: {pname}."
        if not culture
        else f"Visit plan updated to feature {pname}."
    )
    if desc:
        seg["description"] = note
        # seg["description"] = desc + "\n\n" + note
    else:
        seg["description"] = (
            f"Spend time at {pname}." if culture else f"Enjoy your time at {pname}."
        )
    # ms = seg.get("meal_suggestion")
    # if culture:
    #     seg["meal_suggestion"] = (
    #         f"Allow time at {pname} (sightseeing)."
    #         if not (isinstance(ms, str) and ms.strip())
    #         else f"{ms.strip()} — include {pname}"
    #     )
    # else:
    #     if isinstance(ms, str) and ms.strip():
    #         seg["meal_suggestion"] = f"{ms.strip()} — {pname}"
    #     else:
    #         seg["meal_suggestion"] = f"Dine at {pname}"


def apply_recommendation_to_bundle(
    bundle: Dict[str, Any],
    selected_index: int,
    recommendations: List[Dict[str, Any]],
    candidate_places: List[Dict[str, Any]],
    snapshot: Optional[Dict[str, Any]] = None,
    target_day_index: Optional[int] = None,
    target_segment_index: Optional[int] = None,
    destination_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deep-copy bundle, patch one segment with selected venue (name + coords from OSM candidates).
    """
    if not recommendations or selected_index < 0 or selected_index >= len(recommendations):
        raise ValueError("Invalid recommendation index")
    rec = recommendations[selected_index]
    name = str(rec.get("name") or "").strip()
    if not name:
        raise ValueError("Recommendation has no name")

    place = fuzzy_match_candidate(name, candidate_places)
    if not place:
        place = geocode_place_candidate(name, destination_hint)
    if not place:
        raise ValueError(
            "Could not resolve recommendation to a place: no OSM match and geocoding failed"
        )

    out = copy.deepcopy(bundle)
    di: int
    si: int
    if target_day_index is not None or target_segment_index is not None:
        if target_day_index is None or target_segment_index is None:
            raise ValueError("Both target_day_index and target_segment_index are required")
        days = out.get("days") or []
        if target_day_index < 0 or target_day_index >= len(days):
            raise ValueError("Invalid target_day_index")
        segs = days[target_day_index].get("segments") or []
        if target_segment_index < 0 or target_segment_index >= len(segs):
            raise ValueError("Invalid target_segment_index")
        di, si = target_day_index, target_segment_index
    else:
        flat_idx = infer_meal_flat_segment_index(out, snapshot)
        pos = flat_index_to_day_segment(out, flat_idx)
        if not pos:
            raise ValueError("Could not locate segment to patch")
        di, si = pos
    days = out.get("days") or []
    if di >= len(days):
        raise ValueError("Invalid day index")
    segs = days[di].get("segments") or []
    if si >= len(segs):
        raise ValueError("Invalid segment index")
    seg = segs[si]
    patch_segment_with_place(seg, place, name)
    return out
