# Weather integration (Open-Meteo)

## Provider

- **Name:** Open-Meteo Forecast API  
- **Base URL:** `https://api.open-meteo.com/v1/forecast`  
- **Terms / license:** [https://open-meteo.com/en/license](https://open-meteo.com/en/license) — non-commercial use free without an API key on the public endpoint; data is fetched over **HTTPS** at request time, not embedded as static tables in the app.

## Behavior

- **Trip alignment:** Each itinerary day uses a **calendar date** starting from `persona["trip_start_date"]` (ISO `YYYY-MM-DD`) when set; otherwise the **generation date** (today). Segments use **daily** forecast variables for that date and the segment’s coordinates.
- **No static “typical climate”:** Displayed values come only from API responses (or an explicit unavailable state).
- **Attribution:** The UI and stored segment payload include `weather_source` (`open-meteo`) and `weather_fetched_at` (UTC ISO-8601).

## Planner vs replanner

- **Initial generation:** `PlannerAgent` calls `fetch_daily_weather` after the LLM builds the itinerary and merges forecast metadata onto each segment. That is when live HTTP-backed weather is attached.
- **Replans / edits:** `ReplannerAgent` patches the itinerary via the LLM only; it does **not** re-call the weather service or re-merge segment weather. Forecasts shown after a replan are whatever the model preserved in JSON (they may be missing or stale). A future change could post-process replanner output the same way as the planner.

## Cache (performance)

- **In-process TTL cache** keyed by `(latitude, longitude, forecast_date)`.
- **Default TTL:** 900 seconds (15 minutes), overridable with `WEATHER_CACHE_TTL_SECONDS`.
- **Invalidation:** Time-based only; a cache entry does not pretend to be non-API ground truth—it is a short-lived memo of the same HTTP-backed response.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `WEATHER_HTTP_TIMEOUT` | `10` | Per-request timeout (seconds) |
| `WEATHER_CACHE_TTL_SECONDS` | `900` | Cache TTL (seconds) |
| `WEATHER_MAX_RETRIES` | `2` | Retries on transport/HTTP errors |

## Failure handling

- Timeouts and HTTP errors: segment gets `weather_availability: unavailable`, `weather_error: api_failure`, and a clear UI message—not fabricated temperatures.
- Missing or invalid coordinates: `weather_error: missing_coordinates`.
