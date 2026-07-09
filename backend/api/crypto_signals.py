"""
Crypto Signals API — Phase 2
------------------------------
REST endpoints to get trade signals for tracked coins.
GET /api/v1/crypto/signals        → signals for all top-10 coins
GET /api/v1/crypto/signals/{sym}  → detailed signal for one coin
GET /api/v1/crypto/signals/best   → top BUY opportunities ranked by confidence
"""

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query

from services.crypto_signal_engine import calculate_crypto_signal, calculate_all_signals
from services.strategy_selector import get_consensus, apply_consensus_adjustment

logger = structlog.get_logger()
router = APIRouter()


def _build_response(success: bool, data: object, error: Optional[str] = None) -> dict:
    return {
        "success": success,
        "data": data,
        "error": error,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/")
async def get_all_signals():
    """
    GET /api/v1/crypto/signals
    Calculates and returns signals for all top-10 active coins.
    Takes ~10-20s on first call (CoinGecko fetches); subsequent calls use Redis cache.
    """
    logger.info("all_signals_requested")
    try:
        signals = await calculate_all_signals()
        # Sort: BUY first (by confidence desc), then WATCH, then others
        order = {"BUY": 0, "WATCH": 1, "HOLD": 2, "AVOID": 3, "SELL": 4}
        signals.sort(key=lambda s: (order.get(s["signal"], 5), -s["confidence"]))
        return _build_response(success=True, data={"signals": signals, "count": len(signals)})
    except Exception as e:
        logger.error("all_signals_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/best")
async def get_best_opportunities(
    min_confidence: int = Query(default=60, ge=0, le=100),
    limit: int = Query(default=5, ge=1, le=10),
):
    """
    GET /api/v1/crypto/signals/best?min_confidence=60&limit=5
    Returns only BUY signals above the confidence threshold, ranked best first.
    This is what the bot uses to decide which coins to buy.
    """
    signals = await calculate_all_signals()
    opportunities = [
        s for s in signals
        if s["signal"] == "BUY" and s["confidence"] >= min_confidence
    ]
    opportunities.sort(key=lambda s: -s["confidence"])
    opportunities = opportunities[:limit]

    return _build_response(
        success=True,
        data={
            "opportunities": opportunities,
            "count": len(opportunities),
            "min_confidence_used": min_confidence,
            "message": (
                f"Found {len(opportunities)} BUY opportunity(ies) above {min_confidence}% confidence"
                if opportunities
                else f"No strong BUY opportunities found above {min_confidence}% confidence right now"
            ),
        },
    )


@router.get("/{symbol}")
async def get_signal(symbol: str):
    """
    GET /api/v1/crypto/signals/BTC
    Full detailed signal for a single coin — includes all 4 strategy breakdowns,
    market condition analysis, all indicators, and consensus vote.
    """
    symbol = symbol.upper()
    logger.info("single_signal_requested", symbol=symbol)
    try:
        result = await calculate_crypto_signal(symbol)

        # Enrich with consensus across all strategies
        consensus = get_consensus(result["strategy_breakdown"])
        adjusted_confidence = apply_consensus_adjustment(result["confidence"], consensus)

        result["consensus"] = consensus
        result["adjusted_confidence"] = adjusted_confidence

        return _build_response(success=True, data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("single_signal_failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
