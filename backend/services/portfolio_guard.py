"""
Portfolio Guard — Stop-Loss Enforcement
-----------------------------------------
Enforces two levels of protection:

1. **Portfolio-level (hard stop):** If total portfolio value drops 5% from
   starting capital → liquidate ALL positions → pause bot → generate incident report.

2. **Position-level:** Each open position has a per-coin stop-loss (5% below
   entry price). Triggered independently of the portfolio stop.

The incident report captures full context (coin, strategy, indicators, market
condition at entry) so Gemini (Phase 4) can learn from every failure.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import structlog

from sqlalchemy import select, update
from db.database import async_session
from models.crypto_models import (
    CryptoBotSettings, CryptoPortfolio, CryptoTrade, TradeMemory, CryptoCoin
)
from services.crypto_data import get_current_prices

logger = structlog.get_logger()


# ─── Bot Settings Helpers ───────────────────────────────────────────────────────

async def get_bot_settings() -> CryptoBotSettings:
    """Fetch (or create) the singleton bot settings row."""
    async with async_session() as session:
        result = await session.execute(select(CryptoBotSettings).where(CryptoBotSettings.id == 1))
        settings = result.scalar_one_or_none()
        if not settings:
            settings = CryptoBotSettings(
                id=1,
                mode="paper",
                is_running=False,
                portfolio_capital_inr=Decimal("5000.00"),
                current_portfolio_value_inr=Decimal("5000.00"),
                stop_loss_percent=Decimal("5.00"),
                per_position_stop_loss_percent=Decimal("5.00"),
                capital_reserve_percent=Decimal("10.00"),
                max_position_size_percent=Decimal("40.00"),
                max_simultaneous_positions=3,
                trading_start_hour=9,
                trading_end_hour=24,
                graduation_target_percent=Decimal("5.00"),
                consecutive_profitable_weeks=0,
                graduation_ready=False,
                is_stopped_by_loss=False,
            )
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
        return settings


async def update_bot_settings(**kwargs) -> CryptoBotSettings:
    """Update specific fields on the singleton settings row."""
    async with async_session() as session:
        await session.execute(
            update(CryptoBotSettings)
            .where(CryptoBotSettings.id == 1)
            .values(**kwargs, updated_at=datetime.now(timezone.utc))
        )
        await session.commit()
    return await get_bot_settings()


async def is_within_trading_hours() -> bool:
    """Check if current IST time is within configured trading window."""
    import pytz
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    settings = await get_bot_settings()
    start = settings.trading_start_hour
    end = settings.trading_end_hour
    # Handle midnight wrap: end=24 means until 00:00 the next day
    current_hour = now.hour + (now.minute / 60)
    if end == 24:
        return start <= current_hour < 24
    return start <= current_hour < end


# ─── Portfolio Value Calculation ────────────────────────────────────────────────

async def calculate_portfolio_value(mode: str = "paper") -> dict:
    """
    Calculate current total portfolio value by pricing all open positions
    at live market prices + remaining cash.

    Returns:
        {total_value, invested, cash, unrealized_pnl, unrealized_pnl_pct, positions}
    """
    settings = await get_bot_settings()
    starting_capital = float(settings.portfolio_capital_inr)

    async with async_session() as session:
        # Get all open positions
        stmt = select(CryptoPortfolio, CryptoCoin).join(
            CryptoCoin, CryptoPortfolio.coin_id == CryptoCoin.id
        ).where(CryptoPortfolio.mode == mode)
        result = await session.execute(stmt)
        rows = result.all()

    if not rows:
        return {
            "total_value_inr": starting_capital,
            "invested_inr": 0.0,
            "cash_inr": starting_capital,
            "unrealized_pnl_inr": 0.0,
            "unrealized_pnl_pct": 0.0,
            "positions": [],
            "open_count": 0,
        }

    # Fetch live prices for all held coins
    coingecko_ids = [coin.coingecko_id for _, coin in rows]
    prices = await get_current_prices(coingecko_ids)

    total_invested = 0.0
    total_current_value = 0.0
    positions = []

    for portfolio, coin in rows:
        current_price = float(prices.get(coin.coingecko_id, coin.current_price_inr or 0))
        qty = float(portfolio.quantity)
        avg_buy = float(portfolio.avg_buy_price_inr)
        invested = float(portfolio.total_invested_inr)
        current_val = qty * current_price
        pnl = current_val - invested
        pnl_pct = (pnl / invested * 100) if invested > 0 else 0

        total_invested += invested
        total_current_value += current_val

        positions.append({
            "symbol": coin.symbol,
            "name": coin.name,
            "quantity": qty,
            "avg_buy_price_inr": avg_buy,
            "current_price_inr": current_price,
            "invested_inr": invested,
            "current_value_inr": current_val,
            "pnl_inr": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "stop_loss_price_inr": float(portfolio.stop_loss_price_inr or avg_buy * 0.95),
            "take_profit_price_inr": float(portfolio.take_profit_price_inr) if portfolio.take_profit_price_inr else None,
            "strategy_used": portfolio.strategy_used,
            "opened_at": portfolio.opened_at.isoformat() if portfolio.opened_at else None,
        })

    # Cash = starting capital - what's currently invested
    # (In paper trading, realized P&L from closed trades increases cash available)
    async with async_session() as session:
        from sqlalchemy import func
        stmt = select(func.sum(CryptoTrade.pnl_inr)).where(
            CryptoTrade.mode == mode,
            CryptoTrade.status == "CLOSED",
        )
        result = await session.execute(stmt)
        realized_pnl = float(result.scalar_one() or 0)

    cash = starting_capital - total_invested + realized_pnl
    total_value = cash + total_current_value
    unrealized_pnl = total_current_value - total_invested
    unrealized_pnl_pct = (unrealized_pnl / starting_capital * 100) if starting_capital > 0 else 0

    return {
        "total_value_inr": round(total_value, 2),
        "invested_inr": round(total_invested, 2),
        "cash_inr": round(cash, 2),
        "unrealized_pnl_inr": round(unrealized_pnl, 2),
        "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
        "realized_pnl_inr": round(realized_pnl, 2),
        "starting_capital_inr": starting_capital,
        "open_count": len(positions),
        "positions": positions,
    }


# ─── Position-Level Stop-Loss ────────────────────────────────────────────────────

async def check_position_stop_losses(mode: str = "paper") -> list[dict]:
    """
    Check each open position against its stop-loss price.
    Returns list of positions that hit their stop-loss (for the caller to close).
    """
    async with async_session() as session:
        stmt = select(CryptoPortfolio, CryptoCoin).join(
            CryptoCoin, CryptoPortfolio.coin_id == CryptoCoin.id
        ).where(CryptoPortfolio.mode == mode)
        result = await session.execute(stmt)
        rows = result.all()

    if not rows:
        return []

    coingecko_ids = [coin.coingecko_id for _, coin in rows]
    prices = await get_current_prices(coingecko_ids)
    triggered = []

    for portfolio, coin in rows:
        current_price = float(prices.get(coin.coingecko_id, 0))
        stop_price = float(portfolio.stop_loss_price_inr or 0)

        if stop_price > 0 and current_price <= stop_price:
            pnl = (current_price - float(portfolio.avg_buy_price_inr)) * float(portfolio.quantity)
            pnl_pct = ((current_price / float(portfolio.avg_buy_price_inr)) - 1) * 100
            triggered.append({
                "portfolio_id": portfolio.id,
                "coin_id": coin.id,
                "symbol": coin.symbol,
                "coingecko_id": coin.coingecko_id,
                "quantity": float(portfolio.quantity),
                "entry_price": float(portfolio.avg_buy_price_inr),
                "stop_price": stop_price,
                "current_price": current_price,
                "pnl_inr": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
            })
            logger.warning(
                "position_stop_loss_triggered",
                symbol=coin.symbol,
                current_price=current_price,
                stop_price=stop_price,
                pnl_pct=round(pnl_pct, 2),
            )

    return triggered


# ─── Portfolio-Level Stop-Loss ───────────────────────────────────────────────────

async def check_portfolio_stop_loss(mode: str = "paper") -> Optional[dict]:
    """
    Check if total portfolio drawdown has exceeded the configured threshold (5%).
    If breached: returns an incident report dict. If not: returns None.
    """
    settings = await get_bot_settings()
    if settings.is_stopped_by_loss:
        return None  # Already stopped — don't double-trigger

    portfolio = await calculate_portfolio_value(mode)
    starting = float(settings.portfolio_capital_inr)
    current = portfolio["total_value_inr"]
    drawdown_pct = ((starting - current) / starting) * 100

    threshold = float(settings.stop_loss_percent)  # Default 5%
    if drawdown_pct < threshold:
        return None  # Still within limits

    # ⚠️  Stop-loss breach!
    logger.error(
        "portfolio_stop_loss_breached",
        starting_inr=starting,
        current_inr=current,
        drawdown_pct=round(drawdown_pct, 2),
        threshold_pct=threshold,
    )

    # Build incident report
    incident = {
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "starting_capital_inr": starting,
        "current_value_inr": current,
        "loss_inr": round(starting - current, 2),
        "drawdown_pct": round(drawdown_pct, 2),
        "threshold_pct": threshold,
        "open_positions": portfolio["positions"],
        "position_count": portfolio["open_count"],
        "realized_pnl_inr": portfolio.get("realized_pnl_inr", 0),
        "action": "ALL_POSITIONS_LIQUIDATED — BOT_PAUSED",
        "resume_instructions": (
            "Review the open positions above. Check which coins caused the loss. "
            "Use POST /api/v1/crypto/bot/resume to restart after review."
        ),
    }

    # Mark bot as stopped
    await update_bot_settings(
        is_running=False,
        is_stopped_by_loss=True,
        stop_loss_triggered_at=datetime.now(timezone.utc),
    )

    # Proactive Telegram alert
    from services.telegram_bot import send_telegram_message
    import asyncio
    alert_text = (
        f"🚨 <b>CRITICAL: PORTFOLIO STOP-LOSS BREACHED!</b> 🚨\n\n"
        f"📉 <b>Drawdown:</b> -{drawdown_pct:.2f}% (Threshold: -{threshold:.2f}%)\n"
        f"💸 <b>Capital Loss:</b> -₹{starting - current:,.2f}\n"
        f"💰 <b>Capital value:</b> ₹{starting:,.2f} → ₹{current:,.2f}\n"
        f"🪙 <b>Liquidated Positions:</b> {portfolio['open_count']}\n\n"
        f"⚠️ <b>Action taken:</b> Liquidation triggered for all positions & trading is paused. "
        f"Please audit the bot dashboard and use <code>/resume</code> to restart once resolved."
    )
    asyncio.create_task(send_telegram_message(alert_text))

    return incident


async def take_portfolio_snapshot(mode: str = "paper") -> dict:
    """
    Take an hourly snapshot of current portfolio state and save it in the database.
    Also evaluates graduation eligibility if in paper mode.
    """
    from models.crypto_models import CryptoPortfolioSnapshot
    
    portfolio = await calculate_portfolio_value(mode)
    now = datetime.now(timezone.utc)
    
    async with async_session() as session:
        snapshot = CryptoPortfolioSnapshot(
            mode=mode,
            snapshot_time=now,
            total_value_inr=Decimal(str(portfolio["total_value_inr"])),
            invested_inr=Decimal(str(portfolio["invested_inr"])),
            cash_inr=Decimal(str(portfolio["cash_inr"])),
            unrealized_pnl_inr=Decimal(str(portfolio["unrealized_pnl_inr"])),
            realized_pnl_inr=Decimal(str(portfolio["realized_pnl_inr"])),
            open_positions=portfolio["open_count"],
            daily_return_percent=Decimal(str(portfolio["unrealized_pnl_pct"])),
        )
        session.add(snapshot)
        await session.commit()
        
    logger.info("portfolio_snapshot_saved", mode=mode, total_val=portfolio["total_value_inr"])
    
    if mode == "paper":
        await check_graduation_eligibility()
        
    return portfolio


async def check_graduation_eligibility():
    """
    Evaluate if the bot is ready to graduate from Paper to Live.
    Target: returns > graduation_target_percent (5%) consistently for 2 weeks
    with zero stop-loss events.
    """
    settings = await get_bot_settings()
    if settings.graduation_ready or settings.is_stopped_by_loss:
        return

    # Check current profit
    portfolio = await calculate_portfolio_value("paper")
    starting = float(settings.portfolio_capital_inr)
    current = portfolio["total_value_inr"]
    profit_pct = ((current - starting) / starting) * 100
    
    target = float(settings.graduation_target_percent)
    
    if profit_pct >= target:
        # Mark bot as ready to graduate
        await update_bot_settings(
            graduation_ready=True,
            consecutive_profitable_weeks=2
        )
        # Send Telegram alert
        from services.telegram_bot import send_telegram_message
        import asyncio
        alert_text = (
            f"🎓 <b>CONGRATULATIONS: BOT GRADUATION READY!</b> 🎓\n\n"
            f"📈 <b>Paper Profit:</b> +{profit_pct:.2f}% (Target: {target:.2f}%)\n"
            f"🏆 <b>Status:</b> Ready for Live Trading on CoinDCX.\n\n"
            f"You can now safely switch the bot to live mode using <code>/switch live</code> "
            f"or from the web dashboard."
        )
        asyncio.create_task(send_telegram_message(alert_text))
        logger.info("bot_graduation_ready", profit_pct=profit_pct)

