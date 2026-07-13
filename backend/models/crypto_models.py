"""
Crypto Bot DB Models
--------------------
All crypto-specific tables. ETF tables (db_models.py) are left untouched.
These tables share the same TimescaleDB instance as the ETF platform.
"""

from sqlalchemy import (
    Column, String, Numeric, Integer, BigInteger,
    DateTime, Boolean, Text, JSON, Index, ForeignKey
)
from sqlalchemy.sql import func
from db.database import Base


class CryptoCoin(Base):
    """
    Registry of tracked coins — top 10 by market cap, auto-refreshed weekly.
    Stablecoins (USDT, USDC, DAI, etc.) are excluded automatically.
    """
    __tablename__ = "crypto_coins"

    id = Column(Integer, primary_key=True)
    coingecko_id = Column(String(100), nullable=False, unique=True, index=True)  # e.g. "bitcoin"
    symbol = Column(String(20), nullable=False, index=True)                       # e.g. "BTC"
    name = Column(String(100), nullable=False)                                    # e.g. "Bitcoin"
    rank = Column(Integer, nullable=False)                                         # 1 = largest market cap
    market_cap_usd = Column(Numeric(precision=20, scale=2))
    current_price_inr = Column(Numeric(precision=20, scale=8))
    is_active = Column(Boolean, default=True)                                      # False = dropped out of top 10
    last_price_update = Column(DateTime(timezone=True))
    last_rank_update = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CryptoPriceHistory(Base):
    """
    OHLCV price history for each tracked coin.
    Stored as a TimescaleDB hypertable for efficient time-series queries.
    """
    __tablename__ = "crypto_price_history"

    id = Column(BigInteger, primary_key=True)
    coin_id = Column(Integer, ForeignKey("crypto_coins.id"), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    open = Column(Numeric(precision=20, scale=8), nullable=False)
    high = Column(Numeric(precision=20, scale=8), nullable=False)
    low = Column(Numeric(precision=20, scale=8), nullable=False)
    close = Column(Numeric(precision=20, scale=8), nullable=False)
    volume = Column(Numeric(precision=30, scale=8), nullable=False)
    interval = Column(String(10), default="1d")  # "1d", "4h", "1h"

    __table_args__ = (
        Index("ix_crypto_price_history_symbol_ts", "symbol", "timestamp"),
    )


class CryptoPortfolio(Base):
    """
    Open positions — one row per coin held.
    mode='paper' → paper trading | mode='live' → real money on CoinDCX
    """
    __tablename__ = "crypto_portfolio"

    id = Column(Integer, primary_key=True)
    mode = Column(String(10), nullable=False, default="paper")  # "paper" | "live"
    coin_id = Column(Integer, ForeignKey("crypto_coins.id"), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    quantity = Column(Numeric(precision=20, scale=10), nullable=False)
    avg_buy_price_inr = Column(Numeric(precision=20, scale=8), nullable=False)
    total_invested_inr = Column(Numeric(precision=16, scale=2), nullable=False)
    stop_loss_price_inr = Column(Numeric(precision=20, scale=8))                 # Hard stop per position
    take_profit_price_inr = Column(Numeric(precision=20, scale=8))               # Take profit target price
    strategy_used = Column(String(50))
    opened_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CryptoTrade(Base):
    """
    Completed trade log — every buy and sell is recorded here.
    This is the source of truth for performance analytics and Gemini learning.
    """
    __tablename__ = "crypto_trades"

    id = Column(Integer, primary_key=True)
    mode = Column(String(10), nullable=False, default="paper")  # "paper" | "live"
    coin_id = Column(Integer, ForeignKey("crypto_coins.id"), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(4), nullable=False)                     # "BUY" | "SELL"
    quantity = Column(Numeric(precision=20, scale=10), nullable=False)
    price_inr = Column(Numeric(precision=20, scale=8), nullable=False)
    total_inr = Column(Numeric(precision=16, scale=2), nullable=False)
    strategy_used = Column(String(50))
    signal_confidence = Column(Integer)                          # 0–100 from Gemini
    stop_loss_price_inr = Column(Numeric(precision=20, scale=8))
    status = Column(String(10), default="OPEN")                  # "OPEN" | "CLOSED" | "STOPPED"
    pnl_inr = Column(Numeric(precision=16, scale=2))             # Null while open
    pnl_percent = Column(Numeric(precision=6, scale=2))          # Null while open
    close_reason = Column(String(30))                            # "PROFIT_TARGET" | "STOP_LOSS" | "MANUAL" | "SIGNAL_REVERSAL"
    gemini_pre_trade_note = Column(Text)                         # Pre-trade Gemini analysis summary
    opened_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    closed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_crypto_trades_symbol_status", "symbol", "status"),
    )


class TradeMemory(Base):
    """
    Gemini's learning ledger.
    After every trade closes, context + outcome is saved here.
    Gemini reads this before every new trade to avoid past mistakes.
    """
    __tablename__ = "trade_memory"

    id = Column(Integer, primary_key=True)
    trade_id = Column(Integer, ForeignKey("crypto_trades.id"), nullable=False, unique=True)
    coin_id = Column(Integer, ForeignKey("crypto_coins.id"), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)

    # Market context at time of trade entry
    indicators_at_entry = Column(JSON)     # {"rsi": 52, "macd": 0.01, "bollinger_pct": 0.3, ...}
    market_conditions = Column(JSON)       # {"trend": "uptrend", "volatility": "high", "hour": 14}

    strategy_used = Column(String(50))
    outcome = Column(String(10))           # "PROFIT" | "LOSS" | "BREAKEVEN"
    pnl_percent = Column(Numeric(precision=6, scale=2))
    holding_duration_minutes = Column(Integer)

    # Gemini's post-trade analysis (filled async after trade closes)
    what_worked = Column(Text)
    what_failed = Column(Text)
    lesson = Column(Text)                  # One-line lesson Gemini extracted
    avoid_pattern = Column(Text)           # Specific pattern to avoid in future

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CryptoBotSettings(Base):
    """
    Singleton bot configuration row (id=1).
    Controls everything — mode, trading hours, stop-loss thresholds, capital.
    """
    __tablename__ = "crypto_bot_settings"

    id = Column(Integer, primary_key=True, default=1)
    mode = Column(String(10), default="paper")       # "paper" | "live"
    is_running = Column(Boolean, default=False)

    # Capital config
    portfolio_capital_inr = Column(Numeric(precision=16, scale=2), default=5000.00)
    current_portfolio_value_inr = Column(Numeric(precision=16, scale=2), default=5000.00)

    # Risk config
    stop_loss_percent = Column(Numeric(precision=4, scale=2), default=5.00)         # 5% portfolio stop
    per_position_stop_loss_percent = Column(Numeric(precision=4, scale=2), default=5.00)
    capital_reserve_percent = Column(Numeric(precision=4, scale=2), default=10.00)  # Always keep 10% cash
    max_position_size_percent = Column(Numeric(precision=4, scale=2), default=40.00)# Max 40% in one coin
    max_simultaneous_positions = Column(Integer, default=3)

    # Trading hours (IST 24h)
    trading_start_hour = Column(Integer, default=9)   # 9 AM IST
    trading_end_hour = Column(Integer, default=24)    # 12 AM IST (midnight)

    # Paper→Live graduation criteria
    graduation_target_percent = Column(Numeric(precision=4, scale=2), default=5.00)
    consecutive_profitable_weeks = Column(Integer, default=0)
    graduation_ready = Column(Boolean, default=False)

    # Stop-loss breach state
    is_stopped_by_loss = Column(Boolean, default=False)
    stop_loss_triggered_at = Column(DateTime(timezone=True))

    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CryptoPortfolioSnapshot(Base):
    """
    Periodic snapshot of portfolio value for P&L charting on the dashboard.
    Captured every hour when bot is running.
    """
    __tablename__ = "crypto_portfolio_snapshots"

    id = Column(BigInteger, primary_key=True)
    mode = Column(String(10), nullable=False, default="paper")
    snapshot_time = Column(DateTime(timezone=True), nullable=False, index=True)
    total_value_inr = Column(Numeric(precision=16, scale=2), nullable=False)
    invested_inr = Column(Numeric(precision=16, scale=2), nullable=False)
    cash_inr = Column(Numeric(precision=16, scale=2), nullable=False)
    unrealized_pnl_inr = Column(Numeric(precision=16, scale=2), default=0.00)
    realized_pnl_inr = Column(Numeric(precision=16, scale=2), default=0.00)
    open_positions = Column(Integer, default=0)
    daily_return_percent = Column(Numeric(precision=6, scale=2))
