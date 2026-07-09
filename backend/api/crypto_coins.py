"""
Crypto Coins API — Phase 1
---------------------------
REST endpoints for coin data, rankings, and live prices.
All data comes from the CryptoCoin table + CoinGecko live fetch.
"""

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.coin_ranker import (
    get_tracked_coins,
    update_coin_rankings,
    refresh_coin_prices,
    get_coin_by_symbol,
)
from services.crypto_data import get_ohlcv, get_current_prices

logger = structlog.get_logger()
router = APIRouter()


# ─── Response Models ────────────────────────────────────────────────────────────

class CoinResponse(BaseModel):
    coingecko_id: str
    symbol: str
    name: str
    rank: int
    market_cap_usd: Optional[float]
    current_price_inr: Optional[float]
    last_price_update: Optional[datetime]

    class Config:
        from_attributes = True


class OHLCVPoint(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class ApiResponse(BaseModel):
    success: bool
    data: object
    error: Optional[str] = None
    timestamp: datetime = None

    def __init__(self, **data):
        if "timestamp" not in data:
            data["timestamp"] = datetime.utcnow()
        super().__init__(**data)


# ─── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/", response_model=ApiResponse)
async def list_tracked_coins():
    """
    GET /api/v1/crypto/coins
    Returns all active top-10 coins from the DB, ordered by rank.
    """
    coins = await get_tracked_coins()
    return ApiResponse(
        success=True,
        data=[CoinResponse.model_validate(c) for c in coins]
    )


@router.get("/{symbol}/price", response_model=ApiResponse)
async def get_coin_price(symbol: str):
    """
    GET /api/v1/crypto/coins/BTC/price
    Returns the current live price (INR) for a tracked coin.
    """
    coin = await get_coin_by_symbol(symbol.upper())
    if not coin:
        raise HTTPException(status_code=404, detail=f"{symbol.upper()} is not in the tracked coin list")

    prices = await get_current_prices([coin.coingecko_id])
    price = prices.get(coin.coingecko_id)

    return ApiResponse(
        success=True,
        data={
            "symbol": coin.symbol,
            "name": coin.name,
            "price_inr": float(price) if price else None,
            "rank": coin.rank,
        }
    )


@router.get("/{symbol}/ohlcv", response_model=ApiResponse)
async def get_coin_ohlcv(
    symbol: str,
    days: int = Query(default=90, ge=7, le=365, description="Number of days of OHLCV history")
):
    """
    GET /api/v1/crypto/coins/BTC/ohlcv?days=90
    Returns candlestick OHLCV data for charting and signal calculation.
    """
    coin = await get_coin_by_symbol(symbol.upper())
    if not coin:
        raise HTTPException(status_code=404, detail=f"{symbol.upper()} is not in the tracked coin list")

    candles = await get_ohlcv(coin.coingecko_id, days=days)
    return ApiResponse(
        success=True,
        data={
            "symbol": coin.symbol,
            "coingecko_id": coin.coingecko_id,
            "days": days,
            "candles": candles,
            "count": len(candles),
        }
    )


@router.post("/refresh/rankings", response_model=ApiResponse)
async def refresh_rankings(force: bool = Query(default=False)):
    """
    POST /api/v1/crypto/coins/refresh/rankings?force=true
    Manually trigger a coin ranking refresh from CoinGecko.
    Normally runs weekly via Celery. Use force=true to bypass the 7-day check.
    """
    logger.info("manual_ranking_refresh_triggered", force=force)
    result = await update_coin_rankings(force=force)
    return ApiResponse(success=True, data=result)


@router.post("/refresh/prices", response_model=ApiResponse)
async def refresh_prices():
    """
    POST /api/v1/crypto/coins/refresh/prices
    Manually trigger a price refresh for all active coins.
    Normally runs every 15 minutes via Celery.
    """
    count = await refresh_coin_prices()
    return ApiResponse(
        success=True,
        data={"updated_count": count, "message": f"Refreshed prices for {count} coins"}
    )
