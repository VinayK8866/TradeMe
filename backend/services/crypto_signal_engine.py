"""
Crypto Signal Engine — Phase 2
--------------------------------
Calculates technical indicators and generates trade signals for a given coin.
Uses 90 days of OHLCV data from CoinGecko (cached via Redis).

Indicators computed:
  - RSI (14)
  - EMA 20 / EMA 50
  - MACD (12, 26, 9)
  - Bollinger Bands (20, 2σ)
  - ATR (14) — for volatility sizing
  - Volume ratio (current vs 20-period average)
  - ADX (14) — trend strength
  - Bollinger Band Width — for squeeze detection
"""

import numpy as np
import pandas as pd
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import structlog

from services.crypto_data import get_ohlcv
from services.coin_ranker import get_tracked_coins, get_coin_by_symbol

logger = structlog.get_logger()


# ─── Data Loading ───────────────────────────────────────────────────────────────

async def load_ohlcv_dataframe(coingecko_id: str, days: int = 90) -> pd.DataFrame:
    """
    Fetch OHLCV from CoinGecko and return as a clean pandas DataFrame.
    Sorted oldest → newest. Minimum 30 rows required for signal calculation.
    """
    raw = await get_ohlcv(coingecko_id, days=days)
    if not raw:
        return pd.DataFrame()

    df = pd.DataFrame(raw)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df[["open", "high", "low", "close", "volume"]] = df[
        ["open", "high", "low", "close", "volume"]
    ].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["close", "volume"])
    return df


# ─── Indicator Calculations ─────────────────────────────────────────────────────

def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (macd_line, signal_line, histogram)."""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_bollinger(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (upper_band, middle_band, lower_band)."""
    middle = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return upper, middle, lower


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Simplified ADX calculation using rolling TR and directional movement."""
    up_move = df["high"].diff()
    down_move = df["low"].diff().abs()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = calc_atr(df, period=1)  # TR at period=1

    plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(period).mean() / tr.rolling(period).mean())
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(period).mean() / tr.rolling(period).mean())

    dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx = dx.rolling(period).mean()
    return adx


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicators to the DataFrame in one pass."""
    df = df.copy()
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["sma20"] = df["close"].rolling(20).mean()
    df["rsi"] = calc_rsi(df["close"], 14)
    df["macd"], df["macd_signal"], df["macd_hist"] = calc_macd(df["close"])
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = calc_bollinger(df["close"])
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]  # Normalized width
    df["atr"] = calc_atr(df, 14)
    df["adx"] = calc_adx(df, 14)
    df["vol_avg20"] = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / df["vol_avg20"].replace(0, np.nan)
    df["bb_pct"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)  # 0=lower, 1=upper
    return df


# ─── Market Condition Detection ─────────────────────────────────────────────────

def detect_market_condition(latest: pd.Series, df: pd.DataFrame) -> dict:
    """
    Classifies current market state for the coin.
    Returns dict with: condition, trend_direction, adx_strength
    """
    adx = latest.get("adx", np.nan)
    ema20 = latest.get("ema20", np.nan)
    ema50 = latest.get("ema50", np.nan)
    close = latest.get("close", np.nan)
    bb_width = latest.get("bb_width", np.nan)

    # ADX: <20 = no trend (ranging), 20-25 = weak, 25-40 = moderate, >40 = strong
    is_trending = not np.isnan(adx) and adx > 22

    # Trend direction from EMA alignment
    if not np.isnan(ema20) and not np.isnan(ema50):
        if ema20 > ema50 and close > ema20:
            trend_direction = "uptrend"
        elif ema20 < ema50 and close < ema20:
            trend_direction = "downtrend"
        else:
            trend_direction = "mixed"
    else:
        trend_direction = "unknown"

    # Bollinger Band squeeze: width below its 20th percentile = consolidation
    bb_width_series = df["bb_width"].dropna()
    bb_squeeze = False
    if len(bb_width_series) >= 20 and not np.isnan(bb_width):
        squeeze_threshold = bb_width_series.quantile(0.25)
        bb_squeeze = bool(bb_width <= squeeze_threshold)

    # Determine primary condition
    if bb_squeeze:
        condition = "squeeze"      # Breakout strategy territory
    elif is_trending and trend_direction == "uptrend":
        condition = "trending_up"  # Momentum strategy territory
    elif is_trending and trend_direction == "downtrend":
        condition = "trending_down"
    else:
        condition = "ranging"      # Mean reversion territory

    return {
        "condition": condition,
        "trend_direction": trend_direction,
        "adx": round(float(adx), 1) if not np.isnan(adx) else None,
        "adx_strength": (
            "strong" if not np.isnan(adx) and adx > 35
            else "moderate" if not np.isnan(adx) and adx > 22
            else "weak"
        ),
        "bb_squeeze": bb_squeeze,
        "bb_width": round(float(bb_width), 4) if not np.isnan(bb_width) else None,
    }


# ─── The 4 Strategies ───────────────────────────────────────────────────────────

def strategy_momentum(latest: pd.Series, prev: pd.Series) -> dict:
    """
    Momentum Strategy — best in uptrending markets.
    Buy when: RSI 45-68 + price > EMA20 > EMA50 + volume spike
    Sell when: RSI > 72 OR price drops below EMA20 OR volume dries up
    """
    rsi = latest["rsi"]
    close = latest["close"]
    ema20 = latest["ema20"]
    ema50 = latest["ema50"]
    vol_ratio = latest["vol_ratio"]
    bb_pct = latest["bb_pct"]

    factors = {}
    score = 0
    max_score = 5

    # 1. RSI in momentum zone
    if 45 <= rsi <= 68:
        score += 1.5
        factors["rsi"] = f"RSI {rsi:.1f} — healthy momentum zone"
    elif rsi > 72:
        score -= 1
        factors["rsi"] = f"RSI {rsi:.1f} — overbought, momentum stalling"
    elif rsi < 40:
        score -= 2
        factors["rsi"] = f"RSI {rsi:.1f} — momentum lost"

    # 2. EMA alignment (price > EMA20 > EMA50)
    if close > ema20 > ema50:
        score += 1.5
        factors["ema"] = "Price > EMA20 > EMA50 — bullish alignment"
    elif close < ema20:
        score -= 1.5
        factors["ema"] = "Price below EMA20 — trend weakening"

    # 3. Volume confirmation
    if vol_ratio >= 1.5:
        score += 1
        factors["volume"] = f"Volume {vol_ratio:.1f}x average — strong participation"
    elif vol_ratio < 0.8:
        score -= 0.5
        factors["volume"] = f"Volume {vol_ratio:.1f}x average — low participation"

    # 4. Not at Bollinger Band extremes
    if 0.4 <= bb_pct <= 0.85:
        score += 0.5
        factors["bb_position"] = f"Price at {bb_pct:.0%} of BB range — good entry zone"
    elif bb_pct > 0.9:
        score -= 0.5
        factors["bb_position"] = "Price near BB upper — stretched"

    # 5. Upward price momentum (close > prev close)
    if close > prev["close"]:
        score += 0.5
        factors["price_action"] = "Price moving up"
    else:
        factors["price_action"] = "Price moving down"

    confidence = int(min(100, max(0, (score / max_score) * 100)))

    if confidence >= 65:
        signal = "BUY"
    elif confidence <= 30:
        signal = "AVOID"
    elif score < 0:
        signal = "SELL" if close < ema20 else "WATCH"
    else:
        signal = "WATCH"

    return {"strategy": "Momentum", "signal": signal, "confidence": confidence, "factors": factors, "score": round(score, 2)}


def strategy_mean_reversion(latest: pd.Series, prev: pd.Series) -> dict:
    """
    Mean Reversion — best in sideways/ranging markets.
    Buy when: RSI oversold AND price near/below lower Bollinger Band.
    Sell when: RSI overbought AND price near/above upper Bollinger Band.
    """
    rsi = latest["rsi"]
    close = latest["close"]
    bb_upper = latest["bb_upper"]
    bb_lower = latest["bb_lower"]
    bb_mid = latest["bb_mid"]
    bb_pct = latest["bb_pct"]
    vol_ratio = latest["vol_ratio"]

    factors = {}
    score = 0
    max_score = 4

    # 1. RSI oversold → buy opportunity
    if rsi < 32:
        score += 2.0
        factors["rsi"] = f"RSI {rsi:.1f} — strongly oversold, reversal likely"
    elif rsi < 40:
        score += 1.0
        factors["rsi"] = f"RSI {rsi:.1f} — oversold zone"
    elif rsi > 70:
        score -= 2.0
        factors["rsi"] = f"RSI {rsi:.1f} — overbought, potential reversal down"
    elif rsi > 60:
        score -= 0.5
        factors["rsi"] = f"RSI {rsi:.1f} — elevated"
    else:
        factors["rsi"] = f"RSI {rsi:.1f} — neutral"

    # 2. Price position within Bollinger Bands
    if bb_pct <= 0.1:
        score += 1.5
        factors["bb_position"] = f"Price at {bb_pct:.0%} of BB — at/below lower band (oversold)"
    elif bb_pct <= 0.25:
        score += 0.75
        factors["bb_position"] = f"Price at {bb_pct:.0%} of BB — near lower band"
    elif bb_pct >= 0.9:
        score -= 1.5
        factors["bb_position"] = f"Price at {bb_pct:.0%} of BB — at/above upper band (overbought)"
    else:
        factors["bb_position"] = f"Price at {bb_pct:.0%} of BB — mid range"

    # 3. Not a strong trend (mean reversion fails in strong trends)
    if 0.8 <= vol_ratio <= 1.3:
        score += 0.5
        factors["volume"] = "Normal volume — range-bound behavior"
    else:
        factors["volume"] = f"Volume {vol_ratio:.1f}x — unusual activity"

    confidence = int(min(100, max(0, (score / max_score) * 100)))

    if confidence >= 65 and rsi < 45:
        signal = "BUY"
    elif score <= -1.5:
        signal = "AVOID"
    elif rsi > 65:
        signal = "WATCH"
    else:
        signal = "HOLD"

    return {"strategy": "Mean Reversion", "signal": signal, "confidence": confidence, "factors": factors, "score": round(score, 2)}


def strategy_breakout(latest: pd.Series, prev: pd.Series, df: pd.DataFrame) -> dict:
    """
    Breakout Strategy — fires when price breaks out of a squeeze.
    Buy when: BB squeeze + price breaks above upper band + volume spike.
    """
    close = latest["close"]
    bb_upper = latest["bb_upper"]
    bb_lower = latest["bb_lower"]
    bb_width = latest["bb_width"]
    vol_ratio = latest["vol_ratio"]
    rsi = latest["rsi"]

    prev_close = prev["close"]
    prev_bb_upper = prev["bb_upper"]
    prev_bb_lower = prev["bb_lower"]

    factors = {}
    score = 0
    max_score = 4

    # 1. Was there a squeeze recently?
    bb_width_history = df["bb_width"].dropna()
    squeeze_threshold = bb_width_history.quantile(0.30) if len(bb_width_history) >= 20 else bb_width * 1.1
    was_squeeze = latest["bb_width"] <= squeeze_threshold
    if was_squeeze:
        score += 1.5
        factors["squeeze"] = f"BB width {bb_width:.3f} — squeeze detected (threshold {squeeze_threshold:.3f})"
    else:
        factors["squeeze"] = "No squeeze detected"

    # 2. Upward breakout (price crossed above upper BB)
    if close > bb_upper and prev_close <= prev_bb_upper:
        score += 2.0
        factors["breakout"] = "Price broke above upper Bollinger Band — bullish breakout!"
    elif close < bb_lower and prev_close >= prev_bb_lower:
        score -= 2.0
        factors["breakout"] = "Price broke below lower Bollinger Band — bearish breakdown!"
    elif close > bb_upper:
        score += 0.5
        factors["breakout"] = "Price above upper BB (sustained)"
    else:
        factors["breakout"] = "No breakout yet — price inside bands"

    # 3. Volume spike confirms breakout
    if vol_ratio >= 2.0:
        score += 1.5
        factors["volume"] = f"Volume {vol_ratio:.1f}x average — strong breakout confirmation"
    elif vol_ratio >= 1.4:
        score += 0.75
        factors["volume"] = f"Volume {vol_ratio:.1f}x average — moderate confirmation"
    else:
        score -= 0.5
        factors["volume"] = f"Volume {vol_ratio:.1f}x — weak, breakout may be false"

    # RSI not overbought
    if rsi < 75:
        score += 0.5
        factors["rsi"] = f"RSI {rsi:.1f} — not yet overbought, room to run"
    else:
        score -= 0.5
        factors["rsi"] = f"RSI {rsi:.1f} — overbought, late entry risk"

    confidence = int(min(100, max(0, (score / max_score) * 100)))

    if confidence >= 60 and score > 0:
        signal = "BUY"
    elif score < -1:
        signal = "AVOID"
    else:
        signal = "WATCH"

    return {"strategy": "Breakout", "signal": signal, "confidence": confidence, "factors": factors, "score": round(score, 2)}


def strategy_macd(latest: pd.Series, prev: pd.Series) -> dict:
    """
    MACD Crossover Strategy — works across all market conditions.
    Buy on bullish crossover (MACD line crosses above signal) + positive histogram.
    Sell on bearish crossover.
    """
    macd = latest["macd"]
    macd_signal = latest["macd_signal"]
    macd_hist = latest["macd_hist"]
    prev_macd = prev["macd"]
    prev_signal = prev["macd_signal"]
    prev_hist = prev["macd_hist"]
    close = latest["close"]
    ema50 = latest["ema50"]
    vol_ratio = latest["vol_ratio"]

    factors = {}
    score = 0
    max_score = 4

    # 1. Crossover detection
    bullish_cross = prev_macd < prev_signal and macd > macd_signal
    bearish_cross = prev_macd > prev_signal and macd < macd_signal

    if bullish_cross:
        score += 2.0
        factors["crossover"] = "MACD bullish crossover — buy signal triggered"
    elif bearish_cross:
        score -= 2.0
        factors["crossover"] = "MACD bearish crossover — sell signal triggered"
    elif macd > macd_signal:
        score += 0.5
        factors["crossover"] = "MACD above signal — bullish bias"
    else:
        score -= 0.5
        factors["crossover"] = "MACD below signal — bearish bias"

    # 2. Histogram momentum (expanding = stronger signal)
    if macd_hist > 0 and macd_hist > prev_hist:
        score += 1.0
        factors["histogram"] = "MACD histogram expanding upward — momentum accelerating"
    elif macd_hist < 0 and macd_hist < prev_hist:
        score -= 1.0
        factors["histogram"] = "MACD histogram expanding downward — bearish momentum"
    elif macd_hist > 0:
        score += 0.25
        factors["histogram"] = "MACD histogram positive — mild bullish momentum"

    # 3. Both MACD line and histogram above zero (above zero = bullish)
    if macd > 0 and macd_hist > 0:
        score += 0.75
        factors["zero_line"] = "MACD and histogram both above zero — strong bullish"
    elif macd < 0 and macd_hist < 0:
        score -= 0.75
        factors["zero_line"] = "MACD and histogram both below zero — bearish"
    else:
        factors["zero_line"] = "MACD near zero line — transition zone"

    # 4. Price above EMA50 (trend filter)
    if close > ema50:
        score += 0.5
        factors["trend_filter"] = "Price above EMA50 — buy signals more reliable"
    else:
        score -= 0.5
        factors["trend_filter"] = "Price below EMA50 — sell signals more reliable"

    confidence = int(min(100, max(0, (score / max_score) * 100)))

    if confidence >= 65 and macd > macd_signal:
        signal = "BUY"
    elif score <= -1.5:
        signal = "SELL" if bearish_cross else "AVOID"
    elif macd > macd_signal:
        signal = "WATCH"
    else:
        signal = "HOLD"

    return {"strategy": "MACD", "signal": signal, "confidence": confidence, "factors": factors, "score": round(score, 2)}


# ─── Main Signal Calculation ────────────────────────────────────────────────────

async def calculate_crypto_signal(symbol: str) -> dict:
    """
    Full signal calculation for a tracked coin.
    Fetches 365 days of OHLCV data (CoinGecko gives 4-day candles at this range,
    yielding ~91 data points — enough for all indicators including MACD-26).
    """
    from services.strategy_selector import select_strategy

    coin = await get_coin_by_symbol(symbol)
    if not coin:
        raise ValueError(f"Coin {symbol} not found in tracked list")

    df = await load_ohlcv_dataframe(coin.coingecko_id, days=365)
    if df.empty or len(df) < 30:
        raise ValueError(f"Insufficient OHLCV data for {symbol} (got {len(df)} rows, need ≥30)")

    df = enrich_dataframe(df)
    df = df.dropna(subset=["rsi", "macd", "bb_upper"])

    if len(df) < 2:
        raise ValueError(f"Not enough enriched data rows for {symbol}")

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # Market condition
    market = detect_market_condition(latest, df)

    # Run all 4 strategies
    results = {
        "Momentum": strategy_momentum(latest, prev),
        "Mean Reversion": strategy_mean_reversion(latest, prev),
        "Breakout": strategy_breakout(latest, prev, df),
        "MACD": strategy_macd(latest, prev),
    }

    # Pick best strategy for current market condition
    selected_name = select_strategy(market, results)
    selected = results[selected_name]

    # Snapshot of key indicators
    indicators = {
        "rsi": round(float(latest["rsi"]), 2),
        "macd": round(float(latest["macd"]), 6),
        "macd_signal": round(float(latest["macd_signal"]), 6),
        "macd_hist": round(float(latest["macd_hist"]), 6),
        "ema20": round(float(latest["ema20"]), 4),
        "ema50": round(float(latest["ema50"]), 4),
        "bb_upper": round(float(latest["bb_upper"]), 4),
        "bb_lower": round(float(latest["bb_lower"]), 4),
        "bb_pct": round(float(latest["bb_pct"]), 3),
        "bb_width": round(float(latest["bb_width"]), 4),
        "atr": round(float(latest["atr"]), 4),
        "adx": round(float(latest["adx"]), 2) if not np.isnan(latest["adx"]) else None,
        "vol_ratio": round(float(latest["vol_ratio"]), 2),
        "close": round(float(latest["close"]), 4),
    }

    # Stop-loss price (5% below current price, can be tightened by ATR)
    stop_loss_price = round(float(latest["close"]) * 0.95, 4)

    return {
        "symbol": coin.symbol,
        "name": coin.name,
        "coingecko_id": coin.coingecko_id,
        "rank": coin.rank,
        "signal": selected["signal"],
        "confidence": selected["confidence"],
        "selected_strategy": selected_name,
        "stop_loss_price_inr": stop_loss_price,
        "market_condition": market,
        "indicators": indicators,
        "strategy_breakdown": results,
        "all_signals": {name: r["signal"] for name, r in results.items()},
        "data_points": len(df),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }


async def calculate_all_signals() -> list[dict]:
    """
    Run signal calculation for all active tracked coins.
    Used by Celery and the dashboard overview endpoint.
    """
    import asyncio
    import os
    import redis.asyncio as aioredis
    import json

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Check if we have cached signals first to return instantly
    cache_key = "crypto:signals:all"
    try:
        redis = aioredis.from_url(redis_url, decode_responses=True)
        async with redis:
            cached = await redis.get(cache_key)
            if cached:
                logger.info("all_signals_cache_hit")
                return json.loads(cached)
    except Exception as cache_err:
        logger.warning("failed_to_get_signals_cache", error=str(cache_err))

    coins = await get_tracked_coins()
    results = []
    errors = []

    try:
        redis = aioredis.from_url(redis_url, decode_responses=True)
        async with redis:
            for coin in coins:
                try:
                    # Check if OHLCV data is already cached
                    ohlcv_key = f"crypto:ohlcv:{coin.coingecko_id}:365d"
                    is_cached = await redis.exists(ohlcv_key)
                    
                    signal = await calculate_crypto_signal(coin.symbol)
                    results.append(signal)
                    logger.info(
                        "signal_calculated",
                        symbol=coin.symbol,
                        signal=signal["signal"],
                        confidence=signal["confidence"],
                        strategy=signal["selected_strategy"],
                        cached=is_cached
                    )
                    
                    # Only sleep if the data wasn't already in Redis cache
                    if not is_cached:
                        await asyncio.sleep(2.0)
                except Exception as e:
                    errors.append({"symbol": coin.symbol, "error": str(e)})
                    logger.error("signal_calculation_failed", symbol=coin.symbol, error=str(e))
    except Exception as e:
        logger.error("redis_connection_failed_in_signals", error=str(e))
        # Fallback without Redis exists check
        for coin in coins:
            try:
                signal = await calculate_crypto_signal(coin.symbol)
                results.append(signal)
                await asyncio.sleep(2.0)
            except Exception as ex:
                errors.append({"symbol": coin.symbol, "error": str(ex)})

    # Cache the successful signals list in Redis for 60 seconds
    if results and not errors:
        try:
            redis = aioredis.from_url(redis_url, decode_responses=True)
            async with redis:
                await redis.setex(cache_key, 60, json.dumps(results))
                logger.info("all_signals_cached")
        except Exception as cache_err:
            logger.warning("failed_to_cache_signals", error=str(cache_err))

    logger.info("all_signals_calculated", success=len(results), errors=len(errors))
    return results
