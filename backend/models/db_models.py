from sqlalchemy import Column, String, Numeric, Integer, DateTime, Index, Boolean
from sqlalchemy.sql import func
from db.database import Base

class ETFPriceHistory(Base):
    __tablename__ = "etf_price_history"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    open = Column(Numeric(precision=12, scale=2), nullable=False)
    high = Column(Numeric(precision=12, scale=2), nullable=False)
    low = Column(Numeric(precision=12, scale=2), nullable=False)
    close = Column(Numeric(precision=12, scale=2), nullable=False)
    volume = Column(Integer, nullable=False)

    __table_args__ = (
        # Index for time-series queries
        Index('ix_etf_price_history_symbol_timestamp', 'symbol', 'timestamp'),
    )

class UserPortfolio(Base):
    __tablename__ = "user_portfolios"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(50), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    quantity = Column(Numeric(precision=12, scale=2), nullable=False)
    avg_price = Column(Numeric(precision=12, scale=2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class TradingSettings(Base):
    __tablename__ = "trading_settings"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, unique=True)
    auto_trade_enabled = Column(Boolean, default=False)
    max_position_size = Column(Numeric(precision=12, scale=2), default=10000.0) # Max INR per trade
    risk_per_trade = Column(Numeric(precision=4, scale=2), default=2.0) # 2% risk
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
