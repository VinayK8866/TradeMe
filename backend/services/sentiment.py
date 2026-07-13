import yfinance as yf
from typing import Dict, List
import google.generativeai as genai
import os
import asyncio
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()

# Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"), transport='rest')
model = genai.GenerativeModel('gemini-3.5-flash')

async def fetch_india_vix() -> Dict:
    """
    Fetch India VIX and analyze the trend.
    """
    try:
        # ^INDIAVIX is the correct ticker for Yahoo Finance
        vix_ticker = yf.Ticker("^INDIAVIX")
        # Fetch last 5 days to see trend
        data = vix_ticker.history(period="5d")
        
        if data.empty:
            logger.warn("vix_data_empty", ticker="^INDIAVIX")
            return {"value": 0, "status": "UNKNOWN", "interpretation": "Market sentiment data unavailable"}

        current_vix = float(data.iloc[-1]['Close'])
        prev_vix = float(data.iloc[-2]['Close']) if len(data) > 1 else current_vix
        
        trend = "STABLE"
        if current_vix > prev_vix * 1.05:
            trend = "RISING"
        elif current_vix < prev_vix * 0.95:
            trend = "FALLING"

        # Interpretation Logic
        status = "CALM"
        interpretation = "The market is calm. Good time for steady ETF accumulation."
        
        if current_vix > 25:
            status = "HIGH_FEAR"
            interpretation = "High market volatility! Avoid large orders and use strict stop-losses."
        elif current_vix > 15:
            status = "ELEVATED"
            interpretation = "Market is slightly nervous. Exercise caution with new entries."

        if trend == "RISING":
            interpretation += " Warning: Fear is increasing rapidly."

        return {
            "value": round(current_vix, 2),
            "status": status,
            "trend": trend,
            "interpretation": interpretation
        }
    except Exception as e:
        logger.error("vix_fetch_error", error=str(e))
        return {"value": 0, "status": "ERROR", "interpretation": "Error monitoring market fear"}

async def analyze_news_sentiment(symbol: str, news_text: str) -> Dict:
    """
    Use Gemini to score the sentiment of news text for a specific ETF.
    Score: -1.0 (Very Bearish) to 1.0 (Very Bullish)
    """
    if not news_text or len(news_text) < 50:
        return {"score": 0.0, "label": "NEUTRAL", "summary": "No significant news found for this instrument."}

    prompt = f"""
    Analyze the following recent market news for the Indian ETF '{symbol}'.
    Assign a sentiment score from -1.0 (extremely negative/bearish) to 1.0 (extremely positive/bullish).
    Also provide a one-sentence summary of the prevailing mood.
    
    Format EXACTLY like this:
    SCORE: [number]
    SUMMARY: [one sentence]
    
    News Text:
    {news_text[:2000]} 
    """

    try:
        from services.gemini_brain import get_gemini_model, generate_content_with_fallback
        active_model = get_gemini_model()
        if not active_model:
            return {"score": 0.0, "label": "NEUTRAL", "summary": "Gemini key not configured. Using technical signals only."}
            
        response = await generate_content_with_fallback(active_model, prompt)
        text = response.text if response else ""
        
        # Parse score and summary with fallbacks
        score = 0.0
        summary = "Neutral market mood."
        
        for line in text.split('\n'):
            if line.upper().startswith("SCORE:"):
                try:
                    score = float(line.split(':')[1].strip())
                except: score = 0.0
            if line.upper().startswith("SUMMARY:"):
                summary = line.split(':')[1].strip()

        label = "NEUTRAL"
        if score > 0.2: label = "BULLISH"
        elif score < -0.2: label = "BEARISH"

        return {
            "score": round(score, 2),
            "label": label,
            "summary": summary
        }
    except Exception as e:
        logger.error("sentiment_analysis_error", symbol=symbol, error=str(e))
        # Fallback to technical-only neutral state rather than ERROR to keep UI clean
        return {"score": 0.0, "label": "NEUTRAL", "summary": "AI sentiment analysis currently unavailable. Using technical signals only."}
