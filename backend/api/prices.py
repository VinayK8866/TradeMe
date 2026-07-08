from fastapi import APIRouter, HTTPException
from models.etf import PriceResponse
from services.data_ingestion import fetch_etf_price, fetch_market_news
from datetime import datetime
import pytz

router = APIRouter()
IST = pytz.timezone('Asia/Kolkata')

@router.get("/{symbol}", response_model=PriceResponse)
async def get_price(symbol: str):
    try:
        price_data = await fetch_etf_price(symbol)
        return PriceResponse(
            success=True,
            data=price_data,
            timestamp=datetime.now(IST)
        )
    except Exception as e:
        return PriceResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now(IST)
        )

@router.get("/{symbol}/news")
async def get_news(symbol: str):
    try:
        news_text = await fetch_market_news(symbol)
        return {
            "success": True,
            "data": news_text,
            "timestamp": datetime.now(IST)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now(IST)
        }
