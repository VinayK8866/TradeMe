from dotenv import load_dotenv
import os

# Load environment variables early
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import prices, signals, explain, backtest, prices_ws, sentiment, auto_trade
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
        # Import models here to ensure they are registered with Base
        from models.db_models import ETFPriceHistory, UserPortfolio, TradingSettings
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized successfully")

# Include routers
app.include_router(prices.router, prefix="/api/v1/prices", tags=["prices"])
app.include_router(signals.router, prefix="/api/v1/signals", tags=["signals"])
app.include_router(explain.router, prefix="/api/v1/explain", tags=["explain"])
app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["backtest"])
app.include_router(sentiment.router, prefix="/api/v1/sentiment", tags=["sentiment"])
app.include_router(auto_trade.router, prefix="/api/v1/auto-trade", tags=["auto-trade"])
app.include_router(prices_ws.router, tags=["websocket"])

@app.get("/")
async def root():
    return {"message": "Welcome to the India ETF Trading Platform API", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting India ETF Trading Platform Backend")
    uvicorn.run(app, host="0.0.0.0", port=8000)
