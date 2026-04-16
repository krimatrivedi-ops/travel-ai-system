# Epic 2 Retrospective — History and Export

Status: done

<!-- Retrospective facilitation pack — run as a team session; not a code implementation story. After the session, set epic-2-retrospective to `done` in sprint-status.yaml and capture action items below. -->

## Purpose

Facilitate a **blame-free** post-epic review for **Epic 2: History and Export** in **travel-ai-system**: extract lessons, confirm outcomes against [epics.md](../planning-artifacts/epics.md), and prepare for **Epic 3: Detail Editing With Preference Snapshot**.

**Psychological safety:** Focus on systems, processes, and learning — not individual fault.

---

## Epic 2 recap (source of truth)

| Item | Intent (from epics) |
|------|------------------------|
| Theme | **Persist** generated itineraries, **browse** past trips, **export PDF** — exports follow the same rules as the app: weather/pricing as **snapshots** or honest unavailable labels (aligned with Epic 1). |
| Stories | 2.1 Persist generated itineraries · 2.2 Past itineraries list · 2.3 PDF download per itinerary |

**Sprint tracking:** `epic-2` **done**; stories `2-1-persist-generated-itineraries`, `2-2-past-itineraries-list`, and `2-3-pdf-download-per-itinerary` **done** (see [`sprint-status.yaml`](./sprint-status.yaml)).

---

## Shipped outcomes (technical summary)

Use this list to anchor the discussion in facts (adjust if the codebase diverges).

### Story 2.1 — Persist generated itineraries

- **Storage:** SQLite table `saved_itineraries` (`services/itinerary_store.py`) — UUID `id`, `created_at`, `destination`, trip dates, `persona_snapshot` JSON, `itinerary_bundle` JSON (full v2 bundle including Epic 1 enrichment).
- **Hook:** Successful generation path in `app.py` calls `save_generated_itinerary`; response may include `saved_itinerary_id`.
- **Tests:** `tests/test_itinerary_store.py`, `tests/test_app_persistence.py` (failure path does not save).
- **Docs:** [`docs/persistence.md`](../../docs/persistence.md) — record shape, snapshot semantics.

### Story 2.2 — Past itineraries list

- **API:** `GET /saved` — summaries (newest first) via `list_saved_itinerary_summaries()`; `GET /saved/{id}` — full row for client hydrate.
- **UI:** [`ui/index.html`](../../ui/index.html) — **My trips** table; opening a row loads snapshot into itinerary + preference chips; **Viewing saved trip** banner; `viewingSavedSnapshot` skips periodic `/state` polling so the snapshot is not overwritten.
- **Pattern:** Client-only hydrate — no server session mutation when opening a saved trip (documented in `docs/persistence.md`).
- **Tests:** `tests/test_saved_list.py`.

### Story 2.3 — PDF download per itinerary

- **Export:** [`services/pdf_export.py`](../../services/pdf_export.py) — `build_itinerary_pdf_bytes` using **fpdf2**; snapshot-only (no live API calls during PDF build); Latin-1–safe text for core PDF fonts (Helvetica).
- **API:** `GET /saved/{id}/pdf` — `application/pdf`, ASCII-safe `Content-Disposition` filename via `pdf_attachment_filename`.
- **UI:** PDF column per My trips row (click isolated from row-open); **Download PDF** near itinerary when `saved_itinerary_id` is known or after opening a saved trip; blob download respects server filename.
- **Tests:** `tests/test_pdf_export.py`.
- **Dependency:** `fpdf2` in [`requirements.txt`](../../requirements.txt).

---

## Facilitation agenda (phases — no fixed durations)

Work through in order; capture notes in **Session notes**.

1. **Set the stage** — Goal: learn together; outcomes over blame.
2. **Epic goals vs reality** — Did persistence + list + PDF meet the “history and export” vision? Are snapshot/historical semantics clear to users?
3. **Story-by-story pulse** — **2.1:** durability and single save path. **2.2:** list UX, client hydrate vs server state tradeoffs, polling guard. **2.3:** PDF fidelity vs bundle schema, Unicode/latin-1 tradeoff in exports.
4. **What went well** — Specific examples (tests, docs, reuse of `get_saved_itinerary` for PDF and UI).
5. **Challenges & gaps** — Single-tenant visibility of all saves; PDF typography for non-Latin destinations; any confusion between “live” session state and saved snapshot.
6. **Epic 3 preview** — Editing and preference memory will touch persisted trips — what contracts (bundle shape, `persona_snapshot`) must stay stable?
7. **Action items** — Few, owned, verifiable (fill the table below).

---

## Prompts (optional deep dives)

- Does the **My trips** + **Viewing saved trip** flow reduce confusion between chat session and saved history, or should we add stronger affordances?
- Is **PDF** content “good enough” for sharing, or do we need richer layout / embedded Unicode fonts before external users?
- What **monitoring or backup** expectations exist for the SQLite file in deployment (POC vs production)?

---

## Success checklist (Epic 2)

- [x] All three stories delivered against epic themes (persist, browse, PDF with snapshot rules) — *verified via implementation artifacts and routes.*
- [x] [`docs/persistence.md`](../../docs/persistence.md) describes APIs and snapshot semantics including PDF.
- [x] Top follow-ups captured as **Action items** below (agent-assisted close-out; optional live sync can refine).

---

## Tasks / Subtasks (retrospective close-out)

- [x] Run facilitation (live or async) using **Session notes** below — *completed via agent-assisted synthesis 2026-04-15.*
- [x] **Action items** table populated with owners and verification columns — *see table; open items remain team-owned.*
- [x] Update [`sprint-status.yaml`](./sprint-status.yaml): `epic-2-retrospective` → `done` when the team accepts the record.

---

## Session notes

**Agent-assisted close-out (2026-04-15):** Epic 2 delivered durable SQLite persistence, a newest-first **My trips** list with client-side hydrate and polling guard, and PDF export from stored bundles only (fpdf2, no live enrichment calls). Documentation in `docs/persistence.md` matches API behavior. Tests cover store list, PDF bytes, and app routes. **Strengths:** single source of truth via `get_saved_itinerary` for detail and PDF; explicit snapshot copy and banner. **Gaps / watch:** single-tenant visibility of all saves; PDF uses Latin-1–safe Helvetica text (non-Latin destinations may degrade); server `/state` vs hydrated saved trip divergence until reset — must inform Epic 3 editing UX. **Consensus for next steps:** track action items 1–3 before Epic 3; optional live retro can adjust wording only.

---

## Action items

| # | Action | Owner | Verify by |
|---|--------|-------|-----------|
| 1 | Confirm **Epic 3** stories align with persisted bundle + `persona_snapshot` contracts (no breaking schema changes without migration). | Team | Epic 3 story specs |
| 2 | Decide whether **PDF export** needs a **Unicode font** path (fpdf2 `add_font`) for non-Latin destinations — or document Latin-1 limitation as acceptable for POC. | Team | Decision in docs or story |
| 3 | Optional: define **backup / DATA_DIR** expectations for SQLite in deployment notes. | Team | `docs/` or runbook |
| 4 | Optional live retro: confirm **top 1–3** improvements and adjust this table. | Team | Meeting notes |

---

## Handoff to Epic 3

- **Epic 3** ([epics.md](../planning-artifacts/epics.md)): itinerary **editing** and **preference snapshot** for replanning — factual refreshes still via integrations (Epic 1 rules).
- **Carry forward:** Stable **`itinerary_bundle`** v2 shape and **`persona_snapshot`** semantics; saved trips are the source of truth for “what was stored” until edits land in Epic 3.
- **Risks to flag:** Client-hydrate pattern means server `/state` may not reflect an opened saved trip until reset or new message — editing flows should not assume server session equals on-screen saved trip without explicit design.

---

## Retrospective record

### Facilitator / Agent Model Used

Composer (Cursor agent) — agent-assisted retrospective close-out and sprint tracking update.

### Completion Notes List

- Session notes and task checkboxes completed without code changes; `epic-2-retrospective` set to **done** in `sprint-status.yaml`.
- Full test suite run to confirm no regressions after doc-only edits.

### File List

- `_bmad-output/implementation-artifacts/epic-2-retrospective.md` (this file)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status update)

### Change Log

- 2026-04-15: Retrospective facilitation document created (`create-story`); `epic-2-retrospective` set to `ready-for-dev` in sprint tracking.
- 2026-04-16: Code review patch — Action item #4 owner set to `Team`.
- 2026-04-15: Agent-assisted close-out: session notes, tasks checked, status **done**, sprint `epic-2-retrospective` → **done**.

### Review Findings (document QA)

- [x] [Review][Patch] **Action items table — owner column** — Row 4 lists owner as `Ubuntu / team`, which reads like a placeholder username. Replace with `Team` or `Facilitator` for a neutral, reusable record. [`epic-2-retrospective.md` Action items]
- [x] [Review][Resolved] **Session notes** — Filled with agent-assisted summary 2026-04-15; optional live retro can extend.

---

**Completion status:** done — Retrospective record accepted (agent-assisted); optional live team sync may still refine action items.
