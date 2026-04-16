# Story 1.1: Weather via Free Reliable APIs

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As a traveler,
I want weather for each day and major stop **fetched from real services**,
so that what I see matches reality—not a static placeholder.

## Acceptance Criteria

1. **Given** an itinerary with dates and geocodable locations,
2. **When** weather is shown (after generation or on refresh),
3. **Then** values come from **HTTP calls to at least one free, reliable weather API** (documented in the project), using coordinates and trip dates—not hardcoded seasonal defaults,
4. **And** the UI shows **source attribution** and when data was fetched or which forecast window applies,
5. **And** if the API fails or a location cannot be resolved, the user sees a **clear unavailable state**—not fabricated conditions,
6. **And** optional short-lived **caching** is allowed for performance, with rules documented (TTL, invalidation)—cache is not a substitute for static fake data.

## Tasks / Subtasks

- [x] **Document provider** (AC: 3, 6)
  - [x] Add a short integration note (e.g. `docs/weather-integration.md` or a section in existing project docs under `docs/`) naming the API(s), base URL(s), terms link, and that data is live HTTP—not static tables.
- [x] **Align weather fetches with trip timeline** (AC: 3)
  - [x] Extend `services/weather_service.py` (or a dedicated module) to request forecast data for the **correct calendar day per itinerary day** and coordinates, not only undated “current” conditions—unless product explicitly anchors to “today” for missing dates (document the rule).
  - [x] Define how **trip dates** are derived: e.g. optional `trip_start_date` on persona/state, or default window from generation date + `trip_duration` from `core/preference_schema.normalize_persona` / `parse_trip_duration_days`. **Do not** invent seasonal climate strings in code as a substitute for API output.
- [x] **Structured metadata on segments or days** (AC: 3–5)
  - [x] Persist on the bundle: `weather_source` (string id), `weather_fetched_at` (ISO-8601), and either `forecast_date` or validity text for the forecast window; keep raw display fields (`condition`, temperature, etc.) traceable to API fields.
  - [x] On failure or missing lat/lon: set explicit **`unavailable` / `weather_error`** semantics in the JSON the UI can branch on—avoid ambiguous `"unknown"` that reads like a guess.
- [x] **Timeouts, retries, user-safe errors** (AC: 5)
  - [x] Use bounded `requests` timeouts and limited retries; log server-side without leaking internals to the client; never fall back to fabricated numeric or narrative “typical weather.”
- [x] **Optional cache** (AC: 6)
  - [x] If implemented: in-process TTL cache keyed by `(lat, lon, date)` with documented TTL (e.g. 15–30 minutes) and note that invalidation is time-based only for this story scope.
- [x] **Planner integration** (AC: 3)
  - [x] Update `agents/planner_agent.py` post-processing to call the new weather API shape for each segment with coordinates; handle segments **without** coordinates (geocode destination or show unavailable—do not silently reuse another stop’s weather as “truth” without documenting it).
- [x] **UI: attribution + fetch/window + unavailable** (AC: 4, 5)
  - [x] Update `ui/index.html` day-detail rendering so each segment (or day summary) shows temperature/condition **from the bundle**, plus **source name** and **fetched time or forecast day**; show a clear **“Weather unavailable”** (or similar) when metadata indicates failure/missing coords.
- [x] **Tests**
  - [x] Unit tests for weather service mapping and failure paths (mock HTTP); optional test that planner attaches metadata when coords exist.

## Dev Notes

### Epic and product context

- **Epic 1** delivers integration-backed enrichment; **no static weather** as source of truth. See [_bmad-output/planning-artifacts/epics.md](../../planning-artifacts/epics.md) — Overview integration principles and Story 1.1 acceptance criteria.
- **Cross-story:** Story 1.2 covers pricing; do not scope pricing here.

### Current implementation (brownfield)

| Area | Location | Gap vs story |
|------|----------|----------------|
| HTTP weather | `services/weather_service.py` | Uses Open-Meteo **current** only; no trip-day alignment, no attribution/fetch time in return value, generic `unknown`/`N/A` on error. |
| Attachment | `agents/planner_agent.py` (lines 86–93) | Sets `segment["weather"]` and `segment["temp"]` only when `lat`/`lon` present; no metadata. |
| Schema | `core/itinerary_schema.py` | Normalizes segments; does not yet define weather field contract—extend carefully for backward compatibility. |
| UI | `ui/index.html` `openDayModal` | **Does not render** `weather` / `temp` at all—users never see API-backed values. |
| Reactive | `agents/replanner_agent.py`, `runtime/engine.py` | Replanner does not re-fetch weather; “on refresh” may mean **new generation** or explicit refresh—clarify minimal scope: at least **initial generation** path must satisfy AC; document if full-trip refresh is out of scope for this story. |

### Technical requirements

- **Stack:** Python 3, FastAPI (`app.py`), `requests` (see `requirements.txt`). No new dependency required for Open-Meteo if continuing with GET + JSON.
- **Provider candidate:** **Open-Meteo** (`https://api.open-meteo.com/v1/forecast`) — free for non-commercial use, no API key for default endpoint; document attribution per [Open-Meteo license/terms](https://open-meteo.com/en/license). If you add a second provider for redundancy, document both and keep one code path authoritative per request to avoid mixed semantics.
- **API shape (illustrative):** Daily forecast uses `daily=...` with `start_date` / `end_date` (or `forecast_days`) per [Open-Meteo forecast API](https://open-meteo.com/en/docs). Map API fields explicitly in code; do not let the LLM invent weather text for display.
- **Coordinates:** Segment `lat`/`lon` types may be numbers or strings from LLM normalization—coerce safely before HTTP calls.

### Architecture compliance

- Keep weather **out of** LLM prompts as factual claims: the model plans activities; **numbers and conditions** come from `weather_service` (or successor module).
- Prefer a single service module for HTTP + mapping so `PlannerAgent` stays thin.
- Future PDF/history (Epic 2) will need persisted snapshots—design weather blobs as **serializable metadata** (source, fetched_at, forecast_date) so later stories can store them without refactor.

### Library and configuration

- Reuse `requests` with explicit `timeout=` (e.g. 10s).
- Optional: `WEATHER_HTTP_TIMEOUT`, `WEATHER_CACHE_TTL_SECONDS` in `.env` via existing `pydantic-settings` patterns if the project already uses env for services (check `services/` and config); otherwise document constants at top of `weather_service.py`.

### File structure (expected touchpoints)

- `services/weather_service.py` — core changes or split `weather_client.py` + thin `weather_service.py`.
- `agents/planner_agent.py` — pass trip date context into weather calls; attach structured fields.
- `core/itinerary_schema.py` — optional: document allowed optional keys on segments; avoid breaking `validate_itinerary_bundle`.
- `ui/index.html` — display weather + attribution + unavailable.
- `docs/` — provider documentation (new or appended file).

### Testing requirements

- Mock `requests.get` (or inject a session) for success, HTTP error, timeout, and malformed JSON.
- If adding pure functions for date→API day index, test edge cases (timezone: prefer **date-only** semantics in destination-local or UTC consistently and document).

### Previous story intelligence

- *Not applicable* — this is the first story in Epic 1; no prior story file in `implementation-artifacts` for epic 1.

### Git intelligence

- Workspace is not a git repository in this environment; rely on file-level notes above.

### Latest technical information

- Open-Meteo Forecast API remains keyless on the public endpoint; verify HTTPS only; respect fair-use—cache helps.
- Deprecations: check Open-Meteo changelog if upgrading parameters; `current` vs `daily` parameter sets differ—use **daily** for per-trip-day alignment.

### Project context reference

- No `project-context.md` found in repo; this story file is the primary handoff document.

## Dev Agent Record

### Agent Model Used

Composer (Cursor agent)

### Debug Log References

### Completion Notes List

- Implemented Open-Meteo **daily** forecast per segment with `trip_anchor_date()` (`trip_start_date` optional else today); metadata on segments (`weather_availability`, `weather_source`, `weather_fetched_at`, `forecast_date`, `forecast_window_note`).
- In-process TTL cache (15 min default), HTTP timeout and retries; docs in `docs/weather-integration.md`.
- UI day modal shows attribution, fetch time, forecast window note, and explicit unavailable copy by `weather_error`.
- Added `pytest` and tests under `tests/` (weather service + planner merge).

### File List

- `docs/weather-integration.md` (new)
- `services/weather_service.py` (modified)
- `agents/planner_agent.py` (modified)
- `core/preference_schema.py` (modified)
- `ui/index.html` (modified)
- `requirements.txt` (modified — pytest)
- `tests/__init__.py` (new)
- `tests/test_weather_service.py` (new)
- `tests/test_planner_weather.py` (new)

## Change Log

- 2026-04-15: Story 1.1 implemented — Open-Meteo daily forecasts, trip date anchor, segment metadata, UI attribution/unavailable states, unit tests.
- 2026-04-15: Code review patches — parse-error path for malformed daily JSON fields; log invalid `trip_start_date`; remove unused retry variable; document planner vs replanner weather; new unit test for malformed daily fields.

### Review Findings

- [x] [Review][Patch] Harden success-path parsing in `fetch_daily_weather` — If Open-Meteo returns HTTP 200 with malformed numeric arrays, `float(tmax)` / `float(tmin)` can raise and abort planner execution; wrap mapping in try/except and return `parse_error` like other bad payloads. [`services/weather_service.py` ~167–197]
- [x] [Review][Patch] Log invalid `trip_start_date` — `trip_anchor_date` silently falls back to today on `ValueError`; add a server-side warning so mis-typed persona dates are visible during debugging. [`core/preference_schema.py` ~45–57]
- [x] [Review][Patch] Clean up retry-loop variable — `last_err` in the Open-Meteo retry loop is assigned but unused; remove it or include it in the final log line. [`services/weather_service.py` ~137–141]
- [x] [Review][Patch] Document planner vs replanner weather scope — `docs/weather-integration.md` should state explicitly that live weather is attached in `PlannerAgent` after generation, and that `ReplannerAgent` does not re-merge weather (aligns AC2 “on refresh” with the story’s documented minimal scope unless replanner is extended later). [`docs/weather-integration.md`]
- [x] [Review][Defer] Replanner does not call `fetch_daily_weather` — [`agents/replanner_agent.py`] — deferred, pre-existing gap noted in story Dev Notes; out of current task checklist; consider a follow-up story to re-attach weather after replan.

---

**Completion status:** done — Review patch items applied (2026-04-15).
