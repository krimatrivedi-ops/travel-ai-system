"""
PDF export for saved itineraries (Story 2.3).

Uses **fpdf2** (pure Python). Text is normalized to Latin-1-safe strings for core PDF fonts
(Helvetica); non-Latin characters are replaced so generation never raises encoding errors.

Does **not** call weather or pricing APIs — only serializes fields already present in the
stored ``itinerary_bundle`` snapshot.
"""
from __future__ import annotations

import re
from io import BytesIO
from typing import Any, Dict, List, Optional, Set, Tuple

from fpdf import FPDF
from fpdf.enums import XPos, YPos

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def pdf_attachment_filename(record: Dict[str, Any]) -> str:
    """
    ASCII-safe filename for Content-Disposition. Pattern:
    {destination_slug}_{start}_{end}_{id_prefix}.pdf
    """
    dest = str(record.get("destination") or "trip").strip() or "trip"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", dest).strip("_")[:48] or "trip"
    ts = _date_part(record.get("trip_date_start"))
    te = _date_part(record.get("trip_date_end"))
    sid = str(record.get("id") or "")[:8]
    parts = [p for p in (slug, ts, te, sid) if p]
    base = "_".join(parts) + ".pdf"
    if len(base) > 180:
        base = (slug[:24] or "trip") + "_" + sid + ".pdf"
    return base


def build_itinerary_pdf_bytes(record: Dict[str, Any]) -> bytes:
    """
    Build a PDF from a ``get_saved_itinerary`` row (dict with id, destination,
    trip_date_start, trip_date_end, created_at, persona_snapshot, itinerary_bundle).
    """
    bundle = record.get("itinerary_bundle") or {}
    if not isinstance(bundle, dict):
        bundle = {}

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.set_margins(14, 14, 14)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    title = _latin1_safe(str(record.get("destination") or "Itinerary"))
    pdf.cell(w=0, h=9, text=title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(
        w=0,
        h=5,
        text=_latin1_safe("Exported from stored trip data (historical snapshot)."),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    tr = _format_trip_dates(record.get("trip_date_start"), record.get("trip_date_end"))
    if tr:
        pdf.cell(w=0, h=5, text=_latin1_safe(f"Trip dates: {tr}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    ca = record.get("created_at")
    if ca:
        pdf.cell(
            w=0,
            h=5,
            text=_latin1_safe(f"Saved (UTC): {ca}"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    pdf.ln(3)

    epw = pdf.epw
    days = bundle.get("days") if isinstance(bundle.get("days"), list) else []
    source_lines: List[str] = []
    seen_sources: Set[str] = set()

    for day in days:
        if not isinstance(day, dict):
            continue
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_x(pdf.l_margin)
        day_label = f"Day {day.get('day', '?')}"
        dt = day.get("title") or day.get("summary") or ""
        line = f"{day_label}: {_truncate(_latin1_safe(str(dt)), 120)}"
        pdf.multi_cell(w=epw, h=6, text=line)
        pdf.set_font("Helvetica", "", 9)
        summ = day.get("summary")
        if summ and str(summ).strip():
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(
                w=epw,
                h=5,
                text=_truncate(_latin1_safe(str(summ)), 500),
            )

        segs = day.get("segments") if isinstance(day.get("segments"), list) else []
        for seg in segs:
            if not isinstance(seg, dict):
                continue
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_x(pdf.l_margin)
            head = " · ".join(
                _latin1_safe(str(x))
                for x in (seg.get("time_label"), seg.get("title"))
                if x
            )
            place = seg.get("place_name") or ""
            if place:
                head = (head + " - " if head else "") + _latin1_safe(str(place))
            if not head.strip():
                head = "Activity"
            pdf.multi_cell(w=epw, h=5, text=_latin1_safe(_truncate(head, 200)))
            pdf.set_font("Helvetica", "", 9)
            desc = seg.get("description")
            if desc and str(desc).strip():
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(w=epw, h=4, text=_truncate(_latin1_safe(str(desc)), 800))
            # Keys match v2 segments from core.itinerary_schema.normalize_bundle_from_llm
            for key, label in (
                ("meal_suggestion", "Meal"),
                ("transport_note", "Getting around"),
                ("local_tip", "Tip"),
            ):
                v = seg.get(key)
                if v and str(v).strip():
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(
                        w=epw,
                        h=4,
                        text=_truncate(_latin1_safe(f"{label}: {v}"), 300),
                    )

            wx_lines, wx_src = _segment_weather_lines(seg)
            for wl in wx_lines:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(w=epw, h=4, text=wl)
            if wx_src and wx_src not in seen_sources:
                seen_sources.add(wx_src)
                source_lines.append(wx_src)

            pr_lines = _segment_pricing_lines(seg)
            for pl in pr_lines:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(w=epw, h=4, text=pl)

            pdf.ln(1)

        pr_day = day.get("pricing_rollups") if isinstance(day.get("pricing_rollups"), dict) else None
        if pr_day:
            dl = _day_rollup_line(pr_day)
            if dl:
                pdf.set_font("Helvetica", "I", 8)
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(w=epw, h=4, text=dl)
                pdf.set_font("Helvetica", "", 9)
        pdf.ln(2)

    _append_bundle_rollups(pdf, bundle)

    if source_lines:
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_x(pdf.l_margin)
        pdf.cell(w=epw, h=6, text="Sources (snapshot metadata)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 8)
        for sl in source_lines[:40]:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(w=epw, h=4, text=_truncate(sl, 500))

    out = BytesIO()
    pdf.output(out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _date_part(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return s[:10] if s else ""


def _format_trip_dates(start: Any, end: Any) -> str:
    a, b = _date_part(start), _date_part(end)
    if a and b:
        return f"{a} - {b}"
    return a or b or ""


def _latin1_safe(s: str) -> str:
    if not s:
        return ""
    return s.encode("latin-1", "replace").decode("latin-1")


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _segment_weather_lines(seg: Dict[str, Any]) -> Tuple[List[str], Optional[str]]:
    """Returns display lines and an optional single footnote line for the Sources section."""
    lines: List[str] = []
    footnote: Optional[str] = None
    avail = seg.get("weather_availability")

    if avail == "unavailable":
        msg = "Weather unavailable."
        err = seg.get("weather_error")
        if err == "missing_coordinates":
            msg = "Weather unavailable - no coordinates for this stop."
        elif err == "api_failure":
            msg = "Weather unavailable - the weather service did not respond."
        elif err == "parse_error":
            msg = "Weather unavailable - could not read forecast for this date."
        lines.append(_latin1_safe(msg))
        return lines, footnote

    if avail == "ok":
        parts_cond: List[str] = []
        if seg.get("condition"):
            parts_cond.append(str(seg["condition"]).replace("_", " "))
        if seg.get("temp"):
            parts_cond.append(str(seg["temp"]))
        if seg.get("precipitation_probability_max") is not None:
            parts_cond.append(f"rain prob (max): {seg['precipitation_probability_max']}%")
        head = "Weather: " + (" - ".join(parts_cond) if parts_cond else "(no detail)")
        lines.append(_latin1_safe(head))
        src = str(seg.get("weather_source") or "")
        fetched = str(seg.get("weather_fetched_at") or "")
        fd = str(seg.get("forecast_date") or "")
        detail_bits = [f"source={src}"] if src else []
        if fd:
            detail_bits.append(f"forecast_date={fd}")
        if fetched:
            detail_bits.append(f"fetched_utc={fetched}")
        if detail_bits:
            lines.append(_latin1_safe(" · ".join(detail_bits)))
        if src or fetched:
            footnote = _latin1_safe(
                f"Weather: source_id={src or 'n/a'}; fetched_utc={fetched or 'n/a'}"
            )
        return lines, footnote

    return lines, footnote


def _segment_pricing_lines(seg: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    p = seg.get("pricing")
    if not isinstance(p, dict):
        return lines
    if p.get("availability") == "ok" and p.get("amount") is not None:
        cur = str(p.get("currency") or "").strip() or "?"
        lines.append(
            _latin1_safe(f"Price (API-backed): {p['amount']} {cur}")
        )
        sid = p.get("source_id")
        fat = p.get("fetched_at")
        bits = []
        if sid:
            bits.append(f"source_id={sid}")
        if fat:
            bits.append(f"fetched_utc={fat}")
        if bits:
            lines.append(_latin1_safe(" · ".join(bits)))
    else:
        reason = p.get("reason") or "Price not available from integrated sources."
        lines.append(_latin1_safe(f"Pricing: {reason}"))
    return lines


def _day_rollup_line(pr_day: Dict[str, Any]) -> str:
    sub = pr_day.get("api_backed_subtotal")
    cur = pr_day.get("currency")
    note = pr_day.get("coverage_note")
    if sub is not None and cur:
        return _latin1_safe(
            f"Day subtotal (API-backed lines only): {sub} {cur}"
        )
    if note:
        return _latin1_safe(str(note))
    return ""


def _append_bundle_rollups(pdf: FPDF, bundle: Dict[str, Any]) -> None:
    epw = pdf.epw
    fx = bundle.get("pricing_reference_fx")
    if isinstance(fx, dict) and fx.get("availability") == "ok":
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_x(pdf.l_margin)
        pdf.cell(
            w=epw,
            h=6,
            text="Reference exchange rates",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.set_font("Helvetica", "", 8)
        base = fx.get("base_currency")
        rates = fx.get("rates") or {}
        rd = fx.get("rate_date")
        fat = fx.get("fetched_at")
        bits = [f"base={base}"] if base else []
        if isinstance(rates, dict) and rates:
            bits.append("rates=" + ",".join(f"{k}:{v}" for k, v in list(rates.items())[:12]))
        if rd:
            bits.append(f"rate_date={rd}")
        if fat:
            bits.append(f"fetched_utc={fat}")
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(w=epw, h=4, text=_latin1_safe(" · ".join(bits)))
        disc = fx.get("disclaimer")
        if disc:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(w=epw, h=4, text=_truncate(_latin1_safe(str(disc)), 400))
    elif isinstance(fx, dict) and fx.get("availability") == "unavailable":
        pdf.set_font("Helvetica", "", 8)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(
            w=epw,
            h=4,
            text=_latin1_safe(f"Reference FX: {fx.get('reason', 'Unavailable')}"),
        )

    pr = bundle.get("pricing_rollups") if isinstance(bundle.get("pricing_rollups"), dict) else None
    trip = pr.get("trip") if pr and isinstance(pr.get("trip"), dict) else None
    if not trip:
        return
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_x(pdf.l_margin)
    pdf.cell(
        w=epw,
        h=6,
        text="Trip pricing rollup",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.set_font("Helvetica", "", 9)
    sub = trip.get("api_backed_subtotal")
    cur = trip.get("currency")
    n_ok = trip.get("lines_with_api_price")
    n_tot = trip.get("lines_total")
    cov = trip.get("coverage_note")
    pdf.set_x(pdf.l_margin)
    if sub is not None and cur:
        pdf.multi_cell(
            w=epw,
            h=5,
            text=_latin1_safe(
                f"Trip subtotal (API-backed lines only): {sub} {cur}"
                + (f" ({n_ok} of {n_tot} lines)" if n_ok is not None and n_tot is not None else "")
            ),
        )
    elif cov:
        pdf.multi_cell(w=epw, h=5, text=_latin1_safe(str(cov)))
    else:
        pdf.multi_cell(w=epw, h=5, text="No API-backed line item totals in snapshot.")
