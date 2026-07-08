from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Dict
import asyncio
import json
from services.data_ingestion import fetch_etf_price
import structlog

logger = structlog.get_logger()
router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()

@router.websocket("/ws/prices")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Poll prices and broadcast to all connected clients
            # We now use the cache-enabled fetcher which simulates live movement
            TRACKED_ETFS = ["NIFTYBEES", "GOLDBEES", "ITBEES", "JUNIORBEES", "LIQUIDBEES"]
            updates = []
            for symbol in TRACKED_ETFS:
                try:
                    # use_cache=True allows the internal simulation logic to kick in
                    price_data = await fetch_etf_price(symbol, use_cache=True)
                    updates.append({
                        "symbol": price_data.symbol,
                        "price": float(price_data.price),
                        "change": float(price_data.change),
                        "change_percent": float(price_data.change_percent),
                        "timestamp": price_data.timestamp.isoformat()
                    })
                except Exception as e:
                    logger.error("ws_fetch_error", symbol=symbol, error=str(e))
                    continue
            
            await websocket.send_text(json.dumps({
                "type": "PRICE_UPDATE", 
                "data": updates,
                "is_simulated": True # Visual cue for the frontend
            }))
            
            # 1 second update frequency for a "pro" feel
            await asyncio.sleep(1) 
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("websocket_error", error=str(e))
        manager.disconnect(websocket)
