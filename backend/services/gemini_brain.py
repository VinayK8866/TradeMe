"""
Gemini Brain — AI Trading Brain
--------------------------------
Integrates Google Gemini Pro for pre-trade scoring, trade explanations,
failure learning, and timing advisories.

Provides a robust fallback mechanism if GOOGLE_API_KEY is not configured
or if the Gemini API call fails.
"""

import os
import json
import asyncio
import structlog
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

import google.generativeai as genai
from sqlalchemy import select, update
from db.database import async_session
from models.crypto_models import TradeMemory, CryptoTrade

logger = structlog.get_logger()

# ─── API Setup & Configuration ───────────────────────────────────────────────

api_key = os.getenv("GOOGLE_API_KEY")
has_gemini = False

if api_key and api_key != "your_gemini_api_key_here" and len(api_key.strip()) > 0:
    try:
        genai.configure(api_key=api_key)
        # Check if the key works by querying models, or just use it
        has_gemini = True
        logger.info("gemini_brain_configured", status="active")
    except Exception as e:
        logger.error("gemini_brain_configuration_failed", error=str(e))
else:
    logger.warning("gemini_brain_not_configured", reason="GOOGLE_API_KEY is empty or default")


def get_gemini_model() -> Optional[genai.GenerativeModel]:
    """Retrieve the Gemini model instance if configured."""
    if not has_gemini:
        return None
    # Using gemini-1.5-flash as it is fast, cheap, and very capable
    return genai.GenerativeModel('gemini-1.5-flash')


# ─── Pre-Trade Scorer & Analysis ─────────────────────────────────────────────

async def get_recent_lessons_to_avoid() -> List[str]:
    """
    Fetch the last 15 lessons or patterns to avoid from TradeMemory.
    We prioritize trades that resulted in a LOSS or have avoid patterns.
    """
    try:
        async with async_session() as session:
            stmt = (
                select(TradeMemory)
                .where(
                    (TradeMemory.outcome == "LOSS") | 
                    (TradeMemory.avoid_pattern != None) | 
                    (TradeMemory.lesson != None)
                )
                .order_by(TradeMemory.created_at.desc())
                .limit(15)
            )
            result = await session.execute(stmt)
            memories = result.scalars().all()
            
            lessons = []
            for m in memories:
                lesson_str = f"- Coin: {m.symbol} | Strategy: {m.strategy_used} | Outcome: {m.outcome} (PnL: {m.pnl_percent}%)"
                if m.lesson:
                    lesson_str += f"\n  Lesson: {m.lesson}"
                if m.avoid_pattern:
                    lesson_str += f"\n  Pattern to Avoid: {m.avoid_pattern}"
                lessons.append(lesson_str)
            return lessons
    except Exception as e:
        logger.error("failed_to_fetch_lessons_to_avoid", error=str(e))
        return []


async def analyze_pre_trade(
    symbol: str,
    strategy: str,
    base_confidence: int,
    indicators: dict,
    market_condition: dict,
) -> Tuple[int, str]:
    """
    Use Gemini to score the trade (0-100) and generate a brief reasoning note.
    Checks the proposed signal against recent failure patterns.
    """
    # Fetch lessons learned from database to pass into context
    lessons = await get_recent_lessons_to_avoid()
    lessons_context = "\n".join(lessons) if lessons else "No previous trade memories logged yet."

    # If Gemini is not set up, fallback immediately
    model = get_gemini_model()
    if not model:
        logger.info("gemini_scorer_fallback", symbol=symbol, reason="Gemini not configured")
        return base_confidence, "Gemini key not configured. Using default technical signal confidence."

    prompt = f"""
    You are the AI trading brain of an automated crypto trading bot.
    Your task is to analyze a proposed BUY signal, evaluate it against technical indicators, current market state, and recent trade memory (lessons learned from losses), and return:
    1. An adjusted confidence score (0-100)
    2. A brief, 1-2 sentence explanation of your decision (this will be the pre-trade note).

    --- INPUT DETAILS ---
    Coin Symbol: {symbol}
    Proposed Strategy: {strategy}
    Base Technical Confidence: {base_confidence}%
    Current Indicators: {json.dumps(indicators)}
    Market Condition: {json.dumps(market_condition)}

    --- RECENT BOT LESSONS / PATTERNS TO AVOID ---
    {lessons_context}

    --- RULES ---
    1. If the current market conditions or indicators match any avoid patterns or display warning signs (e.g. buying a coin in a heavy downtrend with weak ADX/volume, high RSI indicating overbought, or mean reversion signal in a strongly trending market), lower the confidence score.
    2. If indicators align perfectly with the strategy, you may increase or maintain the confidence score.
    3. If the score falls below 60%, the bot will reject the trade, so be appropriately cautious.

    Return your output in strict JSON format matching this schema:
    {{
      "confidence": [integer between 0 and 100],
      "reasoning": "[1-2 sentences explaining why the score was kept/adjusted]"
    }}
    Do not include any markdown formatting or surrounding text, just the raw JSON block.
    """

    try:
        response = await asyncio.to_thread(
            model.generate_content,
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        text = response.text.strip() if response else ""
        data = json.loads(text)
        
        confidence = int(data.get("confidence", base_confidence))
        # Ensure confidence bounds
        confidence = max(0, min(100, confidence))
        reasoning = data.get("reasoning", "Signal approved by Gemini Brain.")
        
        logger.info(
            "gemini_pre_trade_scored",
            symbol=symbol,
            base=base_confidence,
            adjusted=confidence,
            reasoning=reasoning
        )
        return confidence, reasoning
    except Exception as e:
        logger.error("gemini_pre_trade_failed", symbol=symbol, error=str(e))
        return base_confidence, f"Gemini scoring failed: {str(e)[:100]}. Using technical signal."


# ─── Post-Trade Analysis & Explanations ──────────────────────────────────────

async def analyze_trade_outcome(trade_id: int) -> bool:
    """
    Triggered asynchronously after a trade closes.
    Uses Gemini to fill in what_worked, what_failed, lesson, and avoid_pattern
    in the TradeMemory table.
    """
    async with async_session() as session:
        # Load trade and memory
        t_stmt = select(CryptoTrade).where(CryptoTrade.id == trade_id)
        t_res = await session.execute(t_stmt)
        trade = t_res.scalar_one_or_none()

        m_stmt = select(TradeMemory).where(TradeMemory.trade_id == trade_id)
        m_res = await session.execute(m_stmt)
        memory = m_res.scalar_one_or_none()

    if not trade or not memory:
        logger.error("post_trade_analysis_missing_records", trade_id=trade_id)
        return False

    model = get_gemini_model()
    if not model:
        # Fallback if no Gemini key: insert simple placeholders
        logger.info("gemini_post_trade_fallback", trade_id=trade_id)
        async with async_session() as session:
            await session.execute(
                update(TradeMemory)
                .where(TradeMemory.trade_id == trade_id)
                .values(
                    what_worked=f"Strategy {trade.strategy_used} executed successfully.",
                    what_failed="N/A (AI brain not configured for feedback)",
                    lesson="Trade closed. Setup Gemini API key for detailed learning analysis.",
                    avoid_pattern="None registered."
                )
            )
            await session.commit()
        return True

    # Assemble trade context
    pnl_pct = float(trade.pnl_percent or 0)
    outcome = "PROFIT" if pnl_pct > 0 else ("LOSS" if pnl_pct < 0 else "BREAKEVEN")
    duration = memory.holding_duration_minutes or 0

    prompt = f"""
    You are the AI trading brain of an automated crypto trading bot.
    A trade has just closed. Analyze the trade details and extract lessons for the bot's memory.

    --- TRADE INFORMATION ---
    Coin Symbol: {trade.symbol}
    Side/Action: BUY and then closed via SELL
    Strategy Used: {trade.strategy_used}
    Signal Confidence: {trade.signal_confidence}%
    Entry Price: INR {float(trade.price_inr):,.4f}
    Outcome: {outcome}
    PnL: {pnl_pct}% (INR {float(trade.pnl_inr or 0):,.2f})
    Duration: {duration} minutes
    Close Reason: {trade.close_reason}
    Indicators at Entry: {json.dumps(memory.indicators_at_entry)}
    Market Conditions at Entry: {json.dumps(memory.market_conditions)}

    --- TASK ---
    Review this trade carefully. In retrospect, evaluate:
    1. What worked: What indicators, conditions, or timing factors made this trade profitable (or protected capital)?
    2. What failed: What indicators did we misinterpret, or what market shift happened that caused the loss/limitations?
    3. Lesson: A concise, actionable, one-line general lesson for future trades.
    4. Avoid pattern: A specific, structured pattern describing what setup/combination of indicators to avoid next time (e.g. "Do not buy BTC using Mean Reversion when ADX > 35 and RSI < 25 unless volume is at least 1.5x average").

    Return your analysis in strict JSON matching this schema:
    {{
      "what_worked": "[detailed explanation]",
      "what_failed": "[detailed explanation]",
      "lesson": "[one-sentence lesson]",
      "avoid_pattern": "[specific setup to avoid in the future]"
    }}
    Do not include any markdown styling or extra text, just the raw JSON block.
    """

    try:
        response = await asyncio.to_thread(
            model.generate_content,
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        text = response.text.strip() if response else ""
        data = json.loads(text)

        async with async_session() as session:
            await session.execute(
                update(TradeMemory)
                .where(TradeMemory.trade_id == trade_id)
                .values(
                    what_worked=data.get("what_worked", ""),
                    what_failed=data.get("what_failed", ""),
                    lesson=data.get("lesson", ""),
                    avoid_pattern=data.get("avoid_pattern", "")
                )
            )
            await session.commit()
            
        logger.info("gemini_post_trade_analyzed", trade_id=trade_id, outcome=outcome, pnl=pnl_pct)
        return True
    except Exception as e:
        logger.error("gemini_post_trade_analysis_failed", trade_id=trade_id, error=str(e))
        return False


# ─── Intraday Volatility & Timing Advisor ─────────────────────────────────────

async def generate_timing_advisory(coin_symbols: List[str]) -> str:
    """
    Daily timing advisory. Analyzes volatility and recommends the best hours of the day
    for trading the given coins (specifically for the configured IST window).
    """
    model = get_gemini_model()
    if not model:
        return "Advisory requires Gemini API configuration. Please set GOOGLE_API_KEY in backend/.env."

    prompt = f"""
    You are the AI timing advisor for an automated crypto trading bot operating within Indian Standard Time (IST).
    The bot is configured to trade between 9:00 AM and 12:00 AM IST.

    Please provide a concise, high-level daily advisory (maximum 3 paragraphs, formatted in Markdown) for the following coins:
    {", ".join(coin_symbols)}

    Discuss:
    1. Volatility peaks: Which specific windows (e.g. 1:30 PM - 4:30 PM IST when Europe opens, or 7:00 PM - 10:00 PM IST when US opens) present the strongest trends and volume.
    2. Trading tactics: Recommended strategy tweaks for the morning session (9:00 AM - 1:00 PM IST) vs. evening session.
    3. Action items: Precise hours of the day where risk is highest or signals are most reliable.

    Be specific to the current standard behavior of the global crypto market. Keep the formatting neat and professional.
    """

    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        return response.text if response else "Unable to generate timing advisory."
    except Exception as e:
        logger.error("timing_advisory_generation_failed", error=str(e))
        return f"Error generating daily timing advisory: {str(e)}"
