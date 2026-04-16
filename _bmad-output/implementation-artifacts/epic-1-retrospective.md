# Epic 1 Retrospective — Itinerary Enrichment (Integration-Backed)

Status: done

<!-- Retrospective facilitation pack — run as a team session; not a code implementation story. After the session, set epic-1-retrospective to `done` in sprint-status.yaml and capture action items below. -->

## Purpose

Facilitate a **blame-free** post-epic review for **Epic 1: Itinerary Enrichment** in **travel-ai-system**: extract lessons, confirm outcomes against [epics.md](../planning-artifacts/epics.md), and prepare for **Epic 2: History and Export**.

**Psychological safety:** Focus on systems, processes, and learning — not individual fault.

---

## Epic 1 recap (source of truth)

| Item | Intent (from epics) |
|------|---------------------|
| Theme | Enrich itineraries with **live** weather and **API-backed** pricing where possible — no static tables as ground truth. |
| Integration principles | Transparent sourcing; timeouts/retries; user-visible degradation; documented providers. |
| Stories | 1.1 Weather via free reliable APIs · 1.2 Itemized pricing via free APIs (no invented totals) |

**Sprint tracking:** `epic-1` **done**; stories `1-1-weather-via-free-reliable-apis` and `1-2-itemized-pricing-via-free-apis-no-invented-totals` **done** (see `sprint-status.yaml`).

---

## Shipped outcomes (technical summary)

Use this list to anchor the discussion in facts (adjust if the codebase diverges).

### Story 1.1 — Weather

- **Provider:** Open-Meteo daily forecast aligned to trip calendar days (`trip_start_date` or generation date).
- **Code touchpoints:** `services/weather_service.py`, `agents/planner_agent.py` (post-LLM enrichment), `core/preference_schema.trip_anchor_date`, `ui/index.html` (attribution, unavailable states).
- **Docs:** `docs/weather-integration.md`.
- **Known limitation (documented):** Replanner path does not re-call weather enrichment; forecasts may be stale after replan until a future unified post-process.

### Story 1.2 — Pricing

- **Provider:** Frankfurter ECB **reference** FX (`services/pricing_service.py`) — explicitly **not** hotel or ticket prices.
- **Model:** Per-segment `pricing` object (`availability`, `source_id`, `fetched_at`, `amount`/`currency` only when API-backed); default **unavailable** for venue lines until future integrations.
- **Rollups:** `core.itinerary_schema.compute_pricing_rollups` — sums only API-backed lines; mixed currencies suppresses naive totals with coverage notes.
- **LLM guardrails:** Qualitative budget notes only; `qualify_budget_note` prefixing; no numeric money in planner JSON as authoritative.
- **Docs:** `docs/pricing-integration.md`.
- **Replans:** `runtime/engine.py` re-runs `enrich_itinerary_pricing` after replan events.

---

## Facilitation agenda (phases — no fixed durations)

Work through in order; capture notes in **Session notes**.

1. **Set the stage** — Goal: learn together; outcomes over blame.
2. **Epic goals vs reality** — Did we meet the integration-backed enrichment vision? Where did UX or honesty rules shine or fall short?
3. **Story-by-story pulse** — Weather: attribution and failure modes. Pricing: clarity of “reference FX” vs line prices; rollup behavior when no venue API exists.
4. **What went well** — Specific examples (tests, docs, patterns reused from 1.1 → 1.2).
5. **Challenges & gaps** — Replanner vs planner parity; test coverage; anything that felt fragile in production-like use.
6. **Epic 2 preview** — Persisted itineraries and PDFs must preserve the same non-static rules — what should we carry forward or automate earlier?
7. **Action items** — Few, owned, verifiable (fill the table below).

---

## Prompts (optional deep dives)

- Where could a user **mistake** qualitative text or FX rates for a **quoted trip cost**? Are labels sufficient?
- Are **cache TTLs** (weather vs FX) appropriate for fair-use and freshness?
- Do we need a **single post-enrichment pipeline** after both planner and replanner for weather + pricing parity?

---

## Success checklist (Epic 1)

- [x] Both stories’ acceptance themes reflected in shipped behavior (live HTTP, no fake numbers as truth) — *verified via implementation artifacts and services.*
- [x] Documentation exists for each integrated provider (`docs/weather-integration.md`, `docs/pricing-integration.md`).
- [ ] Team agrees on **top 1–3** improvements before Epic 2 — *live discussion; optional follow-up.*

---

## Tasks / Subtasks (retrospective close-out)

- [x] Verify provider docs exist on disk for Epic 1 integrations.
- [x] Confirm planner vs engine enrichment paths in code (`planner_agent`, `engine` + pricing enrichment).
- [x] Record session summary and action items in this file.
- [x] Update `sprint-status.yaml`: `epic-1-retrospective` → `done`.

---

## Session notes

**Prepared completion record (agent-assisted, 2026-04-16):** Epics 1.1 and 1.2 delivered integration-backed weather (Open-Meteo) and pricing reference data (Frankfurter) with explicit unavailable states, rollups, UI attribution, and pytest coverage. Documentation for both providers is present under `docs/`. A known gap remains **planner vs replanner parity for weather**: initial generation enriches segments via `fetch_daily_weather`; replanner output is not automatically re-enriched for weather in the same way pricing is after `enrich_itinerary_pricing` in `runtime/engine.py`. Epic 2 should persist bundles with timestamps/sources so exports do not imply stale API data is “live.”

---

## Action items

| # | Action | Owner | Verify by |
|---|--------|-------|-----------|
| 1 | Prioritize a **unified post-enrichment** step (weather + pricing) after replanner output for parity with planner. | Team | Code review + manual replan smoke test |
| 2 | When starting **Epic 2**, define storage fields for **weather/pricing snapshot metadata** (fetched_at, source ids) on persisted itineraries. | Team | Story 2.1 spec |
| 3 | Optional live retro: confirm **top 1–3** improvements and adjust this table. | Ubuntu / team | Meeting notes |

---

## Handoff to Epic 2

- **Epic 2** ([epics.md](../planning-artifacts/epics.md)): persist itineraries, list past trips, PDF export — **same rules** for weather/pricing blocks (snapshots or explicit unavailable).
- **Risks to flag:** Storing enriched bundles without implying stale API data is “current” unless timestamps/sources travel with exports.

---

## Retrospective record

### Facilitator / Agent Model Used

Composer (Cursor agent) — close-out verification for dev-story workflow.

### Completion Notes List

- Verified `docs/weather-integration.md` and `docs/pricing-integration.md` exist.
- Confirmed `enrich_itinerary_pricing` runs from `planner_agent` and after replan in `runtime/engine.py`; weather enrichment remains planner-primary with documented replan limitation.

### File List

- `_bmad-output/implementation-artifacts/epic-1-retrospective.md` (this file)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status update)

## Change Log

- 2026-04-16: Retrospective record completed (agent-assisted verification); sprint tracking set to `done` for `epic-1-retrospective`.

---

**Completion status:** done — Retrospective artifact closed out; optional live team sync can still refine action items.
