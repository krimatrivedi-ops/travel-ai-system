# Pricing integrations

## Principles

- **No static price catalogs** in this repository are used as live, authoritative amounts. Numeric line prices appear **only** when mapped from a **documented HTTP API** response in application code.
- **LLM output** (including qualitative “budget notes”) is **not** a source of truth for money; it must not be copied into `pricing.amount` without an API merge step.
- **Frankfurter** reference rates are **not** hotel or ticket prices — they are **ECB reference exchange rates** for currency context only.

## Frankfurter (ECB reference rates)

- **Base URL:** `https://api.frankfurter.dev/v1` (see [Frankfurter](https://www.frankfurter.dev/))
- **License:** Open-source project; data from the European Central Bank — see project site for terms.
- **What we use it for:** `GET /latest` to show **reference** FX (e.g. EUR → `display_currency` and a few targets). Labeled in the UI as **reference exchange rates**, not activity pricing.
- **Environment variables:** `PRICING_HTTP_TIMEOUT` (default `10`), `PRICING_CACHE_TTL_SECONDS` (default `3600`), `PRICING_MAX_RETRIES` (default `2`).

## Segment line prices (venues, transport, etc.)

- **Not yet integrated:** Default segment `pricing` is `availability: unavailable` with reason **“Price not available from integrated sources.”** Future stories may attach venue or transit APIs; until then, the UI shows explicit unavailability — **no placeholder euros/dollars**.
- **Trusted sources:** Application code that maps HTTP responses to segment `pricing` must set `source_id` to a value listed in `ALLOWED_SEGMENT_PRICING_SOURCES` in `core/itinerary_schema.py`. Any segment with `availability: ok` and a non-null `amount` whose `source_id` is not allowlisted is reset to the default unavailable object (e.g. after a replanner LLM invents prices).

## Cache

- In-process TTL cache for Frankfurter queries keyed by base + target currency set. **Invalidation:** time-based only; cached values remain HTTP-backed snapshots.

## Rollups

- **Day** and **trip** subtotals sum **only** segments with `pricing.availability === "ok"` and a numeric `amount`. Mixed currencies among API-backed lines suppresses the numeric total with a coverage note (see `core.itinerary_schema.compute_pricing_rollups`).
