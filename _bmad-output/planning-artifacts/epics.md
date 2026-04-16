# travel-ai-system — Epic Breakdown

## Overview

Backlog for a **travel assistant** (orchestration and UX—not an omniscient “agent” that inherently knows facts). The system **does not** ship static weather tables, price lists, or hardcoded forecasts. **Weather and money values must come from live calls** to **free, reliable, documented** providers (official or community APIs with clear terms), with **caching where appropriate**—never from baked-in data masquerading as ground truth.

**Integration principles (applies to all epics below):**

- **No static weather or pricing** as the source of truth. Do not embed fixed forecasts, climates, or price lists in code or config to display as current fact.
- **Weather:** Fetch from free, reputable weather APIs (e.g. forecast/historical endpoints appropriate to trip dates and coordinates). Show **attribution**, **fetch time or validity window**, and graceful **degradation** when the API is unavailable.
- **Pricing:** Show amounts only when backed by a **response from a free, documented API** (transport, venue, currency conversion, etc.) or an **explicit, labeled** state such as “price not available from integrated sources.” If **AI/LLM** is used, it may **assist** (e.g. suggest which API to query, parse unstructured pages behind a separate integration)—it **must not** invent authoritative prices presented as fact. Any model-assisted **estimate** must be **clearly labeled** as non-official and distinct from API-backed figures.
- **Source policy:** Prefer **free tiers** with stable terms; document each integration in project config or architecture. **Reliability:** timeouts, retries, and user-visible errors—not silent fallback to fake numbers.

Enrichment is layered on top of **persisted itineraries**, **history**, **PDF export**, and **editing with a frozen preference snapshot** per trip.

## Epic List

1. **Itinerary enrichment** — Weather and pricing **via integrations** (no static truth); transparent sourcing.
2. **History and export** — Store itineraries, browse past trips, download PDFs (PDF reflects the same rules: only API-backed or clearly labeled content).
3. **Detail editing with preference memory** — Edit trips while keeping the **preference snapshot** for that itinerary; replanning still uses **APIs for facts**, not static data.

---

## Epic 1: Itinerary Enrichment (Integration-Backed)

After an itinerary exists, enrich it with **live** weather and **API-backed** pricing where possible. The assistant **asks the network** (official/free APIs); it does not “know” conditions or costs by itself.

### Story 1.1: Weather via Free Reliable APIs

As a traveler,
I want weather for each day and major stop **fetched from real services**,
So that what I see matches reality—not a static placeholder.

**Acceptance Criteria:**

- **Given** an itinerary with dates and geocodable locations,
- **When** weather is shown (after generation or on refresh),
- **Then** values come from **HTTP calls to at least one free, reliable weather API** (documented in the project), using coordinates and trip dates—not hardcoded seasonal defaults,
- **And** the UI shows **source attribution** and when data was fetched or which forecast window applies,
- **And** if the API fails or a location cannot be resolved, the user sees a **clear unavailable state**—not fabricated conditions,
- **And** optional short-lived **caching** is allowed for performance, with rules documented (TTL, invalidation)—cache is not a substitute for static fake data.

### Story 1.2: Itemized Pricing via Free APIs (No Invented Totals)

As a traveler,
I want **per-line costs only when integrations provide them**,
So that I am not shown made-up prices from a static catalog.

**Acceptance Criteria:**

- **Given** a structured itinerary (activities, legs, stays, etc.),
- **When** I view line items that can have a price,
- **Then** each amount is either **(a)** from a **documented free API response** (e.g. public transport, currency rate, a venue/aggregator we integrate), with **currency and source** visible or traceable, or **(b)** explicitly **“not available”** / **“integrate later”** with no numeric fiction,
- **And** **no hardcoded price list** in the codebase is used to populate live displays as if authoritative,
- **And** where **AI** helps (e.g. routing a query to the right API or summarizing API JSON), the **stored/displayed price** still traces to API output or remains absent—LLM output is not substituted as silent ground truth,
- **And** rollups (day/trip totals) include **only** lines with API-backed amounts, with **separate indication** for incomplete coverage.

---

## Epic 2: History and Export

Persist every generated itinerary and support browsing plus PDF download. Exported documents follow the **same non-static rules**: weather and price blocks reflect **fetched data** or honest **unavailable** states.

### Story 2.1: Persist Generated Itineraries

As a traveler,
I want each completed generation saved automatically,
So that I can return to it later without losing work.

**Acceptance Criteria:**

- **Given** a successful itinerary generation,
- **When** the system completes the run,
- **Then** the itinerary bundle, destination, dates, and snapshot of user preferences used are stored durably,
- **And** each saved record has a stable identifier,
- **And** stored enrichment (weather snapshots, API-backed prices) may be cached metadata with **timestamps and source ids**—not static placeholders passed off as live.

### Story 2.2: Past Itineraries List

As a traveler,
I want a list of my past itineraries,
So that I can reopen any trip quickly.

**Acceptance Criteria:**

- **Given** one or more saved itineraries,
- **When** I open the app or a “My trips” area,
- **Then** I see a chronological (or sortable) list with title, destination, and date range,
- **And** I can select one to open detail.

### Story 2.3: PDF Download Per Itinerary

As a traveler,
I want to download any saved itinerary as a PDF,
So that I can share or print it offline.

**Acceptance Criteria:**

- **Given** a saved itinerary,
- **When** I choose Download PDF,
- **Then** the PDF includes days and activities, and **weather/pricing sections** only as **persisted API-backed snapshots** or **explicit “unavailable”** labels—consistent with Epic 1 rules,
- **And** optional **source footnotes** for weather/price data where applicable,
- **And** the file downloads with a sensible filename.

---

## Epic 3: Detail Editing With Preference Snapshot

Editing respects the **preferences captured for that itinerary**. Factual updates (weather refresh, price re-fetch) still go through **integrations**, not static knowledge.

### Story 3.1: Itinerary Detail Add and Modify

As a traveler,
I want to add or change items when viewing an itinerary’s detail,
So that the plan matches my needs without starting over.

**Acceptance Criteria:**

- **Given** an opened itinerary (new or from history),
- **When** I edit activities, notes, times, or order,
- **Then** changes persist for that itinerary,
- **And** validation prevents obviously invalid states (e.g. overlapping hard constraints) with clear errors,
- **And** new lines that need weather or price follow the **same API-first rules** as Epic 1.

### Story 3.2: Preference Snapshot for Replanning and Edits

As a traveler,
I want the system to remember the preferences that built this itinerary,
So that AI-assisted edits and replans stay consistent with how the trip was originally scoped.

**Acceptance Criteria:**

- **Given** an itinerary with an associated preference snapshot (persona/partial_persona at generation time),
- **When** I request changes, regeneration, or replanning from detail view,
- **Then** the planner uses that snapshot as primary context (merged sensibly with explicit new instructions),
- **And** the UI surfaces which preferences are scoped to **this trip** vs global defaults,
- **And** any **refetch** of weather or prices after replanning uses **live free APIs** again, not static data,
- **And** if LLM is involved in wording or structuring the plan, **factual claims** about weather and cost remain **API-grounded** or **explicitly absent**, per Epic 1.
