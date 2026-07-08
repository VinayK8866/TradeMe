from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class ETFSignal(BaseModel):
    symbol: str
    signal_type: str  # BUY, HOLD, WATCH, AVOID
    rsi: float
    ma50: float
    ma20: float
    volume_ratio: float
    sentiment_score: Optional[float] = 0.0
    sentiment_label: Optional[str] = "NEUTRAL"
    explanation: Optional[str] = None
    timestamp: datetime

class SignalResponse(BaseModel):
    success: bool
    data: Optional[List[ETFSignal]] = None
    error: Optional[str] = None
    timestamp: datetime
