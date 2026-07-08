from decimal import Decimal
from datetime import datetime
import pytz
from typing import List, Optional
from models.db_models import UserPortfolio
from db.database import async_session
from sqlalchemy import select, update

IST = pytz.timezone('Asia/Kolkata')

async def place_simulated_order(user_id: str, symbol: str, quantity: float, price: float, side: str):
    """
    Execute a simulated trade and update the user portfolio.
    side: 'BUY' or 'SELL'
    """
    async with async_session() as session:
        # Check if user already has this ETF
        stmt = select(UserPortfolio).where(UserPortfolio.user_id == user_id, UserPortfolio.symbol == symbol)
        result = await session.execute(stmt)
        portfolio_item = result.scalar_one_or_none()

        if side == 'BUY':
            if portfolio_item:
                # Update average price and quantity
                new_quantity = float(portfolio_item.quantity) + quantity
                new_avg_price = (float(portfolio_item.avg_price) * float(portfolio_item.quantity) + price * quantity) / new_quantity
                portfolio_item.quantity = Decimal(str(new_quantity))
                portfolio_item.avg_price = Decimal(str(new_avg_price))
            else:
                # New portfolio item
                new_item = UserPortfolio(
                    user_id=user_id,
                    symbol=symbol,
                    quantity=Decimal(str(quantity)),
                    avg_price=Decimal(str(price))
                )
                session.add(new_item)
        
        elif side == 'SELL':
            if not portfolio_item or float(portfolio_item.quantity) < quantity:
                raise ValueError("Insufficient quantity to sell")
            
            new_quantity = float(portfolio_item.quantity) - quantity
            if new_quantity == 0:
                await session.delete(portfolio_item)
            else:
                portfolio_item.quantity = Decimal(str(new_quantity))

        await session.commit()
        return {"success": True, "symbol": symbol, "side": side, "quantity": quantity, "price": price}

async def get_user_portfolio(user_id: str):
    """
    Retrieve user portfolio.
    """
    async with async_session() as session:
        stmt = select(UserPortfolio).where(UserPortfolio.user_id == user_id)
        result = await session.execute(stmt)
        items = result.scalars().all()
        return items
