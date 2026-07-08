import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
from models.signal import ETFSignal
from services.data_ingestion import fetch_ohlcv, fetch_market_news
from services.sentiment import analyze_news_sentiment
import structlog

logger = structlog.get_logger()
IST = pytz.timezone('Asia/Kolkata')

# Signal Cache
_signal_cache = {}
SIGNAL_CACHE_EXPIRY = 300 # 5 minutes

def calculate_rsi(series, period=14):
    """Manual RSI calculation."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

async def calculate_signals(symbol: str) -> ETFSignal:
    """
    Calculate technical signals combined with AI news sentiment.
    Includes a 5-minute cache to reduce API overhead.
    """
    now = datetime.now(IST)
    if symbol in _signal_cache:
        cached_signal, timestamp = _signal_cache[symbol]
        if now - timestamp < timedelta(seconds=SIGNAL_CACHE_EXPIRY):
            return cached_signal

    # 1. Technical Analysis
    df = await fetch_ohlcv(symbol, period="1y", interval="1d")
    
    if df.empty or len(df) < 50:
        raise ValueError(f"Insufficient data for signal calculation for {symbol}")

    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['RSI_14'] = calculate_rsi(df['Close'], period=14)
    
    latest = df.iloc[-1]
    avg_volume = df['Volume'].tail(20).mean()
    
    rsi = float(latest['RSI_14'])
    ma50 = float(latest['SMA_50'])
    ma20 = float(latest['SMA_20'])
    price = float(latest['Close'])
    volume = float(latest['Volume'])
    volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
    
    # 2. Sentiment Analysis (Integrated Intelligence)
    news_text = await fetch_market_news(symbol)
    sentiment = await analyze_news_sentiment(symbol, news_text)
    sentiment_score = sentiment.get("score", 0.0)
    
    # 3. Combined Decision Logic
    signal_type = "WATCH"
    
    # Base technical signals
    if price < ma50 or rsi > 70 or rsi < 30:
        signal_type = "AVOID"
    elif 40 <= rsi <= 60 and price > ma50 and volume_ratio > 1.2:
        signal_type = "BUY"
    elif abs(price - ma50) / ma50 < 0.01 or 60 < rsi <= 70:
        signal_type = "HOLD"
    
    # Sentiment Override/Refinement
    if signal_type == "BUY" and sentiment_score < -0.4:
        # Technicals say buy, but news is scary
        signal_type = "WATCH" 
        logger.info("signal_downgraded_by_sentiment", symbol=symbol, score=sentiment_score)
    elif signal_type == "WATCH" and sentiment_score > 0.6 and price > ma50:
        # Technicals neutral but news is extremely bullish and trend is positive
        signal_type = "HOLD"
        logger.info("signal_upgraded_by_sentiment", symbol=symbol, score=sentiment_score)

    signal = ETFSignal(
        symbol=symbol.replace('.NS', '').replace('.BO', ''),
        signal_type=signal_type,
        rsi=round(rsi, 2) if not np.isnan(rsi) else 0,
        ma50=round(ma50, 2) if not np.isnan(ma50) else 0,
        ma20=round(ma20, 2) if not np.isnan(ma20) else 0,
        volume_ratio=round(volume_ratio, 2),
        timestamp=now,
        sentiment_score=round(sentiment_score, 2),
        sentiment_label=sentiment.get("label", "NEUTRAL")
    )
    
    # Update cache
    _signal_cache[symbol] = (signal, now)
    
    return signal
