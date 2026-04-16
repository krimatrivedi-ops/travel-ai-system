import logging
from services.itinerary_store import get_all_saved_itineraries, update_saved_itinerary_bundle
from agents.pricing_agent import PricingAgent
from services.pricing_service import compute_estimated_pricing_rollups

logger = logging.getLogger(__name__)

def refresh_all_itinerary_prices():
    """
    Background job to refresh estimated pricing for all stored itineraries.
    Reuses PricingAgent logic with TTL check (force=False).
    """
    logger.info("Starting background pricing refresh job...")
    itineraries = get_all_saved_itineraries()
    
    agent = PricingAgent()
    
    updated_count = 0
    for it in itineraries:
        try:
            bundle = it["itinerary_bundle"]
            persona = it["persona_snapshot"]
            saved_id = it["id"]
            
            # Run PricingAgent to update estimates (respects 24h TTL)
            agent.run(bundle, persona, force=False)
            
            # Recompute rollups after updating estimates
            compute_estimated_pricing_rollups(bundle)
            
            # Save updated bundle
            update_saved_itinerary_bundle(saved_id, bundle)
            updated_count += 1
            
        except Exception as e:
            logger.error(f"Failed to refresh pricing for itinerary {it.get('id')}: {e}")

    logger.info(f"Background pricing refresh job completed. Processed {updated_count} itineraries.")

if __name__ == "__main__":
    # Setup basic logging if run directly
    logging.basicConfig(level=logging.INFO)
    refresh_all_itinerary_prices()
