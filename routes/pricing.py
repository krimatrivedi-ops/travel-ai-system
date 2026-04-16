from fastapi import APIRouter, HTTPException
from services.itinerary_store import get_saved_itinerary, update_saved_itinerary_bundle
from agents.pricing_agent import PricingAgent
from services.pricing_service import compute_estimated_pricing_rollups

router = APIRouter()

@router.post("/itinerary/{itinerary_id}/refresh-pricing")
async def refresh_itinerary_pricing(itinerary_id: str):
    """
    On-demand refresh for estimated pricing of a specific itinerary.
    Overrides TTL (force=True).
    """
    it = get_saved_itinerary(itinerary_id)
    if not it:
        raise HTTPException(status_code=404, detail="Itinerary not found")
        
    bundle = it["itinerary_bundle"]
    persona = it["persona_snapshot"]
    
    agent = PricingAgent()
    # Force refresh regardless of TTL
    agent.run(bundle, persona, force=True)
    
    # Recompute rollups
    compute_estimated_pricing_rollups(bundle)
    
    # Save updated bundle
    try:
        update_saved_itinerary_bundle(itinerary_id, bundle)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
        
    return {
        "status": "success",
        "message": "Pricing refreshed",
        "itinerary": bundle
    }
