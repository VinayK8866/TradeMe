"""
Coin Ranker — Top 10 Crypto Tracker
-------------------------------------
Manages the list of tracked coins. Fetches top 30 from CoinGecko,
filters out stablecoins, keeps top 10 actual cryptocurrencies.
Auto-refreshed weekly via Celery. Can also be triggered manually.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.database import async_session
from models.crypto_models import CryptoCoin
from services.crypto_data import get_top_coins, get_current_prices, STABLECOIN_IDS

logger = structlog.get_logger()

# Coins to always exclude (wrapped tokens, stablecoins, etc.)
EXCLUDED_IDS = STABLECOIN_IDS | {
    "wrapped-bitcoin",       # WBTC — duplicate of BTC
    "wrapped-ether",         # WETH — duplicate of ETH
    "staked-ether",          # stETH — staked ETH
    "wrapped-steth",
    "bitcoin-cash-sv",       # BSV — low legitimacy
    "leo-token",             # Exchange token
    "bitget-token",          # Exchange token
    "figure-heloc",          # Not a real crypto (asset-backed instrument)
    "usds",                  # Stablecoin not caught by ID
    "ethena-usde",           # Synthetic USD stablecoin
    "ondo-us-dollar-yield",  # Yield-bearing stablecoin
    "mantra-dao",            # Low liquidity concern
}

TOP_N = 10
REFRESH_INTERVAL_DAYS = 7


async def needs_refresh() -> bool:
    """Check if the coin list is stale and should be refreshed."""
    async with async_session() as session:
        stmt = select(CryptoCoin).order_by(CryptoCoin.last_rank_update.desc()).limit(1)
        result = await session.execute(stmt)
        latest = result.scalar_one_or_none()

        if not latest or not latest.last_rank_update:
            return True

        age = datetime.now(timezone.utc) - latest.last_rank_update.replace(tzinfo=timezone.utc)
        return age > timedelta(days=REFRESH_INTERVAL_DAYS)


async def get_tracked_coins() -> list[CryptoCoin]:
    """Return current top 10 active coins from DB, ordered by rank."""
    async with async_session() as session:
        stmt = (
            select(CryptoCoin)
            .where(CryptoCoin.is_active == True)
            .order_by(CryptoCoin.rank)
            .limit(TOP_N)
        )
        result = await session.execute(stmt)
        return result.scalars().all()


async def update_coin_rankings(force: bool = False) -> dict:
    """
    Fetch fresh top-10 from CoinGecko and upsert to DB.
    - Marks coins that left the top 10 as inactive
    - Adds newly entered coins
    - Updates market cap + price for all existing coins

    Returns summary dict with added, removed, and updated coins.
    """
    if not force and not await needs_refresh():
        logger.info("coin_rankings_up_to_date")
        return {"status": "up_to_date", "added": [], "removed": [], "updated": []}

    logger.info("refreshing_coin_rankings")

    # Fetch top 30 from CoinGecko to have enough after filtering
    raw_coins = await get_top_coins(limit=30)

    # Filter out stablecoins and excluded tokens
    eligible = [
        c for c in raw_coins
        if c["coingecko_id"] not in EXCLUDED_IDS
    ]

    # Take top 10 from eligible list
    new_top_10 = eligible[:TOP_N]
    new_ids = {c["coingecko_id"] for c in new_top_10}

    added: list[str] = []
    removed: list[str] = []
    updated: list[str] = []

    async with async_session() as session:
        # Get current active coins from DB
        stmt = select(CryptoCoin)
        result = await session.execute(stmt)
        existing_coins: list[CryptoCoin] = result.scalars().all()
        existing_map = {c.coingecko_id: c for c in existing_coins}
        existing_active_ids = {c.coingecko_id for c in existing_coins if c.is_active}

        now = datetime.now(timezone.utc)

        # Deactivate coins that left the top 10
        for coin_id in existing_active_ids - new_ids:
            if coin_id in existing_map:
                existing_map[coin_id].is_active = False
                removed.append(existing_map[coin_id].symbol)
                logger.info("coin_deactivated", coin=coin_id)

        # Upsert new top 10
        for coin_data in new_top_10:
            cg_id = coin_data["coingecko_id"]
            if cg_id in existing_map:
                # Update existing
                coin = existing_map[cg_id]
                coin.rank = coin_data["rank"]
                coin.market_cap_usd = coin_data.get("market_cap_usd")
                coin.current_price_inr = coin_data.get("current_price_inr")
                coin.is_active = True
                coin.last_rank_update = now
                coin.last_price_update = now
                updated.append(coin.symbol)
            else:
                # New coin entered top 10
                new_coin = CryptoCoin(
                    coingecko_id=cg_id,
                    symbol=coin_data["symbol"],
                    name=coin_data["name"],
                    rank=coin_data["rank"],
                    market_cap_usd=coin_data.get("market_cap_usd"),
                    current_price_inr=coin_data.get("current_price_inr"),
                    is_active=True,
                    last_rank_update=now,
                    last_price_update=now,
                )
                session.add(new_coin)
                added.append(coin_data["symbol"])
                logger.info("new_coin_added", coin=cg_id, symbol=coin_data["symbol"])

        await session.commit()

    summary = {
        "status": "refreshed",
        "timestamp": now.isoformat(),
        "added": added,
        "removed": removed,
        "updated": updated,
        "top_10": [c["symbol"] for c in new_top_10],
    }
    logger.info("coin_rankings_updated", **{k: v for k, v in summary.items() if k != "top_10"})
    return summary


async def refresh_coin_prices() -> int:
    """
    Update current_price_inr for all active coins from CoinGecko.
    Called every 15 minutes by Celery to keep prices fresh.
    Returns number of coins updated.
    """
    coins = await get_tracked_coins()
    if not coins:
        logger.warning("no_active_coins_to_refresh_prices")
        return 0

    coingecko_ids = [c.coingecko_id for c in coins]
    prices = await get_current_prices(coingecko_ids)

    now = datetime.now(timezone.utc)
    async with async_session() as session:
        for coin in coins:
            price = prices.get(coin.coingecko_id)
            if price is not None:
                stmt = (
                    update(CryptoCoin)
                    .where(CryptoCoin.id == coin.id)
                    .values(current_price_inr=price, last_price_update=now)
                )
                await session.execute(stmt)

        await session.commit()

    logger.info("coin_prices_refreshed", count=len(coins))
    return len(coins)


async def get_coin_by_symbol(symbol: str) -> Optional[CryptoCoin]:
    """Fetch a tracked coin by its symbol (e.g. 'BTC')."""
    async with async_session() as session:
        stmt = (
            select(CryptoCoin)
            .where(CryptoCoin.symbol == symbol.upper(), CryptoCoin.is_active == True)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def get_coin_by_id(coingecko_id: str) -> Optional[CryptoCoin]:
    """Fetch a tracked coin by its CoinGecko ID (e.g. 'bitcoin')."""
    async with async_session() as session:
        stmt = select(CryptoCoin).where(CryptoCoin.coingecko_id == coingecko_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
