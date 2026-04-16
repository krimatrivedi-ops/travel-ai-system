# Epic 3 Retrospective — Detail Editing With Preference Snapshot

Status: done

<!-- Retrospective facilitation pack — run as a team session; not a code implementation story. After the session, set epic-3-retrospective to `done` in sprint-status.yaml and capture action items below. -->

## Purpose

Facilitate a **blame-free** post-epic review for **Epic 3: Detail Editing With Preference Snapshot** in **travel-ai-system**: extract lessons, confirm outcomes against [epics.md](../planning-artifacts/epics.md), and capture follow-ups for **product backlog / next epic** work.

**Psychological safety:** Focus on systems, processes, and learning — not individual fault.

---

## Epic 3 recap (source of truth)

| Item | Intent (from epics) |
|------|------------------------|
| Theme | **Edit** itineraries while respecting **preference memory**; factual weather/pricing updates stay on **integrations** (Epic 1 rules), not static knowledge. |
| Stories | 3.1 Itinerary detail add and modify · 3.2 Preference snapshot for replanning and edits |

**Sprint tracking:** `epic-3` **done**; stories `3-1-itinerary-detail-add-and-modify` and `3-2-preference-snapshot-for-replanning-and-edits` **done** (see [`sprint-status.yaml`](./sprint-status.yaml)).

---

## Shipped outcomes (technical summary)

Use this list to anchor the discussion in facts (adjust if the codebase diverges).

### Story 3.1 — Itinerary detail add and modify

- **Validation & finalize:** [`core/itinerary_schema.py`](../../core/itinerary_schema.py) — `validate_edited_itinerary_bundle`, `finalize_edited_bundle`, `ensure_segment_weather_consistency`, `normalize_day_indices`; Epic 1–aligned pricing rollups after edits.
- **APIs:** [`app.py`](../../app.py) — `PUT /itinerary` (session bundle), `PUT /saved/{id}` (SQLite bundle); **400** with `detail.errors`, **404** for missing save.
- **Store:** [`services/itinerary_store.py`](../../services/itinerary_store.py) — `update_saved_itinerary_bundle`.
- **UI:** [`ui/index.html`](../../ui/index.html) — editable day modal (segment fields, move up/down, add/remove, save); routes to correct PUT per `viewingSavedSnapshot` / `lastSavedItineraryId`.
- **Tests:** [`tests/test_itinerary_edit.py`](../../tests/test_itinerary_edit.py).
- **Docs:** [`docs/persistence.md`](../../docs/persistence.md) — edit routing (session vs saved).

### Story 3.2 — Preference snapshot for replanning and edits

- **Merge helper:** [`core/preference_schema.py`](../../core/preference_schema.py) — `merge_trip_snapshot_with_partial` (snapshot defaults + session/LLM overrides).
- **APIs:** [`POST /conversation/message`](../../app.py) and [`POST /plan`](../../app.py) — optional `saved_itinerary_id`; **404** if id missing; responses include `preference_scope`, `replan_from_saved`.
- **Store:** [`update_saved_itinerary_after_replan`](../../services/itinerary_store.py) — updates same row’s `persona_snapshot`, bundle, and derived columns after successful replan from chat.
- **UI:** Send carries `saved_itinerary_id` when viewing a saved trip; **“This trip (saved)”** vs **“New session”** labels in captured preferences; saved banner preserved across replan send.
- **Tests:** [`tests/test_preference_replan.py`](../../tests/test_preference_replan.py).
- **Docs:** [`docs/persistence.md`](../../docs/persistence.md) — chat replan contract, new row vs update.

---

## Facilitation agenda (phases — no fixed durations)

Work through in order; capture notes in **Session notes**.

1. **Set the stage** — Goal: learn together; outcomes over blame.
2. **Epic goals vs reality** — Did structural editing + preference-aware replanning match the “detail editing with preference snapshot” vision? Is the distinction between **saved trip**, **session**, and **replan** clear in the UI?
3. **Story-by-story pulse** — **3.1:** validation strictness, dual PUT paths, manual edit vs API enrichment gaps (e.g. weather-on-save for new coordinates — deferred). **3.2:** merge semantics, same-row update vs new insert, `saved_itinerary_id` contract for clients.
4. **What went well** — Specific examples (tests, docs, reuse of `persona_snapshot`, planner path unchanged for replan).
5. **Challenges & gaps** — Demo **event/simulate** and `ReplannerAgent` paths still use **session** persona, not necessarily trip snapshot; single-tenant SQLite; no drag-across-days; optional enrichment on manual edit.
6. **What’s next** — Hardening, auth/multi-user, UX polish, or new product epics — what matters most?
7. **Action items** — Few, owned, verifiable (fill the table below).

---

## Prompts (optional deep dives)

- Is **“This trip (saved)”** + **Viewing saved trip** banner enough affordance, or do users still confuse chat session state with the opened row?
- Should **weather refresh on save** after manual lat/lon entry be a prioritized follow-up (called out as optional in Story 3.1)?
- Do we need a **single server-side “load saved into session”** endpoint for consistency, or is client hydrate + optional `saved_itinerary_id` on chat sufficient for POC?

---

## Success checklist (Epic 3)

- [x] Both stories delivered against epic themes (structural edits + preference-aware replan) — *verified via implementation artifacts, routes, and tests.*
- [x] [`docs/persistence.md`](../../docs/persistence.md) describes edit APIs, replan body fields, and new-row vs update semantics.
- [x] Top follow-ups captured as **Action items** below (agent-assisted close-out; optional live sync can refine).

---

## Tasks / Subtasks (retrospective close-out)

- [x] Run facilitation (live or async) using **Session notes** below — *completed via agent-assisted synthesis 2026-04-15.*
- [x] **Action items** table populated with owners and verification columns — *see table; open items remain team-owned.*
- [x] Update [`sprint-status.yaml`](./sprint-status.yaml): `epic-3-retrospective` → `done` when the team accepts the record.

---

## Session notes

**Agent-assisted close-out (2026-04-15):** Epic 3 delivered **structural itinerary editing** with server validation and dual persistence (`PUT /itinerary` vs `PUT /saved/{id}`), plus **preference-aware chat replan** via `merge_trip_snapshot_with_partial`, optional `saved_itinerary_id`, and `update_saved_itinerary_after_replan` so the same SQLite row updates instead of always inserting. UI clarifies **This trip (saved)** vs **New session** and preserves the saved banner when replanning from My trips. **Strengths:** tests for edit APIs and preference replan; persistence docs cover edit and replan contracts; planner enrichment path unchanged for regeneration (Epic 1). **Gaps / watch:** demo **event/simulate** / `ReplannerAgent` still driven by **session** persona — not aligned with trip snapshot unless extended; **weather-on-save** after manual coordinate edits remains a documented follow-up; single-tenant visibility of all saves. **Consensus for next steps:** track action items 1–3 on the backlog; optional live retro can adjust wording only.

---

## Action items

| # | Action | Owner | Verify by |
|---|--------|-------|-----------|
| 1 | Decide priority of **weather enrichment on save** when a user adds coordinates in the day editor (Story 3.1 follow-up). | Team | Story or `docs/` decision |
| 2 | Document or implement **persona alignment** for `POST /event/simulate` / `ReplannerAgent` when a saved trip is “active” — or explicitly defer as out of scope for POC. | Team | Docs / backlog |
| 3 | Optional: **backup / DATA_DIR** and SQLite expectations for production-like deploys (if not already covered in Epic 2 action items). | Team | Runbook or `docs/` |
| 4 | Optional live retro: confirm **top 1–3** improvements and adjust this table. | Team | Meeting notes |

---

## Handoff — after Epic 3

- **Product / engineering:** Epic 3 completes the **editing + preference memory** arc on top of Epic 1 (enrichment) and Epic 2 (persistence, list, PDF). Next work is **team choice**: UX polish, auth/multi-tenant storage, mobile/offline, richer replan UX, monitoring, or new feature epics from the roadmap.
- **Stable contracts to preserve:** v2 **`itinerary_bundle`** shape, **`persona_snapshot`** semantics, and the **edit / replan** API contracts documented in [`docs/persistence.md`](../../docs/persistence.md).

---

## Retrospective record

### Facilitator / Agent Model Used

Composer (Cursor agent) — agent-assisted retrospective close-out and sprint tracking update.

### Completion Notes List

- Session notes and task checkboxes completed without code changes; `epic-3-retrospective` set to **done** in [`sprint-status.yaml`](./sprint-status.yaml).
- Full test suite run to confirm no regressions after doc-only edits.

### File List

- `_bmad-output/implementation-artifacts/epic-3-retrospective.md` (this file)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status update)

### Change Log

- Epic 3 retrospective facilitation document created (`create-story`), `epic-3-retrospective` → **ready-for-dev** in sprint tracking (2026-04-15).
- 2026-04-15: Agent-assisted close-out: session notes, tasks checked, status **done**, sprint `epic-3-retrospective` → **done**.

### Review Findings

- [x] [Review][Resolved] **Success checklist** — Checked after verification against shipped stories and `docs/persistence.md`.

---

**Completion status:** done — Retrospective record accepted (agent-assisted); optional live team sync may still refine action items.
