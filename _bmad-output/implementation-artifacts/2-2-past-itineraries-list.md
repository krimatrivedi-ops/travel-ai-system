# Story 2.2: Past Itineraries List

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As a traveler,
I want a list of my past itineraries,
so that I can reopen any trip quickly.

## Acceptance Criteria

1. **Given** one or more saved itineraries,
2. **When** I open the app or a “My trips” area,
3. **Then** I see a chronological (or sortable) list with **title**, **destination**, and **date range**,
4. **And** I can **select one** to open detail.

## Tasks / Subtasks

- [x] **List API** (AC: 1–3)
  - [x] Extend [`services/itinerary_store.py`](../../services/itinerary_store.py) with **`list_saved_itinerary_summaries()`** returning summary rows for each saved trip **without** loading full bundle JSON into memory for every row if possible — e.g. `SELECT id, created_at, destination, trip_date_start, trip_date_end` ordered by `created_at DESC` (newest first).
  - [x] Add a **display title** for each row: prefer **first day theme** from stored bundle when cheap (e.g. parse `itinerary_bundle` JSON only in list path — acceptable for POC volumes), or derive **`{destination} · {trip_date_start}–{trip_date_end}`** when day title unavailable. Document the rule in code comments.
  - [x] Expose **`GET /saved`** (or `/itineraries/saved`) returning JSON array of summaries: `{ id, title, destination, trip_date_start, trip_date_end, created_at }`.
- [x] **Open / detail behavior** (AC: 4)
  - [x] Reuse or extend **`GET /saved/{id}`** ([`app.py`](../../app.py)) so selecting a trip loads **full** record (persona + bundle). Define one flow: **client** fetches full saved trip and **hydrates** the UI (itinerary panel + optional persona chips) **or** **server** `POST /conversation/load-saved` updates [`state/store.py`](../../state/store.py) — pick **one** approach and document tradeoffs (POC: client-side hydrate avoids mutating server session unexpectedly).
  - [x] Ensure opened detail uses the **persisted bundle** (historical weather/pricing snapshots) — label if needed so users do not assume live API refresh (optional copy: “Saved trip” banner).
- [x] **UI — “My trips”** (AC: 2–4)
  - [x] Update [`ui/index.html`](../../ui/index.html): add a visible **My trips** section (nav link, tab, or collapsible panel) that loads the list on open / on demand (`fetch` to list endpoint).
  - [x] Render a **table or card list** with title, destination, date range; **click** loads detail (same day-modal / itinerary table patterns as current generation flow — reuse `renderItinerary` and day modal where possible).
  - [x] Empty state when no saved trips; loading/error states.
- [x] **Epic 1 / persistence alignment**
  - [x] Do not strip enrichment when displaying saved bundles; treat as **snapshots** (consistent with [Epic 2 in epics.md](../planning-artifacts/epics.md)).
- [x] **Tests** (AC: 1–4)
  - [x] Unit tests: list ordering and shape after inserting multiple saves (tmp DB); optional **TestClient** test for `GET /saved` JSON.

## Dev Notes

### Epic and product context

- [Epics — Story 2.2](../planning-artifacts/epics.md)
- **Depends on:** Story 2.1 — [`services/itinerary_store.py`](../../services/itinerary_store.py), `GET /saved/{id}`.

### Brownfield

| Area | Notes |
|------|-------|
| Store | Table `saved_itineraries` has id, created_at, destination, trip dates, persona + bundle JSON. No list API yet. |
| UI | Single-column planner + itinerary; no past-trips UI. |
| State | In-memory session; loading a saved trip may stay **client-only** for POC. |

### Architecture compliance

- **SQLite** only; parameterized SQL for any new queries.
- **Single-tenant:** No auth in scope; all saved trips visible (same as 2.1).

### Scope boundary

- **Out of scope for 2.2:** PDF export (**2.3**); editing saved trips (**Epic 3**). Read-only open is enough.

### Previous story intelligence (2.1)

- Persistence path: [`docs/persistence.md`](../../docs/persistence.md).
- Full record shape and `get_saved_itinerary` — extend, do not duplicate persistence logic in `app.py` beyond thin route handlers.

### File structure (expected touchpoints)

- [`services/itinerary_store.py`](../../services/itinerary_store.py) — list + title derivation.
- [`app.py`](../../app.py) — `GET /saved` list route.
- [`ui/index.html`](../../ui/index.html) — My trips UI + load handler.
- [`tests/`](../../tests/) — `test_saved_list.py` or extend `test_itinerary_store.py`.

### Testing standards

- Use `tmp_path` / `set_database_path_for_tests` pattern from [`tests/test_itinerary_store.py`](../../tests/test_itinerary_store.py).

### Project context reference

- No `project-context.md`; this file + code paths above are authoritative.

## Dev Agent Record

### Agent Model Used

Composer (Cursor agent)

### Debug Log References

None.

### Completion Notes List

- Implemented `list_saved_itinerary_summaries()` and `_summary_title_from_bundle_json()` in `itinerary_store`; `GET /saved` returns summary rows (newest first). `GET /saved/{id}` unchanged for full hydrate.
- UI: “My trips” table, empty/loading/error states, row click loads saved bundle + persona chips; banner clarifies snapshot. `viewingSavedSnapshot` skips 4s `/state` polling until user sends a message or resets trip; `loadMyTrips()` refreshes after successful generation.
- Documented list/detail endpoints in `docs/persistence.md`. Added `groq` to `requirements.txt` so imports (`llm_service`) resolve in clean installs and tests.

### File List

- `services/itinerary_store.py`
- `app.py`
- `ui/index.html`
- `docs/persistence.md`
- `tests/test_saved_list.py`
- `requirements.txt`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

### Change Log

- Story 2.2 implementation: list API, My trips UI, snapshot banner, polling guard, tests, persistence docs; added missing `groq` dependency (2026-04-15).
- 2026-04-16: Code review patch — documented client-side hydrate vs server session in `docs/persistence.md`.

### Review Findings

- [x] [Review][Patch] Document client-side hydrate choice in persistence docs — Story 2.2 asks to pick **one** flow (client hydrate vs `POST` load-saved) and document **tradeoffs**. [`docs/persistence.md`] lists endpoints but does not explicitly state that opening a trip uses **client-only** `GET /saved/{id}` + UI hydrate (no server `state` mutation), and why (POC: avoids surprising session overwrites).
- [x] [Review][Defer] **Sortable list** — AC allows “chronological (or sortable)”; UI/API provide **newest-first** only; no alternate sorts. Acceptable for POC. [`ui/index.html`, `GET /saved`]
- [x] [Review][Defer] **Full `itinerary_bundle` column read per list row** — `list_saved_itinerary_summaries` selects `itinerary_bundle` for title derivation; story allows POC-scale full parse. Future: `json_extract` / denormalized `list_title` column. [`services/itinerary_store.py`]

---

**Completion status:** done — Review doc patch applied (2026-04-16).
