# Story 3.2: Preference Snapshot for Replanning and Edits

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As a traveler,
I want the system to remember the preferences that built this itinerary,
so that AI-assisted edits and replans stay consistent with how the trip was originally scoped.

## Acceptance Criteria

1. **Given** an itinerary with an associated preference snapshot (structured persona at generation time — stored as `persona_snapshot` for saved rows, and held in session `persona` / `partial_persona` after generation),
2. **When** I request changes, regeneration, or replanning from the chat while focused on **this** trip,
3. **Then** the planner / preference pipeline uses **that snapshot as the primary base** and merges it sensibly with explicit new instructions from my messages,
4. **And** the UI surfaces which preferences are scoped to **this trip** (saved snapshot) versus a **fresh session** (no trip loaded),
5. **And** any **refetch** of weather or prices after replanning uses **live free APIs** again (same enrichment path as initial generation — [`PlannerAgent`](../../agents/planner_agent.py) + [`services/weather_service.py`](../../services/weather_service.py) / [`services/pricing_service.py`](../../services/pricing_service.py)), not static data,
6. **And** if the LLM is involved in wording or structuring the plan, **factual claims** about weather and cost remain **API-grounded** or **explicitly absent**, per Epic 1 and existing [`ReplannerAgent`](../../agents/replanner_agent.py) rules.

## Tasks / Subtasks

- [x] **Define merge semantics** (AC: 3)
  - [x] Add a small, testable helper (e.g. in [`core/preference_schema.py`](../../core/preference_schema.py) or `services/preference_context.py`): given a **trip snapshot** `dict` (normalized like post-[`normalize_persona`](../../core/preference_schema.py)) and the **current partial** from [`process_turn`](../../services/preference_llm.py), produce the **effective base** for the next turn. Document precedence: **snapshot fields win** as defaults; user messages may override specific keys once extracted by the preference LLM; avoid silently dropping snapshot keys when the session `partial_persona` is empty or stale.
  - [x] Document behavior when **optional** fields differ (e.g. user says “more relaxed pace”) — merge after each `process_turn` result, not only at generation time.

- [x] **Wire server-side trip context** (AC: 2–3)
  - [x] Extend [`POST /conversation/message`](../../app.py) (and [`PlanInput`](../../app.py) / [`ConversationMessage`](../../app.py) body) to accept an optional **`saved_itinerary_id`** (UUID string). When present and valid:
    - [x] Load the row with [`get_saved_itinerary`](../../services/itinerary_store.py); **404** if missing.
    - [x] Before calling `process_turn`, seed or merge state so the effective partial persona reflects **`persona_snapshot`** from that row (normalized). Do **not** rely on stale in-memory `get_state().partial_persona` alone when this id is supplied.
  - [x] On successful **new generation** (`status: "generated"`) that was initiated with `saved_itinerary_id`, **update the existing SQLite row** instead of only inserting a new one: persist the new `itinerary_bundle` **and** updated `persona_snapshot` (post-merge persona used for generation) via a new store API, e.g. **`update_saved_itinerary_after_replan(saved_id, persona, bundle)`** in [`services/itinerary_store.py`](../../services/itinerary_store.py) (parameterized `UPDATE` of `persona_snapshot`, `itinerary_bundle`, and derived `destination` / `trip_date_*` if needed — mirror fields from [`save_generated_itinerary`](../../services/itinerary_store.py)).
  - [x] If `saved_itinerary_id` is **omitted**, keep current behavior: [`save_generated_itinerary`](../../services/itinerary_store.py) inserts a **new** row (new UUID) as today.

- [x] **Session vs saved consistency** (AC: 2–4)
  - [x] After handling a replan tied to `saved_itinerary_id`, call [`update_state`](../../state/store.py) so `persona`, `partial_persona`, and `itinerary` match what was generated (same as successful flow in [`_handle_conversation_message`](../../app.py)), so [`GET /state`](../../app.py) and polling stay coherent.
  - [x] Document in [`docs/persistence.md`](../../docs/persistence.md): optional body field, merge rule, and **when a new row is created vs row updated**.

- [x] **UI: trip-scoped replan** (AC: 2, 4)
  - [x] Update [`ui/index.html`](../../ui/index.html) `sendMessage`: when `viewingSavedSnapshot && lastSavedItineraryId`, **include `saved_itinerary_id`** in the JSON body to `POST /conversation/message`. **Do not** clear `viewingSavedSnapshot` before the request (today `sendMessage` sets `viewingSavedSnapshot = false` immediately — that breaks trip context and must change for this story).
  - [x] After response handling: if generated with a saved id, keep `lastSavedItineraryId` and saved banner; refresh **My trips** list so titles/dates update if the store updates the row.
  - [x] **Surface preference source** in the “Captured preferences” area: e.g. a short label **“This trip (saved)”** when `viewingSavedSnapshot` or when the last successful message used a saved id; **“New session”** after **New trip** / reset. Reuse or extend [`renderChips`](../../ui/index.html) without duplicating chip HTML in multiple places if possible.

- [x] **Enrichment & Epic 1** (AC: 5–6)
  - [x] Confirm replanned itineraries go through the same **`PlannerAgent.execute`** pipeline (weather + pricing enrichment as in [`agents/planner_agent.py`](../../agents/planner_agent.py)) — no shortcut that skips APIs. If [`ReplannerAgent`](../../agents/replanner_agent.py) is used for smaller edits in future, [`engine.trigger_event`](../../runtime/engine.py) paths must still receive **persona** from the trip snapshot when invoked from a saved-trip context (out of scope unless you unify; this story focuses on **chat-driven regeneration** with snapshot).

- [x] **Tests** (AC: 3, 5)
  - [x] `TestClient`: `POST /conversation/message` with `saved_itinerary_id` loads snapshot; mock or stub LLM/preference layer if needed **or** integration test with heuristic path where possible.
  - [x] Store test: after `update_saved_itinerary_after_replan`, `get_saved_itinerary` returns updated `persona_snapshot` and bundle (use `tmp_path` / [`set_database_path_for_tests`](../../services/itinerary_store.py)).

- [x] **Documentation**
  - [x] Extend [`docs/persistence.md`](../../docs/persistence.md) with the replan contract and UI behavior.

## Dev Notes

### Epic and product context

- [Epic 3 — epics.md](../planning-artifacts/epics.md): **preference memory** for editing; Story 3.1 delivered **structural CRUD** on the bundle ([`PUT /itinerary`](../../app.py), [`PUT /saved/{id}`](../../app.py)). This story (**3.2**) delivers **semantic consistency**: replanning and AI-assisted changes respect the **frozen persona snapshot** for that trip.
- **Depends on:** Story 3.1 (edit APIs), Epic 2 (`persona_snapshot` column), [`core/preference_schema.py`](../../core/preference_schema.py), [`services/preference_llm.py`](../../services/preference_llm.py), [`runtime/orchestrator.py`](../../runtime/orchestrator.py) `generate_from_structured_persona`.

### Brownfield — current behavior (critical gaps)

| Area | Location | Gap |
|------|----------|-----|
| Saved trip open | [`ui/index.html`](../../ui/index.html) `openSavedItinerary` | Loads `persona_snapshot` into chips **client-only**; **server session** is **not** updated with that snapshot. |
| Send message | [`ui/index.html`](../../ui/index.html) `sendMessage` | Sets `viewingSavedSnapshot = false` **before** `POST /conversation/message`, so the user **loses** “saved trip” context on send; body has **no** saved id. |
| Conversation handler | [`app.py`](../../app.py) `_handle_conversation_message` | Uses `get_state().partial_persona` only — **not** `persona_snapshot` from the opened trip. |
| Persistence on regen | [`app.py`](../../app.py) | Always **`save_generated_itinerary`** → **new** row; does not **update** the row the user was editing from. |
| SQLite | [`services/itinerary_store.py`](../../services/itinerary_store.py) | [`update_saved_itinerary_bundle`](../../services/itinerary_store.py) updates bundle only; **no** persona snapshot update API yet. |

### Architecture compliance

- **FastAPI** + Pydantic body models; extend existing models with optional fields (default `None`).
- **SQLite**: parameterized `UPDATE`; no new tables required — extend `UPDATE` to include `persona_snapshot` and metadata columns as needed.
- **Single-tenant POC**: no auth; `saved_itinerary_id` is sufficient to identify the row (same trust model as [`PUT /saved/{id}`](../../app.py)).

### Scope boundary

- **In scope:** Chat-driven **regeneration** with **trip snapshot** as base; persisting updated bundle + persona to the **same** saved id when replanning from that trip; UI labels for trip vs session preferences; tests and docs.
- **Out of scope (unless time permits):** Multi-tab locking; conflict resolution if two devices edit the same row; **natural-language-only** replan without going through `process_turn` (still use preference pipeline for consistency); changing [`ReplannerAgent`](../../agents/replanner_agent.py) demo buttons to use snapshot (optional follow-up).

### Previous story intelligence (3.1)

- [`docs/persistence.md`](../../docs/persistence.md) documents **edit routing**: `PUT /itinerary` for session vs `PUT /saved/{id}` for hydrated saved view — **replanned** bundles should follow the **same** rule: if user replanned from a **saved** trip, persist via the **saved row update** path after generation.
- Validation pipeline [`validate_edited_itinerary_bundle`](../../core/itinerary_schema.py) / [`finalize_edited_bundle`](../../core/itinerary_schema.py) applies to **manual** edits; **planner output** already validates in [`Orchestrator.generate_from_structured_persona`](../../runtime/orchestrator.py). After replan, ensure stored bundle is valid v2 (existing planner path).

### File structure (expected touchpoints)

- [`app.py`](../../app.py) — extend conversation body; load snapshot; branch save vs update; error handling.
- [`services/itinerary_store.py`](../../services/itinerary_store.py) — `update_saved_itinerary_after_replan` (or equivalent).
- [`core/preference_schema.py`](../../core/preference_schema.py) (and/or new small module) — merge helper.
- [`services/preference_llm.py`](../../services/preference_llm.py) — only if merge must happen inside `process_turn` (prefer keeping merge in `app.py` for clarity unless duplication forces otherwise).
- [`ui/index.html`](../../ui/index.html) — `sendMessage`, chips label, optional banner text.
- [`docs/persistence.md`](../../docs/persistence.md).
- New tests under `tests/` (e.g. `test_preference_replan.py`).

### Testing standards

- Follow [`tests/test_itinerary_store.py`](../../tests/test_itinerary_store.py) / [`tests/test_itinerary_edit.py`](../../tests/test_itinerary_edit.py) patterns: `set_database_path_for_tests`, `tmp_path`.

### References

- Epic 3 Story 3.2 — [epics.md](../planning-artifacts/epics.md) (lines 125–138).
- Persistence — [docs/persistence.md](../../docs/persistence.md).
- Preference fields — [core/preference_schema.py](../../core/preference_schema.py) (`REQUIRED_FIELDS`, `normalize_persona`).

### Latest technical notes (stack)

- **FastAPI** `0.115.x`, **Pydantic** v2 (`BaseModel`) — optional fields with `None` default are idiomatic.
- No new third-party dependencies expected for this story.

## Dev Agent Record

### Agent Model Used

Composer (Cursor agent)

### Debug Log References

None.

### Completion Notes List

- Added [`merge_trip_snapshot_with_partial`](../../core/preference_schema.py) and [`update_saved_itinerary_after_replan`](../../services/itinerary_store.py).
- Extended [`_handle_conversation_message`](../../app.py) with optional `saved_itinerary_id`: merge snapshot before `process_turn`, `update_saved_itinerary_after_replan` on success when id present, responses include `preference_scope` and `replan_from_saved`.
- UI: `sendMessage` passes `saved_itinerary_id` when viewing a saved trip; `renderChips` shows “This trip (saved)” vs “New session”; 404 handling for missing id.
- Tests: [`tests/test_preference_replan.py`](../../tests/test_preference_replan.py); full suite 38 passed (includes merge override regression).

### File List

- `core/preference_schema.py`
- `services/itinerary_store.py`
- `app.py`
- `ui/index.html`
- `docs/persistence.md`
- `tests/test_preference_replan.py`
- `_bmad-output/implementation-artifacts/3-2-preference-snapshot-for-replanning-and-edits.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

### Change Log

- Story 3.2: trip preference merge, replan updates same SQLite row, API and UI wiring, docs, tests (2026-04-15).
- 2026-04-15: Code review — `_strip_absent_overrides` in [`merge_trip_snapshot_with_partial`](../../core/preference_schema.py) so blank/null session fields do not erase saved snapshot defaults; test added.

### Review Findings

- [x] [Review][Patch] **Blank or null partial fields could override snapshot** — [`merge_trip_snapshot_with_partial`](../../core/preference_schema.py) used `{**base, **partial}`; a stale `partial_persona` with `destination: ""` or `food_priority: None` could wipe normalized snapshot values before `process_turn`. **Fixed:** `_strip_absent_overrides` removes `None` and blank strings from the override layer; [`test_merge_blank_partial_values_do_not_wipe_snapshot`](../../tests/test_preference_replan.py) locks the behavior.
- [x] [Review][Defer] **Non-dict `persona_snapshot` in DB** — If JSON parsed to a non-object, merge uses `{}` and trip context is lost without 404; only relevant for corrupted rows. Same class as other corrupt-JSON handling.
- [x] [Review][Defer] **SQLite read before merge** — Each `POST /conversation/message` with `saved_itinerary_id` loads the row; acceptable POC cost.

## Project context reference

- No `project-context.md` in repo; this file and linked code paths are authoritative.

---

**Completion status:** done — Code review complete (2026-04-15).
