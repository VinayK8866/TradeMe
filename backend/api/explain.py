from fastapi import APIRouter, HTTPException
from models.signal import ETFSignal
from services.explain import explain_signal
from pydantic import BaseModel
from datetime import datetime
import pytz

router = APIRouter()
IST = pytz.timezone('Asia/Kolkata')

class ExplainRequest(BaseModel):
    signal: ETFSignal

class ExplainResponse(BaseModel):
    success: bool
    explanation: str
    timestamp: datetime

@router.post("/", response_model=ExplainResponse)
async def get_explanation(request: ExplainRequest):
    try:
        explanation = await explain_signal(request.signal)
        return ExplainResponse(
            success=True,
            explanation=explanation,
            timestamp=datetime.now(IST)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
