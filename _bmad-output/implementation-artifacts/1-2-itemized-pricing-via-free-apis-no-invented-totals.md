# Story 1.2: Itemized Pricing via Free APIs (No Invented Totals)

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As a traveler,
I want **per-line costs only when integrations provide them**,
so that I am not shown made-up prices from a static catalog.

## Acceptance Criteria

1. **Given** a structured itinerary (activities, legs, stays, etc.),
2. **When** I view line items that can have a price,
3. **Then** each amount is either **(a)** from a **documented free API response** (e.g. public transport, currency rate, a venue/aggregator we integrate), with **currency and source** visible or traceable, or **(b)** explicitly **“not available”** / **“integrate later”** with no numeric fiction,
4. **And** **no hardcoded price list** in the codebase is used to populate live displays as if authoritative,
5. **And** where **AI** helps (e.g. routing a query to the right API or summarizing API JSON), the **stored/displayed price** still traces to API output or remains absent—LLM output is not substituted as silent ground truth,
6. **And** rollups (day/trip totals) include **only** lines with API-backed amounts, with **separate indication** for incomplete coverage.

## Tasks / Subtasks

- [x] **Document pricing integrations** (AC: 3–4)
  - [x] Add `docs/pricing-integration.md` (or extend `docs/`) listing each HTTP integration: base URL, terms/license link, what facts it provides (e.g. ECB reference rates vs. venue fares), and explicit statement that **no static catalog** in repo is used as live pricing truth.
- [x] **Structured per-line pricing model** (AC: 3, 5, 6)
  - [x] Define a **serializable** `pricing` (or equivalent) object on **segments** (and optionally day-level rollups) with: `availability` (`ok` | `unavailable`), `source_id` (string when `ok`), `fetched_at` (ISO-8601 UTC when `ok`), `amount` + `currency` **only** when traceable to API JSON, `error_code` / `reason` when `unavailable`. **Never** copy LLM-proposed numbers into `amount` without an API merge step.
  - [x] Add **day** and **trip** rollup fields computed in code: `api_backed_subtotal`, `currency` (single currency or per-line list—document rule), `coverage_note` when some lines lack API prices.
- [x] **Implement ≥1 real free API client** (AC: 3)
  - [x] Add `services/pricing_service.py` (or split client + mapper) using `requests` with timeouts/retries consistent with [`services/weather_service.py`](../../services/weather_service.py). **Recommended baseline:** [Frankfurter](https://www.frankfurter.dev/) (ECB rates, no API key) for **reference exchange rates**—useful for displaying a consistent currency context; **do not** present FX as a “hotel price.”
  - [x] For **venue/activity line prices** where no integration exists yet, leave `availability: unavailable` and UI copy such as **“Price not available from integrated sources”**—no placeholder euros/dollars.
  - [x] Optional short-lived **cache** (TTL documented) keyed by query parameters—same honesty rules as weather cache.
- [x] **Planner + LLM guardrails** (AC: 4–5)
  - [x] Update [`agents/planner_agent.py`](../../agents/planner_agent.py) system prompt: **forbid** the model from outputting **numeric currency amounts** as authoritative prices in JSON (including `estimated_daily_budget_note`). Prefer **qualitative** budget language (“budget-conscious day”) or **remove** `estimated_daily_budget_note` until API-backed; if kept, strip or validate that it cannot be mistaken for a quoted fare (e.g. prefix “Non-binding:”).
  - [x] After LLM JSON is normalized, run a **post-process** that initializes `pricing` on each segment from **integrations only** (not from LLM fields). [`core/itinerary_schema.py`](../../core/itinerary_schema.py) `normalize_bundle_from_llm` may need to attach default `pricing: {availability: unavailable, reason: ...}` for every segment.
- [x] **Replanner awareness** (AC: 5)
  - [x] Update [`agents/replanner_agent.py`](../../agents/replanner_agent.py) schema description so the LLM does **not** invent prices; preserve or clear `pricing` fields consistently (document: replan may drop enrichment—acceptable short-term if UI shows stale/unavailable honestly).
- [x] **UI** (AC: 3, 6)
  - [x] Update [`ui/index.html`](../../ui/index.html) day modal (and table if needed): per segment, show **API amount + currency + source + fetched time** when `availability === ok`, otherwise show explicit **not available** / **integrate later**; show **day** and **trip** rollup lines that **only sum API-backed amounts** and a **coverage** message when totals are incomplete.
  - [x] If a **trip-level FX snapshot** (Frankfurter) is shown, label it clearly as **reference exchange rates**, not ticket or hotel prices.
- [x] **Tests** (AC: 3–6)
  - [x] Unit tests: mock HTTP for pricing service success/failure; tests that rollups **exclude** non-API lines; test that LLM-normalized bundles get default unavailable pricing without fake amounts.

## Dev Notes

### Epic and product context

- Integration principles and Story 1.2 AC: [epics.md](../planning-artifacts/epics.md) (Overview + Epic 1).
- **Depends on:** Story 1.1 patterns (metadata on segments, docs under `docs/`, pytest under `tests/`) — mirror that discipline for pricing.

### Brownfield — pricing-related gaps

| Area | Location | Issue |
|------|----------|--------|
| Budget prose | [`agents/planner_agent.py`](../../agents/planner_agent.py) | Prompt asks for `estimated_daily_budget_note` per day — **LLM-generated**, can read like a real quote. Must be **disqualified** as authoritative pricing per epic. |
| Segments | [`core/itinerary_schema.py`](../../core/itinerary_schema.py) | No `pricing` object; segments only have activity fields + weather from 1.1. |
| UI | [`ui/index.html`](../../ui/index.html) | Renders `estimated_daily_budget_note` as “Budget note” with no API provenance — risky for Story 1.2. |
| Currency / APIs | — | No `pricing_service` yet. |

### Architecture compliance

- **Single source of numeric truth:** HTTP API responses mapped in Python — same rule as [`docs/weather-integration.md`](../../docs/weather-integration.md) for weather.
- **LLM role:** Planning copy only; **never** persist LLM numbers into `pricing.amount` without a code path from API JSON.
- **Replanner:** JSON-only patches; pricing enrichment may need a **second pass** (future) like weather post-process on replan output.

### Technical stack

- Python 3, FastAPI, `requests`, pytest — see [`requirements.txt`](../../requirements.txt).

### File structure (expected touchpoints)

- `services/pricing_service.py` (new)
- `docs/pricing-integration.md` (new)
- `agents/planner_agent.py` — prompt + post-enrichment hook for pricing defaults
- `core/itinerary_schema.py` — optional defaults in `normalize_bundle_from_llm` / small helpers for rollups
- `agents/replanner_agent.py` — prompt/schema notes
- `ui/index.html` — segment pricing + rollups + budget note handling
- `tests/test_pricing_service.py`, `tests/test_pricing_rollups.py` (new, names flexible)

### Previous story intelligence (1.1)

- Completed story file: [`1-1-weather-via-free-reliable-apis.md`](./1-1-weather-via-free-reliable-apis.md) — use the same **segment metadata pattern** (`availability`, `source`, `fetched_at`, explicit errors).
- **Replanner / weather:** [`docs/weather-integration.md`](../../docs/weather-integration.md) notes replanner does not re-fetch weather; pricing will likely follow the same limitation until a shared **post-process** runs after replan.

### Latest technical information

- **Frankfurter:** Open-source, ECB data, HTTPS `GET` — verify current base URL and response shape at [frankfurter.dev](https://www.frankfurter.dev/) before implementation.
- If you add a second integration later, document **precedence** (which source wins per line type).

### Project context reference

- No `project-context.md` in repo; this file + epics + code paths above are authoritative.

### Library and framework requirements

- No new paid APIs; prefer keyless public endpoints or env-documented keys only if strictly required.

### Testing standards

- Mock `requests` (or session) in unit tests; assert **no** fake amounts in bundle JSON fixtures used as “API” without a mock response.

## Dev Agent Record

### Agent Model Used

Composer (Cursor agent)

### Debug Log References

### Completion Notes List

- Added `default_segment_pricing()`, `qualify_budget_note()`, `ensure_segment_pricing_defaults()`, `compute_pricing_rollups()` in `core/itinerary_schema.py`; segment `pricing` defaults on normalize; budget notes prefixed as non-authoritative.
- `services/pricing_service.py`: Frankfurter `v1/latest` reference rates, cache, `enrich_itinerary_pricing()`; planner calls after weather; `runtime/engine.py` re-enriches after replan.
- `preference_schema`: optional `display_currency` (default USD) for FX targets.
- UI: line pricing, day/trip rollups, ECB reference FX strip with disclaimer; pacing note label; preference chips for `display_currency` / `trip_start_date`.
- Docs: `docs/pricing-integration.md`. Tests: `test_pricing_service.py`, `test_pricing_rollups.py`; planner test mocks `enrich_itinerary_pricing`.

### File List

- `docs/pricing-integration.md` (new)
- `services/pricing_service.py` (new)
- `core/itinerary_schema.py` (modified)
- `core/preference_schema.py` (modified)
- `agents/planner_agent.py` (modified)
- `agents/replanner_agent.py` (modified)
- `runtime/engine.py` (modified)
- `ui/index.html` (modified)
- `tests/test_pricing_service.py` (new)
- `tests/test_pricing_rollups.py` (new)
- `tests/test_planner_weather.py` (modified)

## Change Log

- 2026-04-15: Story 1.2 implemented — segment pricing model, Frankfurter reference FX, rollups, LLM guardrails, UI, tests, replan re-enrichment.
- 2026-04-15: Code review patches — `ALLOWED_SEGMENT_PRICING_SOURCES` + reset untrusted `pricing` in `ensure_segment_pricing_defaults`; Frankfurter retry loop cleanup; `Tuple` import + docs; `test_ensure_segment_pricing_strips_untrusted_llm_amounts`.

### Review Findings

- [x] [Review][Patch] Sanitize LLM segment `pricing` after replan — `ensure_segment_pricing_defaults` only fills missing `pricing` dicts; a replanner-produced segment can keep `availability: ok` with invented `amount`/`currency` because the planner path overwrites pricing in `normalize_bundle_from_llm`, but the replanner path does not. Clear or reset segment amounts unless `source_id` is in a small allowlist populated by real integration merge steps (empty allowlist today). [`core/itinerary_schema.py` `ensure_segment_pricing_defaults` / `enrich_itinerary_pricing`]
- [x] [Review][Patch] Remove unused `last_err` in Frankfurter retry loop — same pattern as weather service cleanup. [`services/pricing_service.py` ~70–72]
- [x] [Review][Defer] Trip rollup + ECB reference strip repeat inside every day modal — [`ui/index.html` `openDayModal`] — deferred, pre-existing UX nit; could show trip-level blocks once (e.g. only in first day or a summary panel).

---

**Completion status:** done — Review patches applied (2026-04-15).
