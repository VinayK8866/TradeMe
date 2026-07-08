from pydantic import BaseModel
from typing import Optional
from decimal import Decimal
from datetime import datetime

class ETFPrice(BaseModel):
    symbol: str
    price: Decimal
    change: Decimal
    change_percent: Decimal
    high: Decimal
    low: Decimal
    volume: int
    timestamp: datetime

class PriceResponse(BaseModel):
    success: bool
    data: Optional[ETFPrice] = None
    error: Optional[str] = None
    timestamp: datetime
