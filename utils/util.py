import re

def clean_cost(value):
    if not isinstance(value, str):
        return 0.0
    
    # 1. Remove currency codes and commas
    value = re.sub(r'[a-zA-Z,₹]', '', value).strip()
    
    # 2. Handle ranges (e.g., "500-1500") 
    # If there's a hyphen, let's take the average (or change to [0] for min)
    if '-' in value:
        parts = value.split('-')
        try:
            return sum(float(p.strip()) for p in parts) / len(parts)
        except ValueError:
            return 0.0

    # 3. Final attempt to convert
    try:
        return float(value)
    except ValueError:
        return 0.0
    

def safe_float(val):
    try:
        # Takes "10-15 mins" -> "10" -> 10.0
        # Takes "LOW" -> raises error -> returns 0.0
        return float(str(val).split()[0].split('-')[0])
    except (ValueError, IndexError, AttributeError):
        return 0.0    