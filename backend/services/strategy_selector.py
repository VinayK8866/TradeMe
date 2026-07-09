"""
Strategy Selector — Dynamic Strategy Picker
--------------------------------------------
Looks at current market conditions and the output of all 4 strategies,
then picks the most appropriate one for this coin at this moment.

Also provides consensus scoring: when multiple strategies agree,
confidence is boosted. When they disagree, confidence is penalized.
"""

import structlog

logger = structlog.get_logger()


# ─── Strategy → Market Condition Mapping ────────────────────────────────────────

# Primary fit: which strategy works best in each condition
STRATEGY_FIT = {
    "trending_up": ["Momentum", "MACD"],           # Ride the trend
    "trending_down": ["MACD", "Mean Reversion"],   # MACD for timing exits, MR for bounce
    "ranging": ["Mean Reversion", "MACD"],         # Oscillate around mean
    "squeeze": ["Breakout", "MACD"],               # Anticipate the breakout
    "unknown": ["MACD"],                           # Default to MACD when uncertain
}


def select_strategy(market_condition: dict, strategy_results: dict) -> str:
    """
    Pick the best strategy for the current market condition.

    Logic:
    1. Get the preferred strategy order for this market condition
    2. Among preferred strategies, pick the one with the highest confidence
    3. If preferred strategies have low confidence (<40), fall back to MACD
    4. Return strategy name
    """
    condition = market_condition.get("condition", "unknown")
    preferred_order = STRATEGY_FIT.get(condition, ["MACD"])

    # Score each preferred strategy
    best_strategy = None
    best_confidence = -1

    for strategy_name in preferred_order:
        if strategy_name not in strategy_results:
            continue
        result = strategy_results[strategy_name]
        confidence = result.get("confidence", 0)
        if confidence > best_confidence:
            best_confidence = confidence
            best_strategy = strategy_name

    # Fallback: if best preferred strategy has low confidence, try MACD
    if best_confidence < 40 and "MACD" not in preferred_order:
        macd_confidence = strategy_results.get("MACD", {}).get("confidence", 0)
        if macd_confidence >= best_confidence:
            best_strategy = "MACD"
            best_confidence = macd_confidence
            logger.debug("strategy_fallback_to_macd", condition=condition, macd_confidence=macd_confidence)

    # Final fallback
    if not best_strategy:
        best_strategy = "MACD"

    logger.debug(
        "strategy_selected",
        condition=condition,
        selected=best_strategy,
        confidence=best_confidence,
        preferred_order=preferred_order,
    )
    return best_strategy


def get_consensus(strategy_results: dict) -> dict:
    """
    Analyze agreement/disagreement across all 4 strategies.
    Returns consensus signal, agreement score, and breakdown.

    Used to adjust the final confidence:
    - All 4 agree → +15 confidence bonus
    - 3 agree → +8 bonus
    - 2 agree → no change
    - Split → -10 penalty
    """
    signals = [r["signal"] for r in strategy_results.values()]
    buy_count = signals.count("BUY")
    sell_count = signals.count("SELL") + signals.count("AVOID")
    hold_count = signals.count("HOLD") + signals.count("WATCH")

    if buy_count >= 3:
        consensus = "BUY"
        agreement_score = buy_count
        confidence_adjustment = 15 if buy_count == 4 else 8
    elif sell_count >= 3:
        consensus = "AVOID"
        agreement_score = sell_count
        confidence_adjustment = 0  # Don't boost on avoids to be conservative
    elif buy_count == 2 and sell_count <= 1:
        consensus = "WATCH"
        agreement_score = 2
        confidence_adjustment = 0
    elif sell_count >= 2 and buy_count == 0:
        consensus = "AVOID"
        agreement_score = sell_count
        confidence_adjustment = -5
    elif buy_count == sell_count:
        consensus = "HOLD"
        agreement_score = 0
        confidence_adjustment = -10  # Disagreement penalty
    else:
        consensus = "WATCH"
        agreement_score = max(buy_count, sell_count, hold_count)
        confidence_adjustment = 0

    return {
        "consensus_signal": consensus,
        "buy_votes": buy_count,
        "sell_votes": sell_count,
        "hold_votes": hold_count,
        "agreement_score": agreement_score,
        "confidence_adjustment": confidence_adjustment,
        "all_strategy_signals": {name: r["signal"] for name, r in strategy_results.items()},
    }


def apply_consensus_adjustment(base_confidence: int, consensus: dict) -> int:
    """Apply the consensus confidence adjustment, capped at 0–100."""
    adjusted = base_confidence + consensus["confidence_adjustment"]
    return max(0, min(100, adjusted))
