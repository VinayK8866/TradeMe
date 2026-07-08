from fastapi import APIRouter
from services.sentiment import fetch_india_vix
from datetime import datetime
import pytz

router = APIRouter()
IST = pytz.timezone('Asia/Kolkata')

@router.get("/")
async def get_sentiment():
    data = await fetch_india_vix()
    return {
        "success": True,
        "data": data,
        "timestamp": datetime.now(IST)
    }
