# Story 3.1: Itinerary Detail Add and Modify

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As a traveler,
I want to add or change items when viewing an itinerary’s detail,
so that the plan matches my needs without starting over.

## Acceptance Criteria

1. **Given** an opened itinerary (new or from history),
2. **When** I edit activities, notes, times, or order,
3. **Then** changes **persist** for that itinerary (see persistence rules below),
4. **And** validation prevents **obviously invalid** states with **clear errors** (e.g. empty required fields, broken v2 shape, egregious ordering issues you define in code),
5. **And** new or edited lines that need **weather** or **price** follow **Epic 1 rules**: only **API-backed** or **explicit unavailable** — **no LLM-invented money**; new segments use the same `pricing` / `weather_*` field patterns as [`core/itinerary_schema.py`](../../core/itinerary_schema.py) and existing enrichment paths where applicable.

## Tasks / Subtasks

- [x] **Data model & validation** (AC: 4–5)
  - [x] Document **v2 segment minimum fields** for edits: `time_label`, `title`, `place_name` (non-empty strings), `description` optional; preserve `lat`/`lon` when present for future weather; new segments get `pricing` from [`default_segment_pricing()`](../../core/itinerary_schema.py) (or equivalent) until enrichment runs.
  - [x] Add server-side validation helper(s), e.g. in [`core/itinerary_schema.py`](../../core/itinerary_schema.py) or `services/itinerary_edit.py`: validate v2 bundle after edit; optional **lightweight** overlap / ordering checks (POC: e.g. at least one segment per day, day indices consistent, `itinerary_version == 2`). Return structured errors for API responses.
  - [x] After any bundle mutation, call [`compute_pricing_rollups`](../../core/itinerary_schema.py) (and [`ensure_segment_pricing_defaults`](../../core/itinerary_schema.py) if required by project rules) so rollups stay consistent with Epic 1.

- [x] **Persistence — two contexts** (AC: 1–3)
  - [x] **A. In-memory session itinerary** (just generated or refreshed from `/state`): expose an API to replace/update the current v2 bundle in [`state/store.py`](../../state/store.py) (e.g. `PUT /itinerary` or `PATCH /conversation/itinerary`) so the engine’s view matches the UI. Reject invalid bundles with **400** + validation detail.
  - [x] **B. Saved SQLite itineraries** (user opened a trip from **My trips** or has a `saved_itinerary_id`): extend [`services/itinerary_store.py`](../../services/itinerary_store.py) with **`update_saved_itinerary_bundle(saved_id, bundle: dict) -> None`** (or update full row) using parameterized `UPDATE`; load existing row, merge/replace `itinerary_bundle` JSON, commit. Expose e.g. **`PUT /saved/{saved_id}`** with body `{ "itinerary_bundle": { ... } }` (and optionally validate id matches client). **404** if missing.
  - [x] **Consistency:** When both apply (session has a generated trip **and** `lastSavedItinerary_id`), define one rule in code comments: e.g. prefer updating **SQLite** when editing a loaded saved trip **only**, and session otherwise — avoid double writes. Document in [`docs/persistence.md`](../../docs/persistence.md).

- [x] **Enrichment / Epic 1 alignment** (AC: 5)
  - [x] For **new** segments without coordinates: keep `weather_availability` **unavailable** (or omit) until lat/lon exist; do **not** invent forecasts.
  - [x] **Optional POC:** if a segment gains **lat/lon**, call existing [`services/weather_service.py`](../../services/weather_service.py) (or the same path the planner uses) **once** on save to fill snapshot fields — only if story scope allows; otherwise document “enrichment on save” as follow-up. Prefer reusing existing enrichment helpers over duplicating HTTP logic in `app.py`.
  - [x] Pricing: never set `availability: ok` with amounts without a trusted `source_id` (per existing guards in [`core/itinerary_schema.py`](../../core/itinerary_schema.py)).

- [x] **UI — day detail modal** (AC: 1–2)
  - [x] Update [`ui/index.html`](../../ui/index.html): the **day detail** modal (built in `openDayDetail` / segment rendering) becomes **editable** for segment fields (text inputs for time, title, place, description; optional notes fields aligned with schema: `meal_suggestion`, `transport_note`, `local_tip`).
  - [x] **Order:** implement **move up / move down** within the day for segments (or equivalent) to satisfy “order” in AC; keep implementation simple (no full drag-drop required for POC).
  - [x] **Add / remove segment:** buttons to add a blank segment (with defaults) and remove a segment (with confirm if needed); **cannot** remove last segment of a day if validation requires ≥1 — return clear error.
  - [x] **Save:** primary action **Save changes** that serializes the edited bundle from the modal, then calls the appropriate API (session vs saved id based on `viewingSavedSnapshot` / `lastSavedItineraryId`). Show loading and **validation errors** from server in the modal.
  - [x] After successful save: refresh table + modal state (`renderItinerary`); if saved trip, optionally refresh list.

- [x] **Tests** (AC: 3–5)
  - [x] Unit tests: validation rejects invalid bundles; `update_saved_itinerary_bundle` roundtrip with tmp DB.
  - [x] `TestClient`: `PUT` session itinerary and `PUT` saved itinerary return 200 with persisted data; 400 on bad payload.

- [x] **Documentation**
  - [x] Extend [`docs/persistence.md`](../../docs/persistence.md) with edit endpoints and snapshot semantics after edits.

## Dev Notes

### Epic and product context

- [Epic 3 — epics.md](../planning-artifacts/epics.md): editing with **preference memory**; **Story 3.2** covers **preference snapshot for replanning** — this story (**3.1**) focuses on **structural CRUD** on the itinerary bundle; do **not** require full replanner/LLM replan flows unless explicitly scoped.
- **Depends on:** Epic 2 persistence ([`services/itinerary_store.py`](../../services/itinerary_store.py)), v2 bundle shape ([`core/itinerary_schema.py`](../../core/itinerary_schema.py)), Epic 1 enrichment rules ([`docs/weather-integration.md`](../../docs/weather-integration.md), [`docs/pricing-integration.md`](../../docs/pricing-integration.md) if present).

### Brownfield — current behavior

| Area | Location | Gap |
|------|----------|-----|
| Itinerary | [`state/store.py`](../../state/store.py) | `itinerary` holds v2 bundle; **no** public edit API yet. |
| Day UI | [`ui/index.html`](../../ui/index.html) | Day modal is **read-only** HTML; `itineraryBundle` is JS state only. |
| Saved trips | [`GET /saved/{id}`](../../app.py), client hydrate | Opens snapshot; **no** `UPDATE` on `saved_itineraries` yet. |
| Validation | [`validate_itinerary_bundle`](../../core/itinerary_schema.py) | Strict (every segment needs `place_name`, `time_label`); may need **edit-specific** expectations (e.g. allow empty description). |

### Architecture compliance

- **SQLite** for saved updates; parameterized SQL only.
- **Single-tenant POC:** no auth; any saved id can be updated (same as list visibility).
- **FastAPI** + existing patterns; prefer thin routes and logic in services/schema.

### Scope boundary

- **In scope:** Edit/add/reorder segments within days; persist to session and/or SQLite; validation; Epic 1–compliant defaults for new pricing/weather fields.
- **Out of scope for 3.1:** Full **AI replan** from natural language (**3.2**); multi-user locking; **optimistic UI** across tabs; drag-drop across days.

### Previous story intelligence (Epic 2)

- **Client hydrate** + `viewingSavedSnapshot` skips `/state` polling — after **editing a saved trip**, you may need to **keep** `viewingSavedSnapshot` true **or** merge server state carefully so polling does not overwrite edits (see [`docs/persistence.md`](../../docs/persistence.md)).
- **`lastSavedItinerary_id`** tracks the row for PDF — reuse for **PUT /saved/{id}** when editing that trip.

### File structure (expected touchpoints)

- [`core/itinerary_schema.py`](../../core/itinerary_schema.py) — validation helpers; rollups after edit.
- [`services/itinerary_store.py`](../../services/itinerary_store.py) — `UPDATE` saved bundle.
- [`app.py`](../../app.py) — new route(s).
- [`ui/index.html`](../../ui/index.html) — editable modal, save flows.
- [`tests/test_itinerary_edit.py`](../../tests/test_itinerary_edit.py) (new).
- [`docs/persistence.md`](../../docs/persistence.md).

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

- Added `validate_edited_itinerary_bundle`, `finalize_edited_bundle`, `ensure_segment_weather_consistency`, `normalize_day_indices` in `core/itinerary_schema.py`; `update_saved_itinerary_bundle` in `itinerary_store.py`.
- **`PUT /itinerary`** and **`PUT /saved/{saved_id}`** in `app.py` with 400 `{detail.errors}` on validation failure.
- **`ui/index.html`:** day modal is an edit form (segment fields, move up/down, add/remove, save); routes to `PUT /saved/{id}` when `viewingSavedSnapshot` else `PUT /itinerary`.
- Weather-on-save for new lat/lon deferred; documented in `docs/persistence.md`.

### File List

- `core/itinerary_schema.py`
- `services/itinerary_store.py`
- `app.py`
- `ui/index.html`
- `tests/test_itinerary_edit.py`
- `docs/persistence.md`
- `_bmad-output/implementation-artifacts/3-1-itinerary-detail-add-and-modify.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

### Change Log

- Story 3.1: editable day modal, dual PUT APIs, validation/finalize pipeline, SQLite update, tests, docs (2026-04-16).
- 2026-04-15: Code review — clear stale API weather fields when coordinates are absent; sprint status synced.

### Review Findings

- [x] [Review][Patch] **Stale weather snapshot after removing coordinates** — [`ensure_segment_weather_consistency`](../../core/itinerary_schema.py) forced `weather_availability` off `ok` when `lat`/`lon` were missing but left `condition`, `temp`, `weather_source`, etc., which could misrepresent Epic 1 honesty after an edit. **Fixed:** `_clear_segment_api_weather_fields` runs for segments without coordinates; [`tests/test_itinerary_edit.py`](../../tests/test_itinerary_edit.py) covers the regression.
- [x] [Review][Defer] **Extra read on `PUT /saved/{id}`** — [`put_saved_itinerary`](../../app.py) calls `get_saved_itinerary` for 404, then `update_saved_itinerary_bundle` may re-check the row; minor redundancy and a narrow TOCTOU window. Acceptable for single-tenant POC.
- [x] [Review][Dismiss] **Story text vs code** — Tasks reference `openDayDetail`; implementation uses `openDayModal` — naming only; behavior matches.

---

**Completion status:** done — Code review complete (2026-04-15).
