import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "trademe_tasks",
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
    # ── ETF Tasks (existing) ──────────────────────────────────────────────────
    "poll-etf-prices-every-5-minutes": {
        "task": "tasks.scheduler.poll_prices",
        "schedule": crontab(minute="*/5"),
    },
    "auto-trade-executor-every-minute": {
        "task": "tasks.scheduler.auto_trade_executor",
        "schedule": crontab(minute="*"),
    },

    # ── Crypto Bot Tasks ──────────────────────────────────────────────────────
    # Refresh top-10 coin rankings once per week (Sunday 6 AM IST)
    "crypto-refresh-coin-rankings-weekly": {
        "task": "tasks.scheduler.crypto_refresh_rankings",
        "schedule": crontab(hour=6, minute=0, day_of_week=0),  # Sunday 6 AM
    },
    # Refresh live prices for top-10 coins every 15 minutes
    "crypto-refresh-prices-every-15-min": {
        "task": "tasks.scheduler.crypto_refresh_prices",
        "schedule": crontab(minute="*/15"),
    },
    # Take portfolio snapshot every hour for P&L charts
    "crypto-portfolio-snapshot-hourly": {
        "task": "tasks.scheduler.crypto_portfolio_snapshot",
        "schedule": crontab(minute=0),  # Every hour on the hour
    },
    # Run full bot cycle every 15 minutes (signal scan + trade execution)
    "crypto-bot-cycle-every-15-min": {
        "task": "tasks.scheduler.crypto_bot_cycle",
        "schedule": crontab(minute="*/15"),
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
    """Background task to execute automated ETF trades."""
    from services.auto_trade import execute_auto_trades
    import asyncio

    loop = asyncio.get_event_loop()
    loop.run_until_complete(execute_auto_trades())


# ── Crypto Bot Tasks ──────────────────────────────────────────────────────────

@celery_app.task
def crypto_refresh_rankings():
    """Weekly task: refresh top-10 coin list from CoinGecko."""
    from services.coin_ranker import update_coin_rankings
    import asyncio

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(update_coin_rankings(force=True))
    print(f"[crypto_refresh_rankings] {result}")


@celery_app.task
def crypto_refresh_prices():
    """Every 15 min: update live INR prices for all tracked coins."""
    from services.coin_ranker import refresh_coin_prices
    import asyncio

    loop = asyncio.get_event_loop()
    count = loop.run_until_complete(refresh_coin_prices())
    print(f"[crypto_refresh_prices] Updated {count} coins")


@celery_app.task
def crypto_portfolio_snapshot():
    """Hourly: save portfolio value snapshot for P&L chart."""
    from services.portfolio_guard import take_portfolio_snapshot
    import asyncio

    loop = asyncio.get_event_loop()
    portfolio = loop.run_until_complete(take_portfolio_snapshot(mode="paper"))
    print(f"[crypto_portfolio_snapshot] Captured snapshot — Value: ₹{portfolio['total_value_inr']}")


@celery_app.task
def crypto_scan_signals():
    """Every 15 min: run signal engine for all top-10 coins and cache results."""
    from services.crypto_signal_engine import calculate_all_signals
    import asyncio

    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(calculate_all_signals())
    buys = [r for r in results if r["signal"] == "BUY"]
    print(f"[crypto_scan_signals] Scanned {len(results)} coins — {len(buys)} BUY signals")


@celery_app.task
def crypto_bot_cycle():
    """Every 15 min: run full bot cycle (stop-loss checks + trade execution)."""
    from services.crypto_bot_engine import run_bot_cycle
    import asyncio

    loop = asyncio.get_event_loop()
    summary = loop.run_until_complete(run_bot_cycle(mode="paper"))
    opened = len(summary.get("positions_opened", []))
    closed = len(summary.get("positions_closed", []))
    skipped = summary.get("skipped")
    if skipped:
        print(f"[crypto_bot_cycle] Skipped: {skipped}")
    else:
        print(f"[crypto_bot_cycle] Done — opened: {opened}, closed: {closed}, errors: {len(summary.get('errors', []))}")


@celery_app.task
def analyze_closed_trade(trade_id: int):
    """Run post-trade AI analysis in the background after a trade is closed."""
    from services.gemini_brain import analyze_trade_outcome
    import asyncio

    loop = asyncio.get_event_loop()
    loop.run_until_complete(analyze_trade_outcome(trade_id))
    print(f"[analyze_closed_trade] Analyzed trade {trade_id}")

