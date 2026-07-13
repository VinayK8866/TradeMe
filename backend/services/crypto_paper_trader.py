"""
Crypto Paper Trader — Trade Execution
---------------------------------------
Executes paper trades (simulated orders) using live CoinGecko prices.
Manages position opening, closing, stop-loss exits, and P&L tracking.

Capital allocation logic:
  - Confidence 80–100% → up to 40% of total portfolio
  - Confidence 60–79%  → up to 25% of total portfolio
  - Confidence 40–59%  → up to 15% of total portfolio
  - Max 3 positions simultaneously
  - Always keep 10% as cash reserve
  - Never put more than 40% in a single coin
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import structlog

from sqlalchemy import select, update, delete
from db.database import async_session
from models.crypto_models import (
    CryptoCoin, CryptoPortfolio, CryptoTrade, TradeMemory, CryptoBotSettings
)
from services.crypto_data import get_current_prices
from services.portfolio_guard import get_bot_settings, calculate_portfolio_value

logger = structlog.get_logger()


# ─── Capital Allocation ──────────────────────────────────────────────────────────

def calculate_position_size(
    confidence: int,
    total_capital: float,
    available_cash: float,
    max_position_pct: float = 40.0,
) -> float:
    """
    Determine INR amount to allocate to a new position based on signal confidence.
    Never exceeds available_cash or max_position_pct of total_capital.
    """
    if confidence >= 80:
        target_pct = min(40.0, max_position_pct)
    elif confidence >= 60:
        target_pct = min(25.0, max_position_pct)
    else:
        target_pct = min(15.0, max_position_pct)

    target_amount = total_capital * (target_pct / 100)
    # Never allocate more than available cash
    return min(target_amount, available_cash)


# ─── Position Checks ─────────────────────────────────────────────────────────────

async def get_open_positions(mode: str = "paper") -> list[CryptoPortfolio]:
    """Return all currently open positions for the given mode."""
    async with async_session() as session:
        stmt = select(CryptoPortfolio).where(CryptoPortfolio.mode == mode)
        result = await session.execute(stmt)
        return result.scalars().all()


async def has_position(coin_id: int, mode: str = "paper") -> bool:
    """Check if we already hold a position in this coin."""
    async with async_session() as session:
        stmt = select(CryptoPortfolio).where(
            CryptoPortfolio.coin_id == coin_id,
            CryptoPortfolio.mode == mode,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None


# ─── Trade Execution ─────────────────────────────────────────────────────────────

async def open_paper_position(
    coin: CryptoCoin,
    signal_data: dict,
    mode: str = "paper",
    entry_price: Optional[float] = None,  # Pre-fetched price (avoids extra API call)
) -> Optional[dict]:
    """
    Open a new paper trade position.

    Steps:
    1. Check we don't already hold this coin
    2. Calculate position size from confidence + available cash
    3. Get live price from CoinGecko
    4. Calculate quantity = INR_amount / price
    5. Insert CryptoPortfolio + CryptoTrade records
    6. Return trade summary

    Returns None if position cannot be opened (insufficient cash, already held, etc.)
    """
    settings = await get_bot_settings()
    portfolio = await calculate_portfolio_value(mode)

    # Guard: already holding this coin?
    if await has_position(coin.id, mode):
        logger.info("skipping_open_already_held", symbol=coin.symbol)
        return None

    # Guard: max simultaneous positions
    open_count = len(await get_open_positions(mode))
    if open_count >= settings.max_simultaneous_positions:
        logger.info("skipping_open_max_positions_reached", count=open_count, max=settings.max_simultaneous_positions)
        return None

    total_capital = float(settings.portfolio_capital_inr)
    reserve = total_capital * (float(settings.capital_reserve_percent) / 100)
    available_cash = portfolio["cash_inr"] - reserve

    if available_cash <= 0:
        logger.warning("insufficient_cash_for_trade", available=portfolio["cash_inr"], reserve=reserve)
        return None

    # Run Gemini Pre-Trade Scorer to adjust confidence & get pre-trade notes
    base_confidence = signal_data.get("confidence", 50)
    from services.gemini_brain import analyze_pre_trade
    adjusted_conf, pre_trade_note = await analyze_pre_trade(
        symbol=coin.symbol,
        strategy=signal_data.get("selected_strategy", "Unknown"),
        base_confidence=base_confidence,
        indicators=signal_data.get("indicators", {}),
        market_condition=signal_data.get("market_condition", {}),
    )

    # If confidence drops below 60%, reject the trade
    if adjusted_conf < 60:
        logger.warning(
            "trade_rejected_by_gemini_brain",
            symbol=coin.symbol,
            base_confidence=base_confidence,
            adjusted_confidence=adjusted_conf,
            reasoning=pre_trade_note,
        )
        return None

    # Calculate position size using adjusted confidence
    position_inr = calculate_position_size(
        confidence=adjusted_conf,
        total_capital=total_capital,
        available_cash=available_cash,
        max_position_pct=float(settings.max_position_size_percent),
    )

    if position_inr < 50:  # Minimum ₹50 trade
        logger.warning("position_size_too_small", amount_inr=position_inr)
        return None

    # Use pre-fetched price if provided, else fetch from CoinGecko
    if entry_price and entry_price > 0:
        current_price = entry_price
    else:
        prices = await get_current_prices([coin.coingecko_id])
        current_price = float(prices.get(coin.coingecko_id, 0))

    if current_price <= 0:
        logger.error("zero_price_abort", symbol=coin.symbol)
        return None

    quantity = position_inr / current_price
    
    # Dynamic ATR-based stop-loss capped at settings max stop-loss percent
    atr = float(signal_data.get("indicators", {}).get("atr", 0))
    max_loss_pct = float(settings.per_position_stop_loss_percent) / 100
    max_stop_loss_price = current_price * (1 - max_loss_pct)

    if atr > 0:
        # Volatility-based: Entry Price - 1.5 * ATR
        atr_stop_loss_price = current_price - (1.5 * atr)
        # Cap the loss at the max stop-loss percent (choose the higher stop price)
        stop_loss_price = max(max_stop_loss_price, atr_stop_loss_price)
    else:
        stop_loss_price = max_stop_loss_price

    # Strategy-specific Take Profit target percentages
    strategy_name = signal_data.get("selected_strategy", "")
    tp_pct_map = {
        "Momentum": 8.0,
        "Mean Reversion": 4.0,
        "Breakout": 12.0,
        "MACD": 10.0
    }
    tp_pct = tp_pct_map.get(strategy_name, 6.0)
    take_profit_price = current_price * (1 + tp_pct / 100)

    now = datetime.now(timezone.utc)

    async with async_session() as session:
        # Create portfolio position
        position = CryptoPortfolio(
            mode=mode,
            coin_id=coin.id,
            symbol=coin.symbol,
            quantity=Decimal(str(round(quantity, 8))),
            avg_buy_price_inr=Decimal(str(round(current_price, 4))),
            total_invested_inr=Decimal(str(round(position_inr, 2))),
            stop_loss_price_inr=Decimal(str(round(stop_loss_price, 4))),
            take_profit_price_inr=Decimal(str(round(take_profit_price, 4))),
            strategy_used=strategy_name,
            opened_at=now,
        )
        session.add(position)

        # Log the BUY trade
        trade = CryptoTrade(
            mode=mode,
            coin_id=coin.id,
            symbol=coin.symbol,
            side="BUY",
            quantity=Decimal(str(round(quantity, 8))),
            price_inr=Decimal(str(round(current_price, 4))),
            total_inr=Decimal(str(round(position_inr, 2))),
            strategy_used=signal_data.get("selected_strategy"),
            signal_confidence=adjusted_conf,
            stop_loss_price_inr=Decimal(str(round(stop_loss_price, 4))),
            status="OPEN",
            gemini_pre_trade_note=pre_trade_note,
            opened_at=now,
        )
        session.add(trade)
        await session.commit()
        await session.refresh(trade)

        # Write TradeMemory entry for Gemini to learn from (preserves entry context)
        memory = TradeMemory(
            trade_id=trade.id,
            coin_id=coin.id,
            symbol=coin.symbol,
            strategy_used=signal_data.get("selected_strategy"),
            indicators_at_entry=signal_data.get("indicators"),
            market_conditions=signal_data.get("market_condition"),
        )
        session.add(memory)
        await session.commit()

    result = {
        "action": "OPENED",
        "symbol": coin.symbol,
        "mode": mode,
        "trade_id": trade.id,
        "quantity": round(quantity, 8),
        "price_inr": round(current_price, 4),
        "invested_inr": round(position_inr, 2),
        "stop_loss_price_inr": round(stop_loss_price, 4),
        "strategy": signal_data.get("selected_strategy"),
        "confidence": adjusted_conf,
        "opened_at": now.isoformat(),
    }

    logger.info("paper_position_opened", **{k: v for k, v in result.items() if k not in ("opened_at",)})

    # Proactive Telegram alert
    from services.telegram_bot import send_telegram_message
    alert_text = (
        f"🟢 <b>BUY Order Executed ({mode.upper()})</b>\n\n"
        f"🪙 <b>Coin:</b> {coin.name} ({coin.symbol})\n"
        f"💵 <b>Price:</b> ₹{current_price:,.2f}\n"
        f"💰 <b>Invested:</b> ₹{position_inr:,.2f}\n"
        f"🛡️ <b>Stop Loss:</b> ₹{stop_loss_price:,.2f} (-5%)\n"
        f"🎯 <b>Strategy:</b> {signal_data.get('selected_strategy')}\n"
        f"🧠 <b>Confidence:</b> {adjusted_conf}% (Gemini Scored)\n\n"
        f"📝 <i>AI Note: {pre_trade_note}</i>"
    )
    asyncio.create_task(send_telegram_message(alert_text))

    return result


async def close_paper_position(
    coin_id: int,
    symbol: str,
    coingecko_id: str,
    mode: str = "paper",
    reason: str = "SIGNAL_REVERSAL",
) -> Optional[dict]:
    """
    Close an open paper position at current market price.

    Steps:
    1. Look up open position
    2. Get live price
    3. Calculate P&L
    4. Delete from CryptoPortfolio
    5. Update the open CryptoTrade to CLOSED
    6. Write TradeMemory entry for Gemini learning
    7. Return trade summary
    """
    async with async_session() as session:
        stmt = select(CryptoPortfolio).where(
            CryptoPortfolio.coin_id == coin_id,
            CryptoPortfolio.mode == mode,
        )
        result = await session.execute(stmt)
        position = result.scalar_one_or_none()

    if not position:
        return None

    # Live exit price
    prices = await get_current_prices([coingecko_id])
    exit_price = float(prices.get(coingecko_id, float(position.avg_buy_price_inr)))

    qty = float(position.quantity)
    entry_price = float(position.avg_buy_price_inr)
    invested = float(position.total_invested_inr)
    exit_value = qty * exit_price
    pnl_inr = exit_value - invested
    pnl_pct = (pnl_inr / invested * 100) if invested > 0 else 0
    now = datetime.now(timezone.utc)
    hold_minutes = int((now - position.opened_at.replace(tzinfo=timezone.utc)).total_seconds() / 60)

    async with async_session() as session:
        # Delete portfolio position
        await session.execute(
            delete(CryptoPortfolio).where(
                CryptoPortfolio.coin_id == coin_id,
                CryptoPortfolio.mode == mode,
            )
        )

        # Find the matching open BUY trade and close it
        stmt = select(CryptoTrade).where(
            CryptoTrade.coin_id == coin_id,
            CryptoTrade.mode == mode,
            CryptoTrade.status == "OPEN",
            CryptoTrade.side == "BUY",
        ).order_by(CryptoTrade.opened_at.desc()).limit(1)
        result = await session.execute(stmt)
        open_trade = result.scalar_one_or_none()

        if open_trade:
            open_trade.status = "CLOSED"
            open_trade.pnl_inr = Decimal(str(round(pnl_inr, 2)))
            open_trade.pnl_percent = Decimal(str(round(pnl_pct, 2)))
            open_trade.close_reason = reason
            open_trade.closed_at = now

            # Write a SELL trade record
            sell_trade = CryptoTrade(
                mode=mode,
                coin_id=coin_id,
                symbol=symbol,
                side="SELL",
                quantity=Decimal(str(round(qty, 8))),
                price_inr=Decimal(str(round(exit_price, 4))),
                total_inr=Decimal(str(round(exit_value, 2))),
                strategy_used=position.strategy_used,
                status="CLOSED",
                pnl_inr=Decimal(str(round(pnl_inr, 2))),
                pnl_percent=Decimal(str(round(pnl_pct, 2))),
                close_reason=reason,
                opened_at=now,
                closed_at=now,
            )
            session.add(sell_trade)

            # Look up existing TradeMemory record to update outcome, duration
            mem_stmt = select(TradeMemory).where(TradeMemory.trade_id == open_trade.id)
            mem_res = await session.execute(mem_stmt)
            memory = mem_res.scalar_one_or_none()

            outcome = "PROFIT" if pnl_inr > 0 else ("LOSS" if pnl_inr < 0 else "BREAKEVEN")
            if memory:
                memory.outcome = outcome
                memory.pnl_percent = Decimal(str(round(pnl_pct, 2)))
                memory.holding_duration_minutes = hold_minutes
            else:
                memory = TradeMemory(
                    trade_id=open_trade.id,
                    coin_id=coin_id,
                    symbol=symbol,
                    strategy_used=position.strategy_used,
                    outcome=outcome,
                    pnl_percent=Decimal(str(round(pnl_pct, 2))),
                    holding_duration_minutes=hold_minutes,
                )
                session.add(memory)

            await session.commit()

            # Trigger Celery background task for post-trade AI analysis
            try:
                from tasks.scheduler import analyze_closed_trade
                analyze_closed_trade.delay(open_trade.id)
                logger.info("triggered_post_trade_analysis_task", trade_id=open_trade.id)
            except Exception as cel_err:
                logger.error("failed_to_trigger_celery_analysis", trade_id=open_trade.id, error=str(cel_err))

    result_data = {
        "action": "CLOSED",
        "symbol": symbol,
        "mode": mode,
        "exit_price_inr": round(exit_price, 4),
        "entry_price_inr": round(entry_price, 4),
        "quantity": round(qty, 8),
        "invested_inr": round(invested, 2),
        "exit_value_inr": round(exit_value, 2),
        "pnl_inr": round(pnl_inr, 2),
        "pnl_pct": round(pnl_pct, 2),
        "outcome": "PROFIT" if pnl_inr > 0 else ("LOSS" if pnl_inr < 0 else "BREAKEVEN"),
        "reason": reason,
        "hold_minutes": hold_minutes,
        "closed_at": now.isoformat(),
    }

    logger.info(
        "paper_position_closed",
        symbol=symbol,
        pnl_inr=round(pnl_inr, 2),
        pnl_pct=round(pnl_pct, 2),
        reason=reason,
    )

    # Proactive Telegram alert
    from services.telegram_bot import send_telegram_message
    pnl_emoji = "🟢" if pnl_inr >= 0 else "🔴"
    alert_text = (
        f"🔴 <b>SELL Order Executed ({mode.upper()})</b>\n\n"
        f"🪙 <b>Coin:</b> {symbol}\n"
        f"💵 <b>Exit Price:</b> ₹{exit_price:,.2f} (Entry: ₹{entry_price:,.2f})\n"
        f"💰 <b>Exit Value:</b> ₹{exit_value:,.2f} (Invested: ₹{invested:,.2f})\n"
        f"📊 <b>P&L:</b> {pnl_emoji} ₹{pnl_inr:,.2f} ({pnl_pct:+.2f}%)\n"
        f"⏱️ <b>Hold Duration:</b> {hold_minutes} minutes\n"
        f"🚨 <b>Reason:</b> {reason}"
    )
    asyncio.create_task(send_telegram_message(alert_text))

    return result_data


async def get_trade_history(mode: str = "paper", limit: int = 50) -> list[dict]:
    """Return recent closed trades for the dashboard."""
    async with async_session() as session:
        stmt = (
            select(CryptoTrade)
            .where(CryptoTrade.mode == mode, CryptoTrade.status == "CLOSED", CryptoTrade.side == "BUY")
            .order_by(CryptoTrade.closed_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        trades = result.scalars().all()

    return [
        {
            "id": t.id,
            "symbol": t.symbol,
            "strategy": t.strategy_used,
            "pnl_inr": float(t.pnl_inr or 0),
            "pnl_pct": float(t.pnl_percent or 0),
            "outcome": "PROFIT" if (t.pnl_inr or 0) > 0 else "LOSS",
            "close_reason": t.close_reason,
            "opened_at": t.opened_at.isoformat() if t.opened_at else None,
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        }
        for t in trades
    ]
