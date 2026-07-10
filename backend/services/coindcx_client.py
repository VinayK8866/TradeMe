"""
CoinDCX API Client — Live Trading Adapter
-------------------------------------------
Interacts with the CoinDCX REST API for executing real trades,
monitoring order fills, and checking account balances.

Uses HMAC-SHA256 signature calculations based on API Key and Secret.
Provides simulated fallback behavior if credentials are not configured.
"""

import os
import time
import hmac
import hashlib
import json
import httpx
import structlog
from typing import Dict, List, Optional
from decimal import Decimal
from fastapi import HTTPException
from datetime import datetime

logger = structlog.get_logger()

COINDCX_BASE_URL = "https://api.coindcx.com"
COINDCX_API_KEY = os.getenv("COINDCX_API_KEY")
COINDCX_API_SECRET = os.getenv("COINDCX_API_SECRET")

# Check if client can go live
is_credentials_configured = bool(
    COINDCX_API_KEY and 
    COINDCX_API_SECRET and 
    COINDCX_API_KEY != "your_coindcx_api_key_here" and 
    COINDCX_API_SECRET != "your_coindcx_api_secret_here"
)

if not is_credentials_configured:
    logger.warning("coindcx_client_in_mock_mode", reason="CoinDCX API Key/Secret is missing or default")


def _generate_signature(secret: str, body_str: str) -> str:
    """Generate HMAC-SHA256 signature for private endpoints."""
    signature = hmac.new(
        secret.encode('utf-8'),
        body_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature


async def _coindcx_post_request(endpoint: str, payload: dict) -> dict:
    """Helper to perform signed POST request to CoinDCX."""
    if not is_credentials_configured:
        raise ValueError("CoinDCX API key/secret not configured in environment")

    url = f"{COINDCX_BASE_URL}{endpoint}"
    # Payload must contain timestamp in ms
    payload["timestamp"] = int(time.time() * 1000)
    body_str = json.dumps(payload, separators=(',', ':'))

    signature = _generate_signature(COINDCX_API_SECRET, body_str)

    headers = {
        "Content-Type": "application/json",
        "X-AUTH-APIKEY": COINDCX_API_KEY,
        "X-AUTH-SIGNATURE": signature
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, data=body_str, headers=headers, timeout=10.0)
        
        if response.status_code != 200:
            logger.error("coindcx_request_failed", status=response.status_code, text=response.text, endpoint=endpoint)
            raise HTTPException(
                status_code=response.status_code, 
                detail=f"CoinDCX API call failed: {response.text}"
            )
            
        return response.json()


# ─── Public API Wrapper ───────────────────────────────────────────────────────

async def get_coindcx_ticker() -> List[Dict]:
    """Retrieve all market tickers from CoinDCX."""
    url = f"{COINDCX_BASE_URL}/exchange/ticker"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=5.0)
        if response.status_code == 200:
            return response.json()
        return []


# ─── Private Endpoints / Balances ─────────────────────────────────────────────

async def get_coindcx_balances() -> List[Dict]:
    """
    Fetch all user account balances.
    Returns list of assets with quantity and locked balances.
    """
    if not is_credentials_configured:
        # Mock mode fallback for testing
        logger.debug("mocking_coindcx_balances")
        return [
            {"currency": "INR", "balance": "5000.00", "locked_balance": "0.00"},
            {"currency": "BTC", "balance": "0.00", "locked_balance": "0.00"},
            {"currency": "ETH", "balance": "0.00", "locked_balance": "0.00"},
        ]

    try:
        data = await _coindcx_post_request("/exchange/v1/users/balances", {})
        return data
    except Exception as e:
        logger.error("failed_to_fetch_coindcx_balances", error=str(e))
        raise


# ─── Order Execution ──────────────────────────────────────────────────────────

async def place_coindcx_order(
    side: str,         # "buy" or "sell"
    market: str,       # e.g., "BTCINR"
    quantity: float,
    price: Optional[float] = None
) -> Dict:
    """
    Submit a trade order to CoinDCX.
    If price is provided, places a limit_order. Otherwise places a market_order.
    """
    side = side.lower()
    order_type = "limit_order" if price is not None else "market_order"

    if not is_credentials_configured:
        # Mock execution helper
        logger.info(
            "mocking_coindcx_order_execution", 
            side=side, 
            market=market, 
            qty=quantity, 
            price=price
        )
        # Simulate instant full fill
        simulated_price = price if price else 5000000.0  # arbitrary mock price
        return {
            "success": True,
            "id": f"mock_order_{int(time.time())}",
            "market": market,
            "side": side,
            "order_type": order_type,
            "total_quantity": quantity,
            "price_per_unit": simulated_price,
            "status": "filled",
            "fee": round(quantity * simulated_price * 0.002, 2),  # standard 0.2% fee
            "created_at": datetime.utcnow().isoformat()
        }

    payload = {
        "side": side,
        "order_type": order_type,
        "market": market,
        "total_quantity": quantity,
    }
    if price is not None:
        payload["price_per_unit"] = price

    try:
        response = await _coindcx_post_request("/exchange/v1/orders/create", payload)
        # Sample response payload structures can be checked in order updates
        logger.info("coindcx_order_placed_successfully", order_id=response.get("id"), market=market)
        return response
    except Exception as e:
        logger.error("failed_to_place_coindcx_order", market=market, side=side, error=str(e))
        raise


async def cancel_coindcx_order(order_id: str) -> Dict:
    """Cancel an open order."""
    if not is_credentials_configured:
        return {"success": True, "id": order_id, "status": "cancelled"}

    payload = {"id": order_id}
    try:
        return await _coindcx_post_request("/exchange/v1/orders/cancel", payload)
    except Exception as e:
        logger.error("failed_to_cancel_coindcx_order", order_id=order_id, error=str(e))
        raise


async def get_coindcx_order_status(order_id: str) -> Dict:
    """Fetch detail / execution status for a specific order."""
    if not is_credentials_configured:
        return {"id": order_id, "status": "filled"}

    payload = {"id": order_id}
    try:
        return await _coindcx_post_request("/exchange/v1/orders/status", payload)
    except Exception as e:
        logger.error("failed_to_fetch_coindcx_order_status", order_id=order_id, error=str(e))
        raise
