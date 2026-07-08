import os
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()
from typing import Optional
from models.signal import ETFSignal
from services.data_ingestion import fetch_market_news
import structlog

logger = structlog.get_logger()

# Configure Gemini
api_key = os.getenv("GOOGLE_API_KEY", "")
if api_key:
    genai.configure(api_key=api_key)

async def explain_signal(signal: ETFSignal) -> str:
    """
    Generate a plain-English explanation for a technical signal using Google Gemini,
    now incorporating real-time market context and news.
    """
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        return "Google API key not configured. Cannot generate AI explanation."

    # Fetch real-time market context
    market_news = await fetch_market_news(signal.symbol)

    prompt = f"""
    You are an expert Indian stock market mentor helping a complete beginner.
    Explain the following trading signal for the ETF {signal.symbol}:
    
    - Signal: {signal.signal_type}
    - RSI: {signal.rsi} (Relative Strength Index)
    - MA50: {signal.ma50} (50-day Moving Average)
    - Volume Ratio: {signal.volume_ratio}x (compared to 20-day average)
    
    Recent Market Context for {signal.symbol}:
    {market_news}
    
    Context:
    - BUY: Good entry point based on momentum and trend.
    - AVOID: High risk or weak trend.
    - HOLD: Trend is stable but not a new entry.
    - WATCH: Emerging trend, keep an eye.
    
    Requirements:
    1. Keep it under 120 words.
    2. Use very simple, friendly language.
    3. Connect the technical numbers (RSI/MA) with the news if relevant.
    4. Explain what this means for their hard-earned money.
    5. Mention a specific stop-loss recommendation if it's a BUY signal.
    6. Be encouraging but emphasize that this is for educational practice (SEBI compliance).
    """

    try:
        # Initialize model
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Generate content
        response = await model.generate_content_async(prompt)
        
        return response.text.strip()
    except Exception as e:
        logger.error("failed_to_get_ai_explanation", error=str(e))
        return f"Sorry, I couldn't generate a deep analysis right now. Technical Signal: {signal.signal_type}."
