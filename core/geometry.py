import math
from typing import Tuple

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on the Earth
    in kilometers.
    """
    R = 6371.0  # Earth radius in km

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c

    return distance

def estimate_travel_time(distance_km: float, mode: str = "taxi") -> int:
    """
    Estimate travel time in minutes based on distance and mode.
    Modes: walking (5 km/h), auto/taxi (25-35 km/h)
    """
    if mode == "walking":
        speed = 5.0
    else:
        # Default to auto/taxi (average 30 km/h)
        speed = 30.0
    
    time_hours = distance_km / speed
    return int(time_hours * 60)
