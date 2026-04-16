import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from core.contracts import Agent
from services.price_estimation_service import estimate_price

logger = logging.getLogger(__name__)

class PricingAgent(Agent):
    """
    PricingAgent estimates and updates pricing for itinerary segments dynamically.
    """

    def name(self) -> str:
        return "pricing_agent"

    def execute(self, input_data: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standard agent interface.
        input_data should contain 'bundle' and 'persona'.
        """
        bundle = input_data.get("bundle")
        persona = input_data.get("persona")
        force = input_data.get("force", False)
        
        if not bundle or not persona:
            logger.warning("PricingAgent: Missing bundle or persona in input_data")
            return {"bundle": bundle}
            
        self.run(bundle, persona, force=force)
        return {"bundle": bundle}

    def should_refresh(self, segment: Dict[str, Any], force: bool = False) -> bool:
        """
        Determines if the estimated pricing for a segment should be refreshed.
        """
        if force:
            return True
            
        pricing = segment.get("pricing", {})
        est_pricing = segment.get("estimated_pricing")
        
        # If trusted pricing is available (ok), we don't necessarily NEED to refresh estimate,
        # but the requirement says refresh if pricing.availability != "ok".
        if pricing.get("availability") != "ok":
            if not est_pricing:
                return True
            
            # Check TTL (24h)
            last_updated_str = est_pricing.get("last_updated_at")
            if not last_updated_str:
                return True
                
            try:
                # Handling 'Z' suffix for UTC
                if last_updated_str.endswith('Z'):
                    last_updated_str = last_updated_str[:-1] + '+00:00'
                last_updated = datetime.fromisoformat(last_updated_str)
                now = datetime.now(timezone.utc)
                if now - last_updated > timedelta(hours=24):
                    return True
            except ValueError:
                return True
                
        return False

    def run(self, bundle: Dict[str, Any], persona: Dict[str, Any], force: bool = False) -> None:
        """
        Iterates over segments and updates estimated_pricing if needed.
        Mutates bundle in place.
        """
        if not isinstance(bundle, dict) or "days" not in bundle:
            return

        updated_segments = 0
        for day in bundle.get("days", []):
            for segment in day.get("segments", []):
                if self.should_refresh(segment, force=force):
                    estimate = estimate_price(segment, persona)
                    segment["estimated_pricing"] = estimate
                    updated_segments += 1
                    
        if updated_segments > 0:
            logger.info(f"PricingAgent: Updated {updated_segments} segments (force={force})")
