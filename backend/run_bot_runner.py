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

from services.coin_ranker import refresh_coin_prices
from services.crypto_bot_engine import run_bot_cycle
from services.portfolio_guard import take_portfolio_snapshot


async def main():
    print("🚀 Starting 24/7 Bot Cycle Execution...")
    
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
