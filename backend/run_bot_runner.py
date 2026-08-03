"""
Standalone Bot Cycle Runner
---------------------------
Executes one full bot cycle (price refresh + signal scan + exit checks + trade entry).
Designed for GitHub Actions, cron jobs, or manual CLI triggers.
"""

import asyncio
import os
import sys

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import os
import sys

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.database import engine, Base
import models.crypto_models  # Ensure all ORM models are registered
import models.db_models

from services.coin_ranker import refresh_coin_prices, update_coin_rankings
from services.crypto_bot_engine import run_bot_cycle
from services.portfolio_guard import take_portfolio_snapshot, get_bot_settings, update_bot_settings


async def init_db():
    """Auto-create tables on fresh database (Neon/Supabase) and seed initial data."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Ensure bot settings exist and is_running is True for paper mode
    settings = await get_bot_settings()
    if not settings.is_running and not settings.is_stopped_by_loss:
        await update_bot_settings(is_running=True)

    # Seed top-10 coins if empty
    from db.database import async_session
    from models.crypto_models import CryptoCoin
    from sqlalchemy import select, func
    async with async_session() as session:
        res = await session.execute(select(func.count(CryptoCoin.id)))
        count = res.scalar_one()
        if count == 0:
            print("🌱 Fresh database detected. Seeding top-10 coins...")
            await update_coin_rankings(force=True)


async def main():
    print("🚀 Starting 24/7 Bot Cycle Execution...")
    
    # 0. Auto-initialize tables and seed data if fresh database
    try:
        await init_db()
    except Exception as e:
        print(f"⚠️ DB Init warning: {e}")

    # 1. Refresh live coin prices
    try:
        updated = await refresh_coin_prices()
        print(f"✅ Refreshed price data for {updated} coins.")
    except Exception as e:
        print(f"⚠️ Price refresh warning: {e}")

    # 2. Run bot trading cycle (signals + stop-loss + exits + entries)
    summary = await run_bot_cycle(mode="paper")
    print(f"📊 Cycle Result: Mode={summary['mode']}, Opened={len(summary.get('positions_opened', []))}, Closed={len(summary.get('positions_closed', []))}")
    
    if summary.get("skipped"):
        print(f"ℹ️ Reason skipped: {summary['skipped']}")

    if summary.get("positions_closed"):
        print(f"🔴 Closed positions: {summary['positions_closed']}")

    if summary.get("positions_opened"):
        print(f"🟢 Opened positions: {summary['positions_opened']}")

    if summary.get("errors"):
        print(f"❌ Errors: {summary['errors']}")

    # 3. Take portfolio snapshot for analytics
    try:
        snap = await take_portfolio_snapshot(mode="paper")
        print(f"📈 Portfolio Value: ₹{snap['total_value_inr']}")
    except Exception as e:
        print(f"⚠️ Snapshot warning: {e}")

    print("🏁 Bot Cycle Finished Successfully.")


if __name__ == "__main__":
    asyncio.run(main())
