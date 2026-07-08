import asyncio
from fastapi import APIRouter
from models.signal import SignalResponse, ETFSignal
from services.signal_engine import calculate_signals
from datetime import datetime
import pytz

router = APIRouter()
IST = pytz.timezone('Asia/Kolkata')

TRACKED_ETFS = ["NIFTYBEES", "GOLDBEES", "ITBEES", "JUNIORBEES", "LIQUIDBEES"]

@router.get("/", response_model=SignalResponse)
async def get_all_signals():
    # Calculate all signals in parallel
    tasks = [calculate_signals(symbol) for symbol in TRACKED_ETFS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    signals = []
    errors = []
    
    for symbol, result in zip(TRACKED_ETFS, results):
        if isinstance(result, Exception):
            errors.append(f"Error for {symbol}: {str(result)}")
        else:
            signals.append(result)
    
    return SignalResponse(
        success=len(signals) > 0,
        data=signals if signals else None,
        error="; ".join(errors) if errors else None,
        timestamp=datetime.now(IST)
    )

@router.get("/{symbol}")
async def get_signal(symbol: str):
    try:
        signal = await calculate_signals(symbol)
        return SignalResponse(
            success=True,
            data=[signal],
            timestamp=datetime.now(IST)
        )
    except Exception as e:
        return SignalResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now(IST)
        )
