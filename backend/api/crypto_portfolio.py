"""
Crypto Portfolio API — Phase 3
--------------------------------
Portfolio state, trade history, and bot control endpoints.

GET  /api/v1/crypto/portfolio/summary    → current positions + P&L
GET  /api/v1/crypto/portfolio/trades     → trade history
GET  /api/v1/crypto/portfolio/stats      → overall performance stats
POST /api/v1/crypto/bot/start            → start the bot
POST /api/v1/crypto/bot/stop             → pause the bot
POST /api/v1/crypto/bot/resume           → resume after stop-loss review
POST /api/v1/crypto/bot/mode/{mode}      → switch paper/live
GET  /api/v1/crypto/bot/status           → full bot status
POST /api/v1/crypto/bot/cycle            → manually trigger one cycle (for testing)
POST /api/v1/crypto/bot/settings         → update bot config
"""

from datetime import datetime
from typing import Literal, Optional
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.portfolio_guard import (
    get_bot_settings,
    update_bot_settings,
    calculate_portfolio_value,
)
from services.crypto_paper_trader import get_trade_history
from services.crypto_bot_engine import run_bot_cycle
from services.timing_advisor import get_daily_timing_advisory
from models.crypto_models import TradeMemory
from db.database import async_session
from sqlalchemy import select

logger = structlog.get_logger()
router = APIRouter()


def _ok(data: object) -> dict:
    return {"success": True, "data": data, "error": None, "timestamp": datetime.utcnow().isoformat()}


def _err(msg: str) -> dict:
    return {"success": False, "data": None, "error": msg, "timestamp": datetime.utcnow().isoformat()}


# ─── Portfolio Endpoints ────────────────────────────────────────────────────────

@router.get("/portfolio/summary")
async def portfolio_summary():
    """
    GET /api/v1/crypto/portfolio/summary
    Returns live portfolio value with all open positions priced at current market.
    """
    settings = await get_bot_settings()
    portfolio = await calculate_portfolio_value(settings.mode)
    return _ok({
        "mode": settings.mode,
        "is_running": settings.is_running,
        "is_stopped_by_loss": settings.is_stopped_by_loss,
        "starting_capital_inr": float(settings.portfolio_capital_inr),
        **portfolio,
    })


@router.get("/portfolio/trades")
async def trade_history(limit: int = 50):
    """
    GET /api/v1/crypto/portfolio/trades?limit=50
    Returns closed trade history, newest first.
    """
    settings = await get_bot_settings()
    trades = await get_trade_history(mode=settings.mode, limit=limit)
    return _ok({"trades": trades, "count": len(trades)})


@router.get("/portfolio/stats")
async def portfolio_stats():
    """
    GET /api/v1/crypto/portfolio/stats
    Aggregate performance: win rate, avg P&L, best/worst trade.
    """
    settings = await get_bot_settings()
    trades = await get_trade_history(mode=settings.mode, limit=1000)

    if not trades:
        return _ok({
            "total_trades": 0,
            "win_rate_pct": 0,
            "avg_pnl_pct": 0,
            "total_pnl_inr": 0,
            "best_trade": None,
            "worst_trade": None,
        })

    wins = [t for t in trades if t["pnl_inr"] > 0]
    losses = [t for t in trades if t["pnl_inr"] < 0]
    total_pnl = sum(t["pnl_inr"] for t in trades)
    avg_pnl_pct = sum(t["pnl_pct"] for t in trades) / len(trades)

    best = max(trades, key=lambda t: t["pnl_pct"])
    worst = min(trades, key=lambda t: t["pnl_pct"])

    return _ok({
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1),
        "avg_pnl_pct": round(avg_pnl_pct, 2),
        "total_pnl_inr": round(total_pnl, 2),
        "best_trade": best,
        "worst_trade": worst,
        "graduation_check": {
            "target_pct": float(settings.graduation_target_percent),
            "ready": settings.graduation_ready,
            "consecutive_profitable_weeks": settings.consecutive_profitable_weeks,
        },
    })


# ─── Bot Control Endpoints ──────────────────────────────────────────────────────

@router.get("/bot/status")
async def bot_status():
    """
    GET /api/v1/crypto/bot/status
    Full bot configuration and current state.
    """
    settings = await get_bot_settings()
    return _ok({
        "mode": settings.mode,
        "is_running": settings.is_running,
        "is_stopped_by_loss": settings.is_stopped_by_loss,
        "stop_loss_triggered_at": (
            settings.stop_loss_triggered_at.isoformat()
            if settings.stop_loss_triggered_at else None
        ),
        "portfolio_capital_inr": float(settings.portfolio_capital_inr),
        "stop_loss_percent": float(settings.stop_loss_percent),
        "per_position_stop_loss_percent": float(settings.per_position_stop_loss_percent),
        "capital_reserve_percent": float(settings.capital_reserve_percent),
        "max_position_size_percent": float(settings.max_position_size_percent),
        "max_simultaneous_positions": settings.max_simultaneous_positions,
        "trading_hours": f"{settings.trading_start_hour}:00–{settings.trading_end_hour}:00 IST",
        "graduation_ready": settings.graduation_ready,
        "consecutive_profitable_weeks": settings.consecutive_profitable_weeks,
    })


@router.post("/bot/start")
async def start_bot():
    """POST /api/v1/crypto/bot/start — Start the bot trading loop."""
    settings = await get_bot_settings()
    if settings.is_stopped_by_loss:
        return _err("Bot was stopped by a loss breach. Review and use /bot/resume to restart.")
    if settings.is_running:
        return _ok({"message": "Bot is already running"})
    await update_bot_settings(is_running=True)
    logger.info("bot_started")
    return _ok({"message": "Bot started", "mode": settings.mode})


@router.post("/bot/stop")
async def stop_bot():
    """POST /api/v1/crypto/bot/stop — Pause the bot (doesn't close positions)."""
    await update_bot_settings(is_running=False)
    logger.info("bot_stopped_manually")
    return _ok({"message": "Bot paused. Open positions remain open."})


@router.post("/bot/resume")
async def resume_bot():
    """
    POST /api/v1/crypto/bot/resume
    Resume after a stop-loss breach. Clears the stopped state and restarts.
    Only callable after manual review.
    """
    settings = await get_bot_settings()
    if not settings.is_stopped_by_loss:
        return _err("Bot was not stopped by a loss breach — use /bot/start instead.")
    await update_bot_settings(
        is_running=True,
        is_stopped_by_loss=False,
        stop_loss_triggered_at=None,
    )
    logger.info("bot_resumed_after_loss_review")
    return _ok({"message": "Bot resumed after manual review. Trading restarted."})


@router.post("/bot/mode/{mode}")
async def switch_mode(mode: Literal["paper", "live"]):
    """
    POST /api/v1/crypto/bot/mode/paper  or  /api/v1/crypto/bot/mode/live
    Switch between paper trading and live trading.
    Bot must be stopped before switching modes.
    """
    settings = await get_bot_settings()
    if settings.is_running:
        return _err("Stop the bot before switching modes.")
    if mode == "live" and not settings.graduation_ready:
        return _err(
            f"Bot is not graduation-ready yet. It must achieve >{settings.graduation_target_percent}% "
            "profit consistently in paper mode before switching to live."
        )
    await update_bot_settings(mode=mode)
    return _ok({"message": f"Switched to {mode} trading mode.", "mode": mode})


@router.post("/bot/cycle")
async def trigger_cycle():
    """
    POST /api/v1/crypto/bot/cycle
    Manually trigger one bot cycle (for testing without waiting for Celery).
    The bot does NOT need to be in 'running' state for this.
    """
    settings = await get_bot_settings()
    # Temporarily allow manual trigger even if bot is stopped
    was_running = settings.is_running
    was_stopped = settings.is_stopped_by_loss

    if not was_running:
        await update_bot_settings(is_running=True, is_stopped_by_loss=False)

    try:
        result = await run_bot_cycle(mode=settings.mode)
    finally:
        if not was_running:
            await update_bot_settings(is_running=was_running, is_stopped_by_loss=was_stopped)

    return _ok(result)


class BotSettingsUpdate(BaseModel):
    portfolio_capital_inr: Optional[float] = None
    stop_loss_percent: Optional[float] = None
    trading_start_hour: Optional[int] = None
    trading_end_hour: Optional[int] = None
    max_simultaneous_positions: Optional[int] = None
    capital_reserve_percent: Optional[float] = None


@router.post("/bot/settings")
async def update_settings(body: BotSettingsUpdate):
    """
    POST /api/v1/crypto/bot/settings
    Update bot configuration. Only non-null fields are updated.
    """
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return _err("No fields provided to update.")
    await update_bot_settings(**updates)
    settings = await get_bot_settings()
    return _ok({"message": "Settings updated", "updated_fields": list(updates.keys())})


@router.get("/bot/timing-advisory")
async def timing_advisory():
    """
    GET /api/v1/crypto/bot/timing-advisory
    Returns the daily trading timing advisory report (markdown format).
    """
    advisory = await get_daily_timing_advisory()
    return _ok({"advisory": advisory})


@router.get("/trades/{trade_id}/memory")
async def get_trade_memory(trade_id: int):
    """
    GET /api/v1/crypto/trades/{trade_id}/memory
    Retrieves the trade memory / AI explanation for a given closed trade.
    """
    async with async_session() as session:
        stmt = select(TradeMemory).where(TradeMemory.trade_id == trade_id)
        result = await session.execute(stmt)
        mem = result.scalar_one_or_none()

    if not mem:
        raise HTTPException(status_code=404, detail="Trade memory not found for this trade ID")

    return _ok({
        "trade_id": mem.trade_id,
        "symbol": mem.symbol,
        "strategy_used": mem.strategy_used,
        "outcome": mem.outcome,
        "pnl_percent": float(mem.pnl_percent or 0),
        "holding_duration_minutes": mem.holding_duration_minutes,
        "indicators_at_entry": mem.indicators_at_entry,
        "market_conditions": mem.market_conditions,
        "what_worked": mem.what_worked,
        "what_failed": mem.what_failed,
        "lesson": mem.lesson,
        "avoid_pattern": mem.avoid_pattern,
    })
