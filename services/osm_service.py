import time
import requests
from typing import List, Dict, Any, Optional, Tuple

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "TravelAI-POC/1.0 (https://github.com/travel-ai-poc)"

# Public Overpass mirrors (504s are common on a single instance).
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)


def _nominatim_center(location: str) -> Optional[Tuple[float, float]]:
    """Resolve a place name to lat/lon for fallback around-queries."""
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={"q": location, "format": "json", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"Nominatim error for {location!r}: {e}")
        return None


def _normalize_pois_from_elements(
    elements: List[Dict[str, Any]], *, max_pois: int = 20
) -> List[Dict[str, Any]]:
    pois: List[Dict[str, Any]] = []
    seen_names: set = set()
    for element in elements:
        tags = element.get("tags", {})
        name = tags.get("name")
        if not name or name in seen_names:
            continue
        poi_type = tags.get("tourism") or tags.get("historic") or tags.get("amenity") or "point_of_interest"
        lat = element.get("lat")
        lon = element.get("lon")
        if lat is None or lon is None:
            continue
        pois.append(
            {
                "name": name,
                "type": poi_type,
                "lat": str(lat),
                "lon": str(lon),
            }
        )
        seen_names.add(name)
        if len(pois) >= max_pois:
            break
    return pois


def _overpass_post(query: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    POST to Overpass mirrors with retries on 502/503/504.
    Returns (elements, status): status is ok | timeout | http_error.
    """
    last_err = "http_error"
    for url in OVERPASS_URLS:
        for attempt in range(2):
            try:
                r = requests.post(
                    url,
                    data={"data": query},
                    timeout=90,
                    headers={"User-Agent": USER_AGENT},
                )
                if r.status_code in (502, 503, 504):
                    last_err = "timeout"
                    time.sleep(1.2 * (attempt + 1))
                    continue
                r.raise_for_status()
                data = r.json()
                return data.get("elements", []), "ok"
            except requests.exceptions.Timeout:
                last_err = "timeout"
                time.sleep(1.0 * (attempt + 1))
            except requests.exceptions.HTTPError as e:
                code = e.response.status_code if e.response is not None else 0
                if code in (502, 503, 504):
                    last_err = "timeout"
                    time.sleep(1.0 * (attempt + 1))
                else:
                    last_err = "http_error"
            except Exception as e:
                print(f"Overpass request error ({url}): {e}")
                last_err = "http_error"
    return [], last_err


def _query_area(location: str) -> Tuple[List[Dict[str, Any]], str]:
    query = f"""
    [out:json][timeout:25];
    area[name="{location}"]->.searchArea;
    (
      node["tourism"](area.searchArea);
      way["tourism"](area.searchArea);
      node["amenity"="restaurant"](area.searchArea);
      node["amenity"="cafe"](area.searchArea);
    );
    out body;
    >;
    out skel qt;
    """
    return _overpass_post(query)


def _query_around_full(lat: float, lon: float, radius_m: int) -> Tuple[List[Dict[str, Any]], str]:
    query = f"""
    [out:json][timeout:25];
    (
      node["tourism"](around:{radius_m},{lat},{lon});
      way["tourism"](around:{radius_m},{lat},{lon});
      node["amenity"="restaurant"](around:{radius_m},{lat},{lon});
      node["amenity"="cafe"](around:{radius_m},{lat},{lon});
    );
    out body;
    >;
    out skel qt;
    """
    return _overpass_post(query)


def _query_around_lite(lat: float, lon: float, radius_m: int) -> Tuple[List[Dict[str, Any]], str]:
    """Nodes only — lighter load, fewer timeouts."""
    query = f"""
    [out:json][timeout:20];
    (
      node["tourism"](around:{radius_m},{lat},{lon});
      node["amenity"="restaurant"](around:{radius_m},{lat},{lon});
      node["amenity"="cafe"](around:{radius_m},{lat},{lon});
    );
    out body;
    """
    return _overpass_post(query)


def fetch_pois(location: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    Returns (pois, status):
    - ok: at least one POI
    - empty: succeeded but no POIs (wrong area name / sparse data)
    - timeout: 504/timeout after retries (public Overpass busy)
    - error: other HTTP/network issues
    """
    loc = location.strip()
    if not loc:
        return [], "empty"

    last_status = "ok"

    el, st = _query_area(loc)
    if st != "ok":
        last_status = st
    pois = _normalize_pois_from_elements(el)
    if pois:
        return pois, "ok"

    center = _nominatim_center(loc)
    if not center:
        return [], "empty" if last_status == "ok" else last_status

    lat, lon = center

    for radius in (15000, 28000, 45000):
        el, st = _query_around_lite(lat, lon, radius)
        if st != "ok":
            last_status = st
        pois = _normalize_pois_from_elements(el)
        if pois:
            return pois, "ok"

    el, st = _query_around_full(lat, lon, 25000)
    if st != "ok":
        last_status = st
    pois = _normalize_pois_from_elements(el)
    if pois:
        return pois, "ok"

    el, st = _query_around_full(lat, lon, 45000)
    if st != "ok":
        last_status = st
    pois = _normalize_pois_from_elements(el)
    if pois:
        return pois, "ok"

    if last_status in ("timeout", "http_error"):
        return [], last_status
    return [], "empty"


def fetch_restaurants(location: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    Specifically fetch restaurants and cafes for optimization.
    """
    loc = location.strip()
    if not loc:
        return [], "empty"

    query = f"""
    [out:json][timeout:25];
    area[name="{loc}"]->.searchArea;
    (
      node["amenity"="restaurant"](area.searchArea);
      node["amenity"="cafe"](area.searchArea);
    );
    out body;
    """
    el, st = _overpass_post(query)
    
    # If area query fails or is empty, try around Nominatim center
    if not el or st != "ok":
        center = _nominatim_center(loc)
        if center:
            lat, lon = center
            query = f"""
            [out:json][timeout:25];
            (
              node["amenity"="restaurant"](around:5000,{lat},{lon});
              node["amenity"="cafe"](around:5000,{lat},{lon});
            );
            out body;
            """
            el, st = _overpass_post(query)
            
    pois = _normalize_pois_from_elements(el)
    
    # Add some mock review data if missing, as OptimizationAgent expects it
    for poi in pois:
        poi["reviews"] = [
            f"Great place for local food!",
            f"Amazing vibe and friendly staff.",
            f"Highly recommend their signature dish."
        ]
        poi["rating"] = 4.2 # Placeholder
        poi["price_level"] = 2 # Placeholder
        
    return pois, st


def geocode_place_candidate(
    name: str, location_hint: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Resolve a free-text place name via Nominatim when OSM candidate lists do not match.
    Used on optimize/apply so we never substitute an unrelated POI.
    """
    q = (name or "").strip()
    if not q:
        return None
    hint = (location_hint or "").strip()
    if hint:
        q = f"{q}, {hint}"
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={"q": q, "format": "json", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        row = data[0]
        lat = float(row["lat"])
        lon = float(row["lon"])
        return {
            "name": name.strip(),
            "type": "point_of_interest",
            "lat": str(lat),
            "lon": str(lon),
            "reviews": [
                "Verified via geocoding; confirm hours and access before visiting.",
                "Popular with visitors; allow time to explore.",
            ],
            "rating": 4.2,
            "price_level": 2,
        }
    except Exception as e:
        print(f"Nominatim geocode error for {name!r}: {e}")
        return None


def fetch_unified_optimization_pois(location: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    Broad OSM pool: tourism, historic sites, dining, and leisure — not routed by user keywords.
    """
    loc = location.strip()
    if not loc:
        return [], "empty"

    query = f"""
    [out:json][timeout:30];
    area[name="{loc}"]->.searchArea;
    (
      node["tourism"](area.searchArea);
      node["historic"](area.searchArea);
      node["amenity"="restaurant"](area.searchArea);
      node["amenity"="cafe"](area.searchArea);
      node["amenity"="bar"](area.searchArea);
      node["leisure"="park"](area.searchArea);
    );
    out body;
    """
    el, st = _overpass_post(query)

    if not el or st != "ok":
        center = _nominatim_center(loc)
        if center:
            lat, lon = center
            query = f"""
            [out:json][timeout:30];
            (
              node["tourism"](around:15000,{lat},{lon});
              node["historic"](around:15000,{lat},{lon});
              node["amenity"="restaurant"](around:15000,{lat},{lon});
              node["amenity"="cafe"](around:15000,{lat},{lon});
              node["amenity"="bar"](around:15000,{lat},{lon});
              node["leisure"="park"](around:15000,{lat},{lon});
            );
            out body;
            """
            el, st = _overpass_post(query)

    pois = _normalize_pois_from_elements(el, max_pois=50)
    for poi in pois:
        if "reviews" not in poi:
            poi["reviews"] = [
                "Suggested from local OSM data; confirm details before visiting.",
                "Allow time to explore.",
            ]
            poi["rating"] = 4.2
            poi["price_level"] = 2
    return pois, st


def fetch_optimization_candidates(
    location: str, user_request: str
) -> Tuple[List[Dict[str, Any]], str, str]:
    """
    Returns (candidates, fetch_status, mode_label).
    user_request is ignored for routing; a single unified OSM fetch is used.
    mode_label is always 'unified' for API compatibility.
    """
    _ = user_request  # API compatibility; any query uses the same candidate pool
    pois, st = fetch_unified_optimization_pois(location)
    return pois, st, "unified"
