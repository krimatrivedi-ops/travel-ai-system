# Persisted itineraries (SQLite)

## Why SQLite

- **Single file**, no separate database server — fits POC and single-instance deployment.
- **stdlib `sqlite3`** — no extra Python dependencies.
- **Durable** across process restarts (unlike in-memory `state/store.py` session state).

## Location

- Default directory: `DATA_DIR` environment variable, or `./data` under the process working directory.
- Default database file: `TRAVEL_AI_DB` or `{DATA_DIR}/itineraries.sqlite3`.

## Record shape

Each successful generation stores:

| Column | Meaning |
|--------|---------|
| `id` | UUID (primary key) |
| `created_at` | UTC ISO-8601 when saved |
| `destination` | From persona |
| `trip_date_start` / `trip_date_end` | Derived from `trip_start_date` (or today) + `trip_duration` |
| `persona_snapshot` | JSON — normalized persona at generation time |
| `itinerary_bundle` | Full v2 bundle JSON, including Epic 1 enrichment (weather, pricing, FX snapshot) |

Snapshots are **historical**; they are not refreshed as “live” data after save.

## API

- **`GET /saved`** — JSON array of summary objects for the **My trips** list (newest first): `id`, `title` (first-day theme when present, else destination + dates), `destination`, `trip_date_start`, `trip_date_end`, `created_at`.
- **`GET /saved/{id}`** — Full record: `persona_snapshot`, `itinerary_bundle`, plus metadata columns. Used when opening a row; the UI treats this as a **saved snapshot**, not live-refreshed data.

- **`GET /saved/{id}/pdf`** — Returns `application/pdf` with `Content-Disposition: attachment; filename="..."`. The PDF is built **only** from the stored row (same snapshot as the UI). **No** weather or pricing APIs are called during export. Weather and price lines are **persisted** snapshot values or explicit unavailable labels, matching Epic 1 rules. The suggested filename is ASCII-safe: destination slug + trip date range + short id prefix + `.pdf`.

- **`PUT /itinerary`** — JSON body `{ "itinerary": <v2 bundle> }`. Replaces the **in-memory** session itinerary in [`state/store.py`](../state/store.py). Use when the user is **not** in “viewing saved trip only” mode (see below). Server validates the bundle, normalizes day indices, enforces Epic 1 pricing/weather consistency (e.g. no API-ok weather without coordinates), recomputes pricing rollups, returns `{ "ok": true, "itinerary": ... }`. **400** with `{ "detail": { "errors": [...] } }` if invalid.

- **`PUT /saved/{id}`** — JSON body `{ "itinerary_bundle": <v2 bundle> }`. Writes the updated bundle to SQLite for that saved id. Use when the UI is showing a **hydrated saved trip** (`viewing saved snapshot` flow) so the durable row stays the source of truth. Same validation and finalize step as `PUT /itinerary`. **404** if id does not exist.

**Edit routing rule (UI):** If the user opened a trip from **My trips** (saved snapshot), call **`PUT /saved/{id}`** only. If they are editing the **current generated** itinerary without that mode, call **`PUT /itinerary`**. Do not send both for one save — avoids conflicting writes when a session id and a saved id both exist.

After edits, the bundle remains a **snapshot** until any future live refresh or replan (Epic 1 / Story 3.2). **Weather enrichment on save** for new coordinates is optional follow-up; segments without lat/lon keep weather unavailable.

### Chat replan with trip preference snapshot (Story 3.2)

- **`POST /conversation/message`** — JSON body `{ "message": string, "saved_itinerary_id"?: string }`. The optional **`saved_itinerary_id`** is the UUID of a row in `saved_itineraries` when the user is replanning from an opened **My trips** entry.
  - **404** if `saved_itinerary_id` is set but the row does not exist.
  - **Merge rule:** The server loads **`persona_snapshot`** from that row and merges it with session `partial_persona` via [`merge_trip_snapshot_with_partial`](../core/preference_schema.py): normalized snapshot defaults, with session/preference-LLM fields overriding. This is the base passed into [`process_turn`](../services/preference_llm.py) so replanning stays aligned with the trip’s original scope.
  - **New row vs update:** If `saved_itinerary_id` is **omitted**, a successful generation still calls **`save_generated_itinerary`** (new UUID). If **`saved_itinerary_id` is present**, a successful generation calls **`update_saved_itinerary_after_replan`** — same row id, updated `persona_snapshot`, `itinerary_bundle`, and derived `destination` / trip date columns.
  - **Response extras:** `preference_scope` is `"trip_saved"` or `"session"`; `replan_from_saved` is `true` when the request carried a valid `saved_itinerary_id` and generation succeeded (same shape for `need_more` when a snapshot was loaded).

- **`POST /plan`** — Same optional `saved_itinerary_id` on the JSON body (alongside `user_input`).

The UI sends `saved_itinerary_id` when **Viewing saved trip** is active so the chat does not drop trip context. Regeneration still runs the normal **`PlannerAgent`** pipeline (live weather/pricing enrichment), not static data.

### Opening a saved trip (client-side hydrate)

We use **client-only** loading: the browser calls `GET /saved/{id}` and passes the returned JSON into the itinerary renderer and preference chips. There is **no** `POST /conversation/load-saved` (or similar) that copies the bundle into the server’s in-memory [`state/store.py`](../state/store.py) session.

**Why (POC tradeoffs):**

- **Pros:** Avoids surprising overwrites of the live conversation state when the user opens an old trip; keeps the server stateless with respect to “which saved trip is open”; simpler to reason about for single-tenant demos.
- **Cons:** The “current” session in `/state` and the on-screen saved trip can diverge until the user sends a message or resets; the UI shows a **Viewing saved trip** banner and skips polling `/state` while a snapshot is displayed so the client view is not overwritten.

## Multi-user

Current scope is single-tenant POC. A future `user_id` column would be required for authenticated multi-user storage.
