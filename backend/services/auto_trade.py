import asyncio
from datetime import datetime
import pytz
from sqlalchemy import select
from db.database import async_session
from models.db_models import TradingSettings, UserPortfolio
from services.signal_engine import calculate_signals
from services.broker import place_simulated_order
from services.data_ingestion import fetch_etf_price
import structlog

logger = structlog.get_logger()
IST = pytz.timezone('Asia/Kolkata')

def is_market_open():
    """Check if the Indian stock market is currently open."""
    now = datetime.now(IST)
    # Weekends (5 = Sat, 6 = Sun)
    if now.weekday() >= 5:
        return False
    
    # 9:15 AM to 3:30 PM IST
    start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
    end_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    return start_time <= now <= end_time

async def execute_auto_trades():
    """
    Main background loop for auto-trading.
    Checks all enabled ETFs and executes trades if signals align.
    """
    if not is_market_open():
        logger.info("market_closed", reason="Outside NSE hours")
        return

    async with async_session() as session:
        # Get all ETFs with auto-trade enabled
        stmt = select(TradingSettings).where(TradingSettings.auto_trade_enabled == True)
        result = await session.execute(stmt)
        enabled_etfs = result.scalars().all()

        if not enabled_etfs:
            logger.info("auto_trade_idle", reason="No ETFs enabled for auto-trading")
            return

        for settings in enabled_etfs:
            try:
                symbol = settings.symbol
                logger.info("processing_auto_trade", symbol=symbol)

                # 1. Get latest signal
                signal = await calculate_signals(symbol)
                
                # 2. Get latest price (simulated live)
                price_data = await fetch_etf_price(symbol, use_cache=True)
                current_price = float(price_data.price)

                # 3. Decision Logic
                if signal.signal_type == "BUY":
                    # Check if we already have a position to avoid double-buying
                    # In a real app, this would be more complex (position sizing)
                    stmt_pos = select(UserPortfolio).where(UserPortfolio.user_id == "demo_user", UserPortfolio.symbol == symbol)
                    pos_result = await session.execute(stmt_pos)
                    existing_pos = pos_result.scalar_one_or_none()

                    if not existing_pos:
                        # Calculate quantity based on max_position_size
                        max_cash = float(settings.max_position_size)
                        quantity = int(max_cash // current_price)
                        
                        if quantity > 0:
                            logger.info("executing_auto_buy", symbol=symbol, qty=quantity, price=current_price)
                            await place_simulated_order(
                                user_id="demo_user",
                                symbol=symbol,
                                quantity=quantity,
                                price=current_price,
                                side="BUY"
                            )
                        else:
                            logger.warn("insufficient_funds_for_min_qty", symbol=symbol)
                
                elif signal.signal_type == "AVOID" or signal.signal_type == "SELL":
                    # Exit position if signal turns sour
                    stmt_pos = select(UserPortfolio).where(UserPortfolio.user_id == "demo_user", UserPortfolio.symbol == symbol)
                    pos_result = await session.execute(stmt_pos)
                    existing_pos = pos_result.scalar_one_or_none()

                    if existing_pos:
                        logger.info("executing_auto_sell_exit", symbol=symbol, qty=float(existing_pos.quantity))
                        await place_simulated_order(
                            user_id="demo_user",
                            symbol=symbol,
                            quantity=float(existing_pos.quantity),
                            price=current_price,
                            side="SELL"
                        )

            except Exception as e:
                logger.error("auto_trade_execution_failed", symbol=settings.symbol, error=str(e))

async def toggle_auto_trade(symbol: str, enabled: bool):
    """Enable or disable auto-trading for a specific ETF."""
    async with async_session() as session:
        stmt = select(TradingSettings).where(TradingSettings.symbol == symbol)
        result = await session.execute(stmt)
        settings = result.scalar_one_or_none()

        if settings:
            settings.auto_trade_enabled = enabled
        else:
            settings = TradingSettings(symbol=symbol, auto_trade_enabled=enabled)
            session.add(settings)
            
        await session.commit()
        return {"success": True, "symbol": symbol, "auto_trade_enabled": enabled}

async def get_trading_settings():
    """Retrieve all trading settings."""
    async with async_session() as session:
        stmt = select(TradingSettings)
        result = await session.execute(stmt)
        return result.scalars().all()
