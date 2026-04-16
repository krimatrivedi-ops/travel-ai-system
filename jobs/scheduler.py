import logging
from apscheduler.schedulers.background import BackgroundScheduler
from jobs.pricing_refresh_job import refresh_all_itinerary_prices

logger = logging.getLogger(__name__)

def start_scheduler():
    """
    Starts the background scheduler for periodic jobs.
    """
    scheduler = BackgroundScheduler()
    
    # Schedule pricing refresh every 24 hours
    scheduler.add_job(
        refresh_all_itinerary_prices, 
        'interval', 
        hours=24,
        id='pricing_refresh_job',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Scheduler started: pricing_refresh_job scheduled every 24 hours.")
    return scheduler
