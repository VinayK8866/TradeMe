"""
Crypto Bot Engine — Main Orchestrator
---------------------------------------
The central coordinator that runs every 15 minutes via Celery.
Ties together: signals → position sizing → trade execution → stop-loss checks.

Execution flow per cycle:
1. Gate checks (bot running? within hours? not stopped by loss?)
2. Check position-level stop-losses → close any triggered positions
3. Check portfolio-level stop-loss → emergency stop if breach
4. Scan for new BUY signals (confidence ≥ 60%)
5. For each signal: allocate capital + open paper position
6. Log cycle summary
"""

from datetime import datetime, timezone
import structlog
import pytz

from services.portfolio_guard import (
    get_bot_settings,
    is_within_trading_hours,
    check_portfolio_stop_loss,
    check_position_stop_losses,
    calculate_portfolio_value,
)
from services.crypto_paper_trader import (
    open_paper_position,
    close_paper_position,
    get_open_positions,
)
from services.crypto_signal_engine import calculate_all_signals
from services.coin_ranker import get_coin_by_symbol

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")


async def run_bot_cycle(mode: str = "paper") -> dict:
    """
    Execute one full bot cycle. Called every 15 minutes by Celery.
    Returns a summary of what happened this cycle.
    """
    cycle_start = datetime.now(timezone.utc)
    summary = {
        "cycle_time": cycle_start.isoformat(),
        "mode": mode,
        "skipped": None,
        "positions_closed": [],
        "positions_opened": [],
        "portfolio_stop_triggered": False,
        "errors": [],
    }

    # ── Gate 1: Bot must be running ──────────────────────────────────────────────
    settings = await get_bot_settings()
    if not settings.is_running:
        summary["skipped"] = "bot_not_running"
        logger.info("bot_cycle_skipped", reason="bot_not_running")
        return summary

    # ── Gate 2: Must be within trading hours ────────────────────────────────────
    if not await is_within_trading_hours():
        summary["skipped"] = "outside_trading_hours"
        logger.info("bot_cycle_skipped", reason="outside_trading_hours")
        return summary

    # ── Gate 3: Not stopped by loss ─────────────────────────────────────────────
    if settings.is_stopped_by_loss:
        summary["skipped"] = "stopped_by_loss_breach"
        logger.info("bot_cycle_skipped", reason="stopped_by_loss")
        return summary

    logger.info("bot_cycle_starting", mode=mode)

    # ── Step 1: Check position-level stop-losses ─────────────────────────────────
    triggered_positions = await check_position_stop_losses(mode)
    for pos in triggered_positions:
        try:
            close_result = await close_paper_position(
                coin_id=pos["coin_id"],
                symbol=pos["symbol"],
                coingecko_id=pos["coingecko_id"],
                mode=mode,
                reason="STOP_LOSS",
            )
            if close_result:
                summary["positions_closed"].append({
                    **close_result,
                    "trigger": "STOP_LOSS",
                })
        except Exception as e:
            summary["errors"].append(f"Stop-loss close failed for {pos['symbol']}: {e}")
            logger.error("stop_loss_close_failed", symbol=pos["symbol"], error=str(e))

    # ── Step 2: Portfolio-level stop-loss check ──────────────────────────────────
    incident = await check_portfolio_stop_loss(mode)
    if incident:
        summary["portfolio_stop_triggered"] = True
        summary["incident_report"] = incident
        logger.error("portfolio_stop_loss_triggered", drawdown_pct=incident["drawdown_pct"])

        # Close ALL remaining open positions
        open_positions = await get_open_positions(mode)
        from services.crypto_data import get_current_prices
        from services.coin_ranker import get_tracked_coins

        # Get coingecko IDs for open positions
        from sqlalchemy import select
        from db.database import async_session
        from models.crypto_models import CryptoCoin

        for position in open_positions:
            async with async_session() as session:
                coin = await session.get(CryptoCoin, position.coin_id)
            if coin:
                try:
                    await close_paper_position(
                        coin_id=coin.id,
                        symbol=coin.symbol,
                        coingecko_id=coin.coingecko_id,
                        mode=mode,
                        reason="PORTFOLIO_STOP_LOSS",
                    )
                    summary["positions_closed"].append({"symbol": coin.symbol, "trigger": "PORTFOLIO_STOP_LOSS"})
                except Exception as e:
                    summary["errors"].append(f"Emergency close failed for {coin.symbol}: {e}")

        return summary  # Bot is now stopped — end cycle here

    # ── Step 3: Look for new BUY opportunities ───────────────────────────────────
    open_count = len(await get_open_positions(mode))
    settings = await get_bot_settings()  # Reload after potential changes
    max_positions = settings.max_simultaneous_positions

    if open_count >= max_positions:
        logger.info("bot_cycle_max_positions_held", open=open_count, max=max_positions)
        summary["skipped_new_trades"] = f"Max positions ({max_positions}) already held"
        return summary

    # Calculate signals for all coins
    try:
        all_signals = await calculate_all_signals()
    except Exception as e:
        summary["errors"].append(f"Signal scan failed: {e}")
        logger.error("signal_scan_failed", error=str(e))
        return summary

    # Filter to strong BUY signals only (≥60% confidence)
    buy_signals = [
        s for s in all_signals
        if s["signal"] == "BUY" and s["confidence"] >= 60
    ]
    buy_signals.sort(key=lambda s: -s["confidence"])  # Best confidence first

    logger.info("buy_signals_found", count=len(buy_signals))

    # ── Step 4: Open positions for qualifying signals ────────────────────────────
    for signal in buy_signals:
        # Re-check positions count (might have changed during this loop)
        open_count = len(await get_open_positions(mode))
        if open_count >= max_positions:
            break

        coin = await get_coin_by_symbol(signal["symbol"])
        if not coin:
            continue

        try:
            entry_price = signal.get("indicators", {}).get("close")
            trade_result = await open_paper_position(coin=coin, signal_data=signal, mode=mode, entry_price=entry_price)
            if trade_result:
                summary["positions_opened"].append(trade_result)
        except Exception as e:
            summary["errors"].append(f"Open position failed for {signal['symbol']}: {e}")
            logger.error("open_position_failed", symbol=signal["symbol"], error=str(e))

    # ── Cycle summary ────────────────────────────────────────────────────────────
    cycle_end = datetime.now(timezone.utc)
    summary["cycle_duration_seconds"] = round((cycle_end - cycle_start).total_seconds(), 1)

    logger.info(
        "bot_cycle_complete",
        mode=mode,
        opened=len(summary["positions_opened"]),
        closed=len(summary["positions_closed"]),
        errors=len(summary["errors"]),
        duration_s=summary["cycle_duration_seconds"],
    )
    return summary
