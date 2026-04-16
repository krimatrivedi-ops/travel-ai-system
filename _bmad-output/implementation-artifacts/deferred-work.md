# Deferred work

## Deferred from: code review (2026-04-15) — 1-1-weather-via-free-reliable-apis.md

- **Replanner does not call `fetch_daily_weather`** (`agents/replanner_agent.py`): Replanner returns LLM-patched JSON only; weather metadata is not re-merged. Story Dev Notes already flagged this; acceptable for Story 1.1 scope if product treats “refresh” as re-generation via planner. Revisit if replan flows must refresh live forecasts.

## Deferred from: code review (2026-04-15) — 1-2-itemized-pricing-via-free-apis-no-invented-totals.md

- **Trip rollup + ECB strip duplicated in each day modal** (`ui/index.html`): Opening any day shows trip-level pricing rollup and reference FX again; acceptable but repetitive; consolidate later if needed.

## Deferred from: code review (2026-04-16) — 2-1-persist-generated-itineraries.md

- **`_derive_trip_dates` broad exception** (`services/itinerary_store.py`): Catches all exceptions when deriving trip bounds; fine for POC; add logging if null dates become a support issue.

## Deferred from: code review (2026-04-16) — 2-2-past-itineraries-list.md

- **Sortable past trips:** Only chronological (newest-first) ordering; no column sort or alternate order in UI.
- **List query reads full bundle JSON per row:** Acceptable at POC volume; optimize later with SQLite JSON functions or a stored list title.

## Deferred from: code review (2026-04-16) — 2-3-pdf-download-per-itinerary.md

- **PDF text encoding:** Latin-1–safe output may replace characters for non-Western destination names; upgrading fpdf2 fonts is a follow-up.
- **Sources block vs segment pricing:** Aggregate “Sources” section emphasizes weather metadata; pricing source lines are mostly inline on segments.

## Deferred from: code review of 3-1-itinerary-detail-add-and-modify.md (2026-04-15)

- **Redundant `GET` before `UPDATE` on saved bundle** (`app.py` `put_saved_itinerary`): Existence is checked with `get_saved_itinerary` before `update_saved_itinerary_bundle`; acceptable for POC volume; consolidate or rely on a single query if hot path.

## Deferred from: code review of 3-2-preference-snapshot-for-replanning-and-edits.md (2026-04-15)

- **`persona_snapshot` JSON not an object** (`get_saved_itinerary` / `_handle_conversation_message`): If stored JSON parses to a list or other non-dict, merge treats snapshot as `{}` instead of failing loudly; only matters for hand-edited or corrupt DB rows.
- **Per-message SQLite load** when `saved_itinerary_id` is sent: One read per chat turn to load `persona_snapshot`; fine at POC scale; cache in session if traffic grows.
