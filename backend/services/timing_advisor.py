"""
Timing Advisor — Dynamic Trade Window Recommendations
-------------------------------------------------------
Queries the last 30 days of price volatility and volume patterns,
aggregates metrics by hour of the day (in IST), and feeds this quantitative
data to Google Gemini to generate a tailored, actionable trading window advisory.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List
import pandas as pd
import numpy as np
import structlog
import pytz

from sqlalchemy import select
from db.database import async_session
from models.crypto_models import CryptoCoin, CryptoPriceHistory
from services.gemini_brain import generate_timing_advisory

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")


async def get_hourly_volatility_stats() -> Dict:
    """
    Analyzes historical price data to find when volatility and volume spike.
    Aggregates metrics by hour of the day (IST).
    """
    async with async_session() as session:
        # Load last 30 days of price history
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        stmt = (
            select(CryptoPriceHistory)
            .where(CryptoPriceHistory.timestamp >= thirty_days_ago)
            .order_by(CryptoPriceHistory.timestamp.asc())
        )
        result = await session.execute(stmt)
        history = result.scalars().all()

    if not history:
        return {
            "success": False,
            "message": "Insufficient price history data to compute stats",
            "peaks": []
        }

    # Load into Pandas DataFrame for analysis
    data = []
    for h in history:
        # Convert timestamp to IST
        ts_ist = h.timestamp.astimezone(IST)
        # Compute intraday ranges (High - Low) / Close as percentage
        hl_pct = float((h.high - h.low) / h.close * 100) if h.close > 0 else 0
        data.append({
            "symbol": h.symbol,
            "hour": ts_ist.hour,
            "hl_pct": hl_pct,
            "volume": float(h.volume)
        })

    df = pd.DataFrame(data)
    
    # Group by hour to find average hourly volatility & volume
    hourly_stats = df.groupby("hour").agg(
        avg_volatility=("hl_pct", "mean"),
        avg_volume=("volume", "mean")
    ).reset_index()

    # Sort to find peak hours
    peaks_vol = hourly_stats.sort_values(by="avg_volatility", ascending=False).head(3)
    peaks_vol_list = []
    for _, row in peaks_vol.iterrows():
        hour_val = int(row["hour"])
        peaks_vol_list.append({
            "hour_ist": f"{hour_val:02d}:00",
            "avg_volatility_pct": round(float(row["avg_volatility"]), 3)
        })

    return {
        "success": True,
        "hourly_averages": hourly_stats.to_dict(orient="records"),
        "volatility_peaks": peaks_vol_list
    }


async def get_daily_timing_advisory() -> str:
    """
    Combine quantitative volatility stats with Gemini analysis
    to produce the daily timing advisory.
    """
    try:
        # 1. Fetch tracked coin list
        async with async_session() as session:
            stmt = select(CryptoCoin.symbol).where(CryptoCoin.is_active == True)
            result = await session.execute(stmt)
            coin_symbols = [row[0] for row in result.all()]

        if not coin_symbols:
            return "No active coins tracked in DB to analyze timing."

        # 2. Get statistical hourly peaks
        stats = await get_hourly_volatility_stats()
        
        # 3. Request Gemini advisory with stats injected
        from services.gemini_brain import get_gemini_model
        model = get_gemini_model()
        if not model:
            # Fallback markdown advisory if Gemini is not set up
            fallback = "### 🕒 Daily Timing Advisory (Technical Volatility)\n\n"
            if stats.get("success"):
                fallback += "Based on the last 30 days of technical data, here are the peak volatility hours (IST):\n"
                for peak in stats["volatility_peaks"]:
                    fallback += f"- **{peak['hour_ist']} IST** (Average volatility: {peak['avg_volatility_pct']}%)\n"
                fallback += "\n*Note: Setup the Gemini API key in `backend/.env` to get full AI tactical analysis of session setups.*"
            else:
                fallback += "Insufficient data to calculate timing peaks. Let the bot run for a few cycles to accumulate historical data."
            return fallback

        # Format stats context for prompt
        stats_context = ""
        if stats.get("success"):
            stats_context = "Here is the statistical peak volatility hours extracted from database:\n"
            for p in stats["volatility_peaks"]:
                stats_context += f"- Hour: {p['hour_ist']} IST, Average Intraday Volatility: {p['avg_volatility_pct']}%\n"

        prompt = f"""
        You are the AI timing advisor for an automated crypto trading bot operating within Indian Standard Time (IST).
        The bot is configured to trade between 9:00 AM and 12:00 AM IST.

        Tracked Coins: {", ".join(coin_symbols)}

        {stats_context}

        Please provide a concise, data-backed timing advisory report (formatted in Markdown) for the user.
        Include:
        1. **Intraday Volatility Analysis**: Interpret the peak hours listed above and explain how they relate to global market sessions (e.g. London open, NY open).
        2. **Tactical Action Windows**: Recommend 2 specific windows during our active hours (9 AM - 12 AM IST) where trading signals are most reliable.
        3. **Risk Management Tip**: Warn about specific hours where bid-ask spreads might widen or fakeouts are common.
        """

        response = await asyncio.to_thread(model.generate_content, prompt)
        return response.text if response else "Unable to generate daily timing advisory."

    except Exception as e:
        logger.error("daily_timing_advisory_failed", error=str(e))
        return f"Error compiling timing advisory: {str(e)}"
