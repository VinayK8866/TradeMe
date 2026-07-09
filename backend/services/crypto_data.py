"""
Crypto Data Ingestion — CoinGecko API
--------------------------------------
Fetches live prices, OHLCV history, and market cap rankings from CoinGecko.
Uses Redis caching to stay within the free-tier rate limit (30 req/min).
Paper trading mode uses CoinGecko prices — no exchange account needed.
"""

import json
import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

import httpx
import redis.asyncio as aioredis
import structlog
from dotenv import load_dotenv
import os

load_dotenv()

logger = structlog.get_logger()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")  # Optional demo key for higher rate limits

# CoinGecko base URL (works with or without API key)
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Cache TTLs (seconds)
PRICE_CACHE_TTL = 60           # Live prices cached 60s
OHLCV_CACHE_TTL = 3600         # OHLCV data cached 1h
MARKET_CAP_CACHE_TTL = 3600    # Rankings cached 1h

# Stablecoins to exclude from the top-10 list
STABLECOIN_IDS = {
    "tether", "usd-coin", "binance-usd", "dai", "true-usd",
    "pax-dollar", "gemini-dollar", "frax", "nusd", "usdd",
    "usde", "first-digital-usd", "paypal-usd"
}

# ─── HTTP Client ───────────────────────────────────────────────────────────────

def _build_headers() -> dict:
    headers = {"Accept": "application/json"}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
    return headers


async def _get(url: str, params: dict | None = None) -> dict | list:
    """
    Thin async wrapper around httpx with retry and error handling.
    CoinGecko free tier: 30 req/min. We stay well under via caching.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        for attempt in range(3):
            try:
                resp = await client.get(url, params=params, headers=_build_headers())
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    # Rate limited — wait and retry
                    wait = 10 * (attempt + 1)
                    logger.warning("coingecko_rate_limit", attempt=attempt, wait_s=wait)
                    await asyncio.sleep(wait)
                else:
                    raise
            except httpx.RequestError as e:
                logger.error("coingecko_request_error", error=str(e), attempt=attempt)
                if attempt == 2:
                    raise
                await asyncio.sleep(3)
    raise RuntimeError("CoinGecko request failed after 3 retries")


# ─── Redis Cache Helpers ────────────────────────────────────────────────────────

async def _cache_get(key: str) -> Optional[dict | list]:
    try:
        redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        async with redis:
            raw = await redis.get(key)
            if raw:
                return json.loads(raw)
    except Exception as e:
        logger.warning("redis_cache_miss", key=key, error=str(e))
    return None


async def _cache_set(key: str, value: dict | list, ttl: int) -> None:
    try:
        redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        async with redis:
            await redis.setex(key, ttl, json.dumps(value, default=str))
    except Exception as e:
        logger.warning("redis_cache_write_failed", key=key, error=str(e))


# ─── Public API ────────────────────────────────────────────────────────────────

async def get_top_coins(limit: int = 30) -> list[dict]:
    """
    Fetch top coins by market cap from CoinGecko (INR denomination).
    Returns more than 10 so the ranker can filter stablecoins and still get 10.

    Returns list of dicts:
        {coingecko_id, symbol, name, rank, market_cap_usd, current_price_inr}
    """
    cache_key = f"crypto:top_coins:{limit}"
    cached = await _cache_get(cache_key)
    if cached:
        logger.debug("top_coins_cache_hit", limit=limit)
        return cached

    url = f"{COINGECKO_BASE}/coins/markets"
    params = {
        "vs_currency": "inr",
        "order": "market_cap_desc",
        "per_page": limit,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h",
    }
    raw = await _get(url, params)

    coins = [
        {
            "coingecko_id": c["id"],
            "symbol": c["symbol"].upper(),
            "name": c["name"],
            "rank": c["market_cap_rank"],
            "market_cap_usd": c.get("market_cap"),
            "current_price_inr": c.get("current_price"),
            "price_change_24h_percent": c.get("price_change_percentage_24h"),
        }
        for c in raw
        if c.get("id") and c.get("symbol")
    ]

    await _cache_set(cache_key, coins, MARKET_CAP_CACHE_TTL)
    logger.info("top_coins_fetched", count=len(coins))
    return coins


async def get_current_prices(coingecko_ids: list[str]) -> dict[str, Decimal]:
    """
    Batch fetch current prices in INR for given CoinGecko IDs.
    Returns {coingecko_id: price_inr}
    """
    if not coingecko_ids:
        return {}

    ids_str = ",".join(coingecko_ids)
    cache_key = f"crypto:prices:{ids_str}"
    cached = await _cache_get(cache_key)
    if cached:
        return {k: Decimal(str(v)) for k, v in cached.items()}

    url = f"{COINGECKO_BASE}/simple/price"
    params = {
        "ids": ids_str,
        "vs_currencies": "inr",
        "include_24hr_change": "true",
    }
    raw = await _get(url, params)

    prices = {
        coin_id: data.get("inr", 0)
        for coin_id, data in raw.items()
    }
    await _cache_set(cache_key, prices, PRICE_CACHE_TTL)
    logger.debug("prices_fetched", coins=list(prices.keys()))
    return {k: Decimal(str(v)) for k, v in prices.items()}


async def get_ohlcv(coingecko_id: str, days: int = 90) -> list[dict]:
    """
    Fetch OHLCV candlestick data for a coin in INR.
    CoinGecko OHLC granularity:
      - days 1-2   → 30-minute candles
      - days 3-30  → 4-hour candles
      - days 31+   → 4-day candles

    For signal calculation we want daily candles. For days >=1, we use
    market_chart with interval=daily which gives daily closes + volume.

    Returns list of dicts: {timestamp, open, high, low, close, volume}
    """
    cache_key = f"crypto:ohlcv:{coingecko_id}:{days}d"
    cached = await _cache_get(cache_key)
    if cached:
        logger.debug("ohlcv_cache_hit", coin=coingecko_id, days=days)
        return cached

    # Use OHLC endpoint for candle data
    ohlc_url = f"{COINGECKO_BASE}/coins/{coingecko_id}/ohlc"
    ohlc_params = {"vs_currency": "inr", "days": str(days)}

    chart_url = f"{COINGECKO_BASE}/coins/{coingecko_id}/market_chart"
    chart_params = {"vs_currency": "inr", "days": str(days), "interval": "daily"}

    # Sequential calls to avoid rate-limit spikes (2 parallel calls per coin = 20 hits for 10 coins)
    ohlc_raw = await _get(ohlc_url, ohlc_params)
    await asyncio.sleep(1.0)  # Brief pause between calls to same server
    chart_raw = await _get(chart_url, chart_params)

    # Build volume lookup {timestamp_ms: volume}
    volume_map: dict[int, float] = {}
    for ts_ms, vol in chart_raw.get("total_volumes", []):
        # Round to nearest day to match OHLC timestamps
        volume_map[ts_ms] = vol

    # Map OHLC rows [timestamp_ms, open, high, low, close]
    candles = []
    for row in ohlc_raw:
        ts_ms, o, h, l, c = row
        # Find closest volume entry
        vol = volume_map.get(ts_ms, 0.0)
        if vol == 0.0:
            # Fallback: find nearest timestamp within ±1 day
            for vts, vvol in volume_map.items():
                if abs(vts - ts_ms) < 86_400_000:
                    vol = vvol
                    break

        candles.append({
            "timestamp": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": vol,
        })

    await _cache_set(cache_key, candles, OHLCV_CACHE_TTL)
    logger.info("ohlcv_fetched", coin=coingecko_id, candles=len(candles))
    return candles


async def get_coin_metadata(coingecko_id: str) -> dict:
    """
    Fetch additional metadata for a coin (description, links, categories).
    Used occasionally — heavily cached.
    """
    cache_key = f"crypto:meta:{coingecko_id}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    url = f"{COINGECKO_BASE}/coins/{coingecko_id}"
    params = {
        "localization": "false",
        "tickers": "false",
        "market_data": "true",
        "community_data": "false",
        "developer_data": "false",
    }
    raw = await _get(url, params)
    meta = {
        "coingecko_id": raw["id"],
        "symbol": raw["symbol"].upper(),
        "name": raw["name"],
        "description": raw.get("description", {}).get("en", "")[:500],
        "homepage": raw.get("links", {}).get("homepage", [None])[0],
        "categories": raw.get("categories", []),
    }
    await _cache_set(cache_key, meta, 86400)  # Cache 24h
    return meta
