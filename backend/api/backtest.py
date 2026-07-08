from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.backtest_engine import run_backtest
from datetime import datetime
import pytz

router = APIRouter()
IST = pytz.timezone('Asia/Kolkata')

class BacktestRequest(BaseModel):
    symbol: str
    cash: int = 100000

class BacktestResponse(BaseModel):
    success: bool
    data: dict
    timestamp: datetime

@router.post("/", response_model=BacktestResponse)
async def execute_backtest(request: BacktestRequest):
    try:
        results = await run_backtest(request.symbol, cash=request.cash)
        return BacktestResponse(
            success=True,
            data=results,
            timestamp=datetime.now(IST)
        )
    except Exception as e:
        return BacktestResponse(
            success=False,
            data={"error": str(e)},
            timestamp=datetime.now(IST)
        )
