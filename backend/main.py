from dotenv import load_dotenv
import os

# Load environment variables early
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import prices, signals, explain, backtest, prices_ws, sentiment, auto_trade
from api import crypto_coins, crypto_signals, crypto_portfolio
from db.database import engine, Base
import structlog

# Setup structured logging
structlog.configure()
logger = structlog.get_logger()

app = FastAPI(title="India ETF Trading Platform API")

# Configure CORS for Next.js frontend (Allowing both localhost and 127.0.0.1)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3030", "http://127.0.0.1:3030"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing database tables...")
    async with engine.begin() as conn:
        # ETF models
        from models.db_models import ETFPriceHistory, UserPortfolio, TradingSettings
        # Crypto bot models
        from models.crypto_models import (
            CryptoCoin, CryptoPriceHistory, CryptoPortfolio,
            CryptoTrade, TradeMemory, CryptoBotSettings, CryptoPortfolioSnapshot
        )
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text
        await conn.execute(text("ALTER TABLE crypto_portfolio ADD COLUMN IF NOT EXISTS take_profit_price_inr NUMERIC(20, 8);"))
        # Update empty trade memories with a helpful fallback message since quota was breached
        await conn.execute(text("""
            UPDATE trade_memory 
            SET what_worked = 'Unavailable due to API error.', 
                what_failed = 'AI analysis failed: Gemini API key exceeded its daily request limits (429 Quota Exceeded) during the cycle.', 
                lesson = 'Ensure your Gemini API key has sufficient quota limits or wait for the daily limit to reset.', 
                avoid_pattern = 'N/A' 
            WHERE lesson IS NULL OR lesson = '';
        """))
    logger.info("Database initialized successfully")

    # Start Telegram Bot service
    from services.telegram_bot import init_telegram_bot, start_telegram_bot
    await init_telegram_bot()
    await start_telegram_bot()


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down services...")
    from services.telegram_bot import stop_telegram_bot
    await stop_telegram_bot()
    logger.info("Shutdown complete")

# ETF Platform routes (existing)
app.include_router(prices.router, prefix="/api/v1/prices", tags=["etf-prices"])
app.include_router(signals.router, prefix="/api/v1/signals", tags=["etf-signals"])
app.include_router(explain.router, prefix="/api/v1/explain", tags=["etf-explain"])
app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["etf-backtest"])
app.include_router(sentiment.router, prefix="/api/v1/sentiment", tags=["etf-sentiment"])
app.include_router(auto_trade.router, prefix="/api/v1/auto-trade", tags=["etf-auto-trade"])
app.include_router(prices_ws.router, tags=["etf-websocket"])

# Crypto Bot routes
app.include_router(crypto_coins.router, prefix="/api/v1/crypto/coins", tags=["crypto-coins"])
app.include_router(crypto_signals.router, prefix="/api/v1/crypto/signals", tags=["crypto-signals"])
app.include_router(crypto_portfolio.router, prefix="/api/v1/crypto", tags=["crypto-portfolio"])

@app.get("/")
async def root():
    return {"message": "Welcome to the India ETF Trading Platform API", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting India ETF Trading Platform Backend")
    uvicorn.run(app, host="0.0.0.0", port=8000)
