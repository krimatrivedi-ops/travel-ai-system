# Story 2.3: PDF Download Per Itinerary

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As a traveler,
I want to download any saved itinerary as a PDF,
so that I can share or print it offline.

## Acceptance Criteria

1. **Given** a saved itinerary (record in SQLite `saved_itineraries`),
2. **When** I choose **Download PDF** (or equivalent),
3. **Then** the PDF includes **days and activities** (segments) in a readable structure,
4. **And** **weather** and **pricing** appear **only** as **persisted snapshot values** from the stored bundle, or explicit **unavailable / not available** wording when the bundle has no API-backed data — **never** invented numbers or fake “live” claims (aligned with [Epic 1 integration rules](../planning-artifacts/epics.md) and Story 2.1 snapshot semantics),
5. **And** optional **footnotes or a short “Sources” section** listing weather/price **source ids** and **fetch timestamps** where those fields exist on segments or rollups,
6. **And** the browser receives a file with a **sensible filename** (e.g. destination + date range + stable id fragment, ASCII-safe),
7. **And** invalid or missing saved ids return **404** with no partial PDF.

## Tasks / Subtasks

- [x] **PDF generation module** (AC: 3–6)
  - [x] Add a dedicated builder, e.g. [`services/pdf_export.py`](../../services/pdf_export.py) (name flexible), with a single entry like `build_itinerary_pdf_bytes(record: dict) -> bytes` where `record` is the **same shape** as [`get_saved_itinerary`](../../services/itinerary_store.py) (includes `destination`, `trip_date_start`, `trip_date_end`, `persona_snapshot`, `itinerary_bundle`).
  - [x] Implement layout for **v2** bundles: [`core/itinerary_schema.py`](../../core/itinerary_schema.py) — iterate `itinerary_bundle["days"]`, each day `title` / `summary`, each segment `time_label`, `title`, `place_name`, `description` (truncate long text sensibly), optional meal/transport lines if present in JSON.
  - [x] **Weather:** For each segment, mirror UI semantics from [`ui/index.html`](../../ui/index.html) (`weather_availability`, `weather_error`, `weather_source`, `weather_fetched_at`, displayed conditions when present). If unavailable, print a clear label — **do not** fabricate forecasts.
  - [x] **Pricing:** For each segment `pricing`, show API-backed amount + currency only when `availability == "ok"` and `amount` is set; otherwise print the persisted reason / unavailable state. Include day/trip rollup sections only if `pricing_rollups` / bundle rollups exist and match Epic 1 rules (sums of API-backed lines only).
  - [x] Add a cover block: destination, trip date range, `created_at` (saved time), optional one-line note: *“Exported from stored trip data (historical snapshot).”*
  - [x] **Library choice:** Use **pure-Python PDF** generation suitable for server deploy without LibreOffice. Recommended: **`fpdf2`** (add to [`requirements.txt`](../../requirements.txt) with a pinned or minimum version) *or* `reportlab` — pick one, document in module docstring; avoid adding heavy system dependencies (e.g. wkhtmltopdf) unless justified.
  - [x] **UTF-8 / symbols:** Ensure common travel text and currency symbols render; if `fpdf2`, use built-in Unicode/font handling per library docs — test with a non-ASCII destination if feasible.

- [x] **HTTP API** (AC: 1–2, 7)
  - [x] Add **`GET /saved/{saved_id}/pdf`** (or `GET /saved/{saved_id}/export.pdf` — choose one, keep RESTful) in [`app.py`](../../app.py): load row via `get_saved_itinerary(saved_id)`; if `None`, **404**; else return `Response` / `StreamingResponse` with `media_type="application/pdf"` and **`Content-Disposition: attachment; filename="..."`** using a **sanitized** filename helper (ASCII slug from destination + dates + short id suffix).
  - [x] Do **not** re-fetch weather or pricing APIs during PDF build — **only** serialize what is already in `itinerary_bundle`.

- [x] **UI** (AC: 2)
  - [x] In [`ui/index.html`](../../ui/index.html) **My trips** table: add a **Download PDF** control per row (button or icon) with **`event.stopPropagation()`** so it does not trigger row-open. Link or `fetch` + blob download to `GET /saved/{id}/pdf` with the correct filename from `Content-Disposition` or a client-side fallback matching the server rule.
  - [x] Optional enhancement: if the chat response after generation includes **`saved_itinerary_id`** (already returned by [`app.py`](../../app.py)), show a **Download PDF** action near the itinerary panel for that id — same endpoint — so users need not find the row in My trips.

- [x] **Documentation** (AC: 4–5)
  - [x] Extend [`docs/persistence.md`](../../docs/persistence.md) with the PDF endpoint, snapshot semantics, and filename behavior.

- [x] **Tests** (AC: 3–7)
  - [x] Unit test: `build_itinerary_pdf_bytes` (or route) with a **tmp DB** fixture inserting a minimal saved itinerary — assert PDF bytes start with `%PDF`, assert 404 for unknown id via `TestClient`.
  - [x] Optional: assert generated PDF contains a known substring from destination or day title (decode cautiously — binary-safe checks).

## Dev Notes

### Epic and product context

- Epic 2 overview: [epics.md](../planning-artifacts/epics.md) — **History and export**; PDF must follow same **non-static** rules as the app: only stored API-backed or labeled unavailable content.
- **Depends on:** Stories **2.1** (persisted bundle + `get_saved_itinerary`), **2.2** (list + open saved trips). Reuse stored JSON **as-is**.

### Brownfield — current behavior

| Area | Location | Notes |
|------|----------|--------|
| Saved record | [`services/itinerary_store.py`](../../services/itinerary_store.py) | `get_saved_itinerary(id)` returns parsed `persona_snapshot` + `itinerary_bundle`. |
| List / open UI | [`ui/index.html`](../../ui/index.html) | My trips rows call `openSavedItinerary`; add PDF without breaking row click. |
| Success response | [`app.py`](../../app.py) | May include `saved_itinerary_id` for last save — usable for optional inline Download. |
| Dependencies | [`requirements.txt`](../../requirements.txt) | Has `python-docx` but **does not** produce PDF natively; **add** a PDF library for this story. |

### Architecture compliance

- **FastAPI** streaming/file response patterns; **no new database tables** — export is derived from existing rows.
- **Single-tenant:** Same visibility as list — any saved id is downloadable (POC).
- **Security:** Filename from server-side sanitization only; **path traversal** N/A for UUID id but validate id format if adding stricter checks.

### Scope boundary

- **In scope:** One PDF layout for v2 bundles; snapshot-only content; My trips download; optional download when `saved_itinerary_id` is known.
- **Out of scope:** Editable PDFs, email delivery, multi-language templates, **Epic 3** editing flows.

### Previous story intelligence (2.2)

- **Client hydrate** pattern: full trip loaded with `GET /saved/{id}` — PDF should use the **same** underlying record as the UI snapshot, not session state.
- **Polling guard** (`viewingSavedSnapshot`) is unrelated to PDF; PDF generation is **server-side** and idempotent per request.
- Tests use **`set_database_path_for_tests`** — follow the same pattern as [`tests/test_saved_list.py`](../../tests/test_saved_list.py).

### File structure (expected touchpoints)

- New: [`services/pdf_export.py`](../../services/pdf_export.py) (or `export/pdf_itinerary.py`).
- [`app.py`](../../app.py) — PDF route.
- [`ui/index.html`](../../ui/index.html) — Download controls + blob download helper if needed.
- [`docs/persistence.md`](../../docs/persistence.md).
- [`tests/test_pdf_export.py`](../../tests/test_pdf_export.py) (new).
- [`requirements.txt`](../../requirements.txt) — PDF dependency.

### Technical requirements (guardrails)

- **No live API calls** inside PDF builder.
- **Epic 1 alignment:** Same distinction between API-backed prices and unavailable — mirror labels used in UI strings where practical.
- **Errors:** 404 for missing save; 500 only on unexpected failures — log server-side.

### Library / framework notes (latest-practice summary)

- **`fpdf2`** (actively maintained fork of FPDF): common choice for simple reports; check current docs for `FPDF` Unicode/font handling (`add_font` / `DejaVu` paths) for international destinations.
- **`reportlab`**: more layout control, heavier API — acceptable if team prefers Platypus flows.
- Avoid **phantom** dependencies: do not use `python-docx` alone for “PDF” without a documented conversion pipeline.

### Testing standards

- **pytest** + **TestClient**; tmp SQLite via `set_database_path_for_tests`.
- Keep tests **fast** — no real network.

### Project context reference

- No `project-context.md` in repo; this file + [`core/itinerary_schema.py`](../../core/itinerary_schema.py) + [`docs/persistence.md`](../../docs/persistence.md) are authoritative.

## Dev Agent Record

### Agent Model Used

Composer (Cursor agent)

### Debug Log References

None.

### Completion Notes List

- Implemented [`services/pdf_export.py`](../../services/pdf_export.py) with **fpdf2**: cover snapshot notice, days/segments, weather/pricing from stored JSON only, optional FX/rollup blocks, **Sources** lines for weather metadata. Text normalized to Latin-1-safe for core Helvetica fonts (avoid Unicode encoding errors).
- **`GET /saved/{saved_id}/pdf`** returns PDF with `Content-Disposition`; 404 when missing; `pdf_attachment_filename()` for ASCII filenames.
- UI: **PDF** column in My trips (row click ignores PDF cell); **Download PDF** under itinerary when `saved_itinerary_id` exists or after opening a saved trip; blob download reads `Content-Disposition` filename.
- [`docs/persistence.md`](../../docs/persistence.md) updated; [`tests/test_pdf_export.py`](../../tests/test_pdf_export.py); [`requirements.txt`](../../requirements.txt) pins `fpdf2==2.8.2`.

### File List

- `services/pdf_export.py`
- `app.py`
- `ui/index.html`
- `docs/persistence.md`
- `tests/test_pdf_export.py`
- `requirements.txt`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

### Change Log

- Story 2.3: PDF export pipeline, API route, My trips + itinerary panel download, tests, fpdf2 dependency (2026-04-15).
- 2026-04-16: Code review patch — PDF segment extras use `meal_suggestion`, `transport_note`, `local_tip` with UI-aligned labels.

### Review Findings

- [x] [Review][Patch] **Segment optional fields use wrong JSON keys** — [`services/pdf_export.py`](../../services/pdf_export.py) reads `meal_note`, `stay_note` alongside `transport_note`, but v2 bundles from [`normalize_bundle_from_llm`](../../core/itinerary_schema.py) use **`meal_suggestion`**, **`transport_note`**, **`local_tip`**. Meal/local-tip lines are therefore omitted from PDFs. Align keys (and labels) with the schema / UI.
- [x] [Review][Defer] **Unicode / Latin-1** — `_latin1_safe` replaces non–Latin-1 characters; destinations with CJK or accented text may appear degraded in PDF. Documented tradeoff in module docstring; full Unicode would need DejaVu/`add_font` in fpdf2.
- [x] [Review][Defer] **Sources section** — Weather footnotes aggregated; pricing `source_id`/`fetched_at` appear per segment when API-backed, but not duplicated in the aggregate “Sources (snapshot metadata)” block. Acceptable POC; extend if stricter AC5 parity is required.

---

**Completion status:** done — Review patch applied (2026-04-16).
