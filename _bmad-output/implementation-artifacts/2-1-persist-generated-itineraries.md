# Story 2.1: Persist Generated Itineraries

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As a traveler,
I want each completed generation saved automatically,
so that I can return to it later without losing work.

## Acceptance Criteria

1. **Given** a successful itinerary generation,
2. **When** the system completes the run,
3. **Then** the itinerary bundle, destination, dates, and snapshot of user preferences used are stored durably,
4. **And** each saved record has a stable identifier,
5. **And** stored enrichment (weather snapshots, API-backed prices) may be cached metadata with **timestamps and source ids**—not static placeholders passed off as live.

## Tasks / Subtasks

- [x] **Persistence strategy** (AC: 3–5)
  - [x] Add durable storage (recommended: **SQLite** single file under a configurable path, e.g. `DATA_DIR` / `TRAVEL_AI_DB` env defaulting to project-local `data/` — avoids new infra). Document in `docs/` or story Dev Notes why SQLite fits POC/single-instance deploy.
  - [x] Define a **saved itinerary** record: stable **`id`** (UUID string), **`created_at`** (UTC ISO-8601), **`destination`** (string), **`persona_snapshot`** (JSON — normalized persona used at generation), **`itinerary_bundle`** (full v2 bundle JSON including Epic 1 enrichment: `weather_*`, `pricing`, `pricing_reference_fx`, `pricing_rollups` as produced by the planner/engine).
  - [x] Optionally derive and store **`trip_date_start`** / **`trip_date_end`** or duration hint for future Epic 2 list sorting — document derivation from `persona.trip_start_date`, `trip_duration`, and/or bundle days (even if approximate).
- [x] **Repository layer** (AC: 3–4)
  - [x] Implement `services/` (or `persistence/`) module with **insert** API: `save_generated_itinerary(persona, bundle) -> str` returning **saved id**. Use parameterized queries / JSON serialization; no SQL string concatenation with user content.
  - [x] **Idempotency:** Persist **once per successful generation** — hook only on the success path where `itinerary_has_content` is true (same as API “generated” response). Do **not** persist empty or failed planner runs.
- [x] **Integration point** (AC: 1–2)
  - [x] Call save from the **single success path** after a full bundle exists — e.g. [`app.py`](../../app.py) `_handle_conversation_message` when `status == "generated"` and itinerary is non-empty, **or** inside [`runtime/orchestrator.py`](../../runtime/orchestrator.py) `generate_from_structured_persona` immediately before/after `update_state` on success. Prefer **one** place to avoid double saves.
  - [x] Include **`saved_itinerary_id`** (or similar) in the JSON response to `/conversation/message` when generation succeeds so clients and future Story 2.2 can reference the record (optional but recommended).
- [x] **Epic 1 compliance on persist** (AC: 5)
  - [x] Store the bundle **as returned by enrichment** — do not strip `weather_fetched_at`, `weather_source`, `pricing.fetched_at`, `pricing_reference_fx`, etc. Persisted data is a **snapshot**; UI/export (Epic 2.3) will treat it as historical — not fake live data.
- [x] **Tests** (AC: 3–4)
  - [x] Unit/integration tests: save after mock success produces retrievable row with expected JSON fields and UUID; verify failed generation does not insert.

## Dev Notes

### Epic and product context

- Epic 2 overview and integration principles: [epics.md](../planning-artifacts/epics.md) — Epic 2 + Story 2.1.
- **Scope boundary:** This story is **persist on success** only. **Story 2.2** adds browsing UI/API; **2.3** adds PDF. Do not build the full “My trips” list UI here unless needed minimally to verify persistence (optional dev-only endpoint `GET /debug/saved` — only if it speeds validation; prefer tests + optional `GET /saved/{id}` for smoke).

### Brownfield — current behavior

| Area | Location | Gap |
|------|----------|-----|
| State | [`state/store.py`](../../state/store.py) | In-memory only; **lost on process restart**. |
| Success path | [`app.py`](../../app.py) `_handle_conversation_message` + [`runtime/orchestrator.py`](../../runtime/orchestrator.py) `generate_from_structured_persona` | No durable write. |
| Itinerary shape | [`core/itinerary_schema.py`](../../core/itinerary_schema.py) | v2 bundle already carries weather/pricing metadata from Epic 1. |

### Architecture compliance

- **FastAPI** + existing patterns; new dependencies only if justified (e.g. `sqlite3` stdlib — no extra package required).
- **Secrets:** No user auth in scope for 2.1 unless already present — single-tenant POC is acceptable; document that multi-user would need `user_id` on records later.

### Technical requirements

- **Python 3**, **FastAPI**, **pytest** — see [`requirements.txt`](../../requirements.txt).
- **JSON:** Use `json.dumps` with stable defaults; for SQLite store TEXT or BLOB for large payloads.

### File structure (expected touchpoints)

- New: persistence module + schema/migrations or `CREATE TABLE IF NOT EXISTS` on startup.
- [`app.py`](../../app.py) and/or [`runtime/orchestrator.py`](../../runtime/orchestrator.py) — single hook.
- [`tests/`](../../tests/) — new test module for persistence.

### Previous story intelligence (Epic 1)

- Itinerary segments include **weather** and **pricing** fields from [`services/weather_service.py`](../../services/weather_service.py), [`services/pricing_service.py`](../../services/pricing_service.py) — persist verbatim in `itinerary_bundle`.

### Testing standards

- Use **tmp_path** or in-memory SQLite for tests; clean up files.

### Project context reference

- No `project-context.md` in repo; this file + code paths above are authoritative.

## Dev Agent Record

### Agent Model Used

Composer (Cursor agent)

### Debug Log References

### Completion Notes List

- Added `services/itinerary_store.py` (SQLite, UUID ids, trip date derivation, `get_saved_itinerary`).
- `app.py`: startup `init_store()`, save on successful generation only, response field `saved_itinerary_id`, `GET /saved/{saved_id}`.
- `docs/persistence.md`; `data/` in `.gitignore`.
- Tests: `tests/test_itinerary_store.py` (roundtrip + enrichment preservation).

### File List

- `services/itinerary_store.py` (new)
- `app.py` (modified)
- `docs/persistence.md` (new)
- `.gitignore` (modified)
- `tests/test_itinerary_store.py` (new)
- `tests/test_app_persistence.py` (new — review patch)

## Change Log

- 2026-04-16: Story 2.1 implemented — SQLite persistence, save hook, saved id in API, GET retrieval, tests.
- 2026-04-16: Code review patches — `get_saved_itinerary` handles corrupt JSON; `test_app_persistence.py` + `test_get_saved_corrupt_json_returns_none`.

### Review Findings

- [x] [Review][Patch] Harden `get_saved_itinerary` JSON parsing — `json.loads` on `persona_snapshot` / `itinerary_bundle` can raise if the DB row is corrupted or manually edited; catch `json.JSONDecodeError`, log, return `None` (or map to 404 via API) instead of an unhandled 500. [`services/itinerary_store.py` ~119–126]
- [x] [Review][Patch] Add automated coverage for “failed generation does not insert” — Story tasks require verifying no durable row on planner/OSM failure; store tests only cover the happy path. Add a test that mocks `engine.generate_from_structured_persona` (or the orchestrator result) to return `success: False` and asserts `save_generated_itinerary` is not called / no new row (e.g. `unittest.mock` on `app.save_generated_itinerary` or DB file row count). [`tests/` + `app.py` path]
- [x] [Review][Defer] `_derive_trip_dates` uses broad `except Exception` — [`services/itinerary_store.py` ~64–72] — deferred; acceptable for POC; optional debug logging if trip dates often null.

---

**Completion status:** done — Review patches applied (2026-04-16).
