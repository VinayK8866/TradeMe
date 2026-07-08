import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "etf_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Celery Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
)

# Periodic Tasks
celery_app.conf.beat_schedule = {
    "poll-etf-prices-every-5-minutes": {
        "task": "tasks.scheduler.poll_prices",
        "schedule": crontab(minute="*/5"), # Every 5 minutes
    },
    "auto-trade-executor-every-minute": {
        "task": "tasks.scheduler.auto_trade_executor",
        "schedule": crontab(minute="*"), # Every minute during market hours
    },
}

@celery_app.task
def poll_prices():
    """Task to poll ETF prices and signals."""
    from services.signal_engine import calculate_signals
    import asyncio
    
    TRACKED_ETFS = ["NIFTYBEES", "GOLDBEES", "ITBEES", "JUNIORBEES", "LIQUIDBEES"]
    
    async def run_polling():
        for symbol in TRACKED_ETFS:
            try:
                await calculate_signals(symbol)
            except Exception as e:
                print(f"Failed to poll {symbol}: {e}")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_polling())

@celery_app.task
def auto_trade_executor():
    """Background task to execute automated trades."""
    from services.auto_trade import execute_auto_trades
    import asyncio
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(execute_auto_trades())
