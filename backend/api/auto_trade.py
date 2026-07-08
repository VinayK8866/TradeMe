from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.auto_trade import toggle_auto_trade, get_trading_settings
from datetime import datetime
import pytz

router = APIRouter()
IST = pytz.timezone('Asia/Kolkata')

class ToggleRequest(BaseModel):
    symbol: str
    enabled: bool

@router.post("/toggle")
async def toggle(request: ToggleRequest):
    try:
        result = await toggle_auto_trade(request.symbol, request.enabled)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/settings")
async def settings():
    try:
        all_settings = await get_trading_settings()
        return {
            "success": True,
            "data": [
                {
                    "symbol": s.symbol,
                    "auto_trade_enabled": s.auto_trade_enabled,
                    "max_position_size": float(s.max_position_size),
                    "risk_per_trade": float(s.risk_per_trade)
                } for s in all_settings
            ],
            "timestamp": datetime.now(IST)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
