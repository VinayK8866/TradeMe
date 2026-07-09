"""
Telegram Bot Service — Command handler and alerting system
------------------------------------------------------------
Implements commands: /status, /holdings, /pause, /resume, /performance,
/toptrades, /worst, /switch, /stop.

Sends proactive alerts for trade openings, closures, and stop-loss triggers.
Robust fallbacks: if token or chat ID is missing, logs warnings and acts as a dummy.
"""

import os
import asyncio
import structlog
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes, ApplicationBuilder
from sqlalchemy import select, update, delete

from db.database import async_session
from models.crypto_models import CryptoBotSettings, CryptoPortfolio, CryptoTrade, CryptoCoin, TradeMemory
from services.portfolio_guard import get_bot_settings, update_bot_settings, calculate_portfolio_value
from services.crypto_paper_trader import get_open_positions, close_paper_position
from services.crypto_data import get_current_prices

logger = structlog.get_logger()

# Config loaded from env
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Singleton Application instances
telegram_app: Optional[Application] = None
telegram_bot: Optional[Bot] = None
bot_task: Optional[asyncio.Task] = None

# ─── Alert Sending ────────────────────────────────────────────────────────────

async def send_telegram_message(text: str) -> bool:
    """
    Send a markdown-formatted Telegram alert to the user.
    Uses direct bot client. Non-blocking & ignores failures gracefully.
    """
    if not TOKEN or not CHAT_ID or TOKEN.strip() == "" or CHAT_ID.strip() == "":
        logger.debug("telegram_alert_skipped_no_config", text=text)
        return False

    try:
        bot = Bot(token=TOKEN)
        # HTML is easier to format robustly than MarkdownV2
        await bot.send_message(
            chat_id=CHAT_ID,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        logger.info("telegram_alert_sent", text=text[:50])
        return True
    except Exception as e:
        logger.error("telegram_alert_failed", error=str(e))
        return False


# ─── Command Handlers ──────────────────────────────────────────────────────────

async def check_user(update: Update) -> bool:
    """Ensure commands only run from the configured chat ID."""
    if not CHAT_ID:
        return True  # If not configured, allow for testing
    chat = update.effective_chat
    if not chat or str(chat.id) != CHAT_ID:
        logger.warning("unauthorized_telegram_access", chat_id=chat.id if chat else None)
        await update.message.reply_text("⛔ Unauthorized. You do not have control over this bot.")
        return False
    return True


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start — Welcome message."""
    if not await check_user(update): return
    welcome = (
        "🤖 <b>Antigravity Crypto Trading Bot</b> active!\n\n"
        "Here are the available commands:\n"
        "📈 /status - Current portfolio value & state\n"
        "💼 /holdings - View current open positions\n"
        "⏸️ /pause - Pause the bot (won't open new positions)\n"
        "▶️ /resume - Resume bot after stop-loss review\n"
        "📊 /performance - P&L stats (last 7 / 30 days)\n"
        "🏆 /toptrades - Best 5 trades\n"
        "📉 /worst - Worst 5 trades\n"
        "🔄 /switch [paper/live] - Change trading mode\n"
        "🚨 /stop - Stop bot + Liquidate all positions"
    )
    await update.message.reply_html(welcome)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status — State, cash, total portfolio value."""
    if not await check_user(update): return
    try:
        settings = await get_bot_settings()
        val = await calculate_portfolio_value(settings.mode)
        
        status_emoji = "🟢 RUNNING" if settings.is_running else "🔴 PAUSED"
        if settings.is_stopped_by_loss:
            status_emoji = "⚠️ CRITICAL (STOPPED BY DRAWDOWN)"

        msg = (
            f"🤖 <b>Bot Status:</b> {status_emoji}\n"
            f"⚙️ <b>Mode:</b> {settings.mode.upper()}\n"
            f"-----------------------------------\n"
            f"💰 <b>Starting Capital:</b> ₹{val['starting_capital_inr']:,.2f}\n"
            f"💼 <b>Total Value:</b> ₹{val['total_value_inr']:,.2f}\n"
            f"💵 <b>Available Cash:</b> ₹{val['cash_inr']:,.2f}\n"
            f"📉 <b>Unrealized P&L:</b> ₹{val['unrealized_pnl_inr']:,.2f} ({val['unrealized_pnl_pct']}%)\n"
            f"📈 <b>Realized P&L:</b> ₹{val['realized_pnl_inr']:,.2f}\n"
            f"🪙 <b>Open Positions:</b> {val['open_count']}"
        )
        await update.message.reply_html(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching status: {e}")


async def cmd_holdings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/holdings — Current positions."""
    if not await check_user(update): return
    try:
        settings = await get_bot_settings()
        val = await calculate_portfolio_value(settings.mode)
        
        if val['open_count'] == 0:
            await update.message.reply_text("💼 No open positions currently.")
            return

        lines = ["<b>Current holdings:</b>\n"]
        for p in val['positions']:
            pnl_color = "🟢" if p['pnl_inr'] >= 0 else "🔴"
            lines.append(
                f"🪙 <b>{p['symbol']}</b> (Qty: {p['quantity']:.4f})\n"
                f"  └ Buy Price: ₹{p['avg_buy_price_inr']:,.2f}\n"
                f"  └ Current: ₹{p['current_price_inr']:,.2f}\n"
                f"  └ Invested: ₹{p['invested_inr']:,.2f}\n"
                f"  └ Stop Loss: ₹{p['stop_loss_price_inr']:,.2f}\n"
                f"  └ P&L: {pnl_color} ₹{p['pnl_inr']:,.2f} ({p['pnl_pct']}%)\n"
            )
        await update.message.reply_html("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching holdings: {e}")


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/pause — Stop bot cycles."""
    if not await check_user(update): return
    settings = await update_bot_settings(is_running=False)
    await update.message.reply_html("⏸️ <b>Bot trading loop paused.</b> Open positions will remain open.")


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/resume — Clear stop-loss triggers and start bot."""
    if not await check_user(update): return
    settings = await get_bot_settings()
    if settings.is_stopped_by_loss:
        await update_bot_settings(is_running=True, is_stopped_by_loss=False, stop_loss_triggered_at=None)
        await update.message.reply_html("▶️ <b>Bot resumed.</b> Drawdown locks cleared.")
    else:
        await update_bot_settings(is_running=True)
        await update.message.reply_html("▶️ <b>Bot trading loop resumed.</b>")


async def cmd_performance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/performance — stats breakdown."""
    if not await check_user(update): return
    try:
        settings = await get_bot_settings()
        
        async with async_session() as session:
            stmt = select(CryptoTrade).where(
                CryptoTrade.mode == settings.mode,
                CryptoTrade.status == "CLOSED",
                CryptoTrade.side == "BUY"
            )
            result = await session.execute(stmt)
            trades = result.scalars().all()

        if not trades:
            await update.message.reply_text("📊 No trades logged yet in this mode.")
            return

        now = datetime.now(timezone.utc)
        
        def calculate_stats(days_limit: int) -> str:
            limit_date = now - timedelta(days=days_limit)
            filtered = [t for t in trades if t.closed_at and t.closed_at.replace(tzinfo=timezone.utc) >= limit_date]
            if not filtered:
                return f"No trades in last {days_limit} days."
            
            wins = [t for t in filtered if (t.pnl_inr or 0) > 0]
            total_pnl = sum(float(t.pnl_inr or 0) for t in filtered)
            win_rate = len(wins) / len(filtered) * 100
            
            return (
                f"<b>Last {days_limit} Days:</b>\n"
                f"  ├ Trades: {len(filtered)}\n"
                f"  ├ Wins: {len(wins)} | Losses: {len(filtered) - len(wins)}\n"
                f"  ├ Win Rate: {win_rate:.1f}%\n"
                f"  └ Net P&L: {'🟢' if total_pnl >= 0 else '🔴'} ₹{total_pnl:,.2f}\n"
            )

        msg = (
            f"📊 <b>Performance Stats ({settings.mode.upper()}):</b>\n\n"
            f"{calculate_stats(7)}\n"
            f"{calculate_stats(30)}"
        )
        await update.message.reply_html(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error compiling performance: {e}")


async def cmd_toptrades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/toptrades — List top 5 profitable trades."""
    if not await check_user(update): return
    try:
        settings = await get_bot_settings()
        async with async_session() as session:
            stmt = (
                select(CryptoTrade)
                .where(CryptoTrade.mode == settings.mode, CryptoTrade.status == "CLOSED", CryptoTrade.side == "BUY")
                .order_by(CryptoTrade.pnl_percent.desc())
                .limit(5)
            )
            result = await session.execute(stmt)
            trades = result.scalars().all()

        if not trades:
            await update.message.reply_text("🏆 No completed trades recorded.")
            return

        lines = ["🏆 <b>Top 5 Profitable Trades:</b>\n"]
        for idx, t in enumerate(trades, 1):
            lines.append(
                f"{idx}. <b>{t.symbol}</b>: 🟢 +{float(t.pnl_percent or 0):.2f}% (+₹{float(t.pnl_inr or 0):,.2f})\n"
                f"   └ Strategy: {t.strategy_used} | Hold: {t.closed_at - t.opened_at if t.closed_at and t.opened_at else 'N/A'}"
            )
        await update.message.reply_html("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_worst(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/worst — List worst 5 trades (for learning/Gemini)."""
    if not await check_user(update): return
    try:
        settings = await get_bot_settings()
        async with async_session() as session:
            stmt = (
                select(CryptoTrade)
                .where(CryptoTrade.mode == settings.mode, CryptoTrade.status == "CLOSED", CryptoTrade.side == "BUY")
                .order_by(CryptoTrade.pnl_percent.asc())
                .limit(5)
            )
            result = await session.execute(stmt)
            trades = result.scalars().all()

        if not trades:
            await update.message.reply_text("📉 No completed trades recorded.")
            return

        lines = ["📉 <b>Worst 5 Performing Trades:</b>\n"]
        for idx, t in enumerate(trades, 1):
            lines.append(
                f"{idx}. <b>{t.symbol}</b>: 🔴 {float(t.pnl_percent or 0):.2f}% (₹{float(t.pnl_inr or 0):,.2f})\n"
                f"   └ Strategy: {t.strategy_used} | Reason: {t.close_reason or 'UNKNOWN'}"
            )
        await update.message.reply_html("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/switch [paper/live] — Switch mode."""
    if not await check_user(update): return
    args = context.args
    if not args or args[0].lower() not in ("paper", "live"):
        await update.message.reply_text("❓ Usage: /switch [paper/live]")
        return

    mode = args[0].lower()
    settings = await get_bot_settings()
    if settings.is_running:
        await update.message.reply_text("⛔ Please pause the bot using /pause before switching modes.")
        return

    if mode == "live" and not settings.graduation_ready:
        await update.message.reply_html(
            f"⛔ <b>Graduation Block:</b> Bot must make &gt;{settings.graduation_target_percent}% profit "
            "consistently in Paper mode before switching to Live."
        )
        return

    await update_bot_settings(mode=mode)
    await update.message.reply_html(f"🔄 <b>Switched mode to {mode.upper()}.</b>")


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stop — Pause bot + Liquidate all positions."""
    if not await check_user(update): return
    try:
        # Pause bot
        await update_bot_settings(is_running=False)
        await update.message.reply_html("🚨 <b>Stopping bot and liquidating all positions...</b>")

        settings = await get_bot_settings()
        open_positions = await get_open_positions(settings.mode)

        if not open_positions:
            await update.message.reply_text("💼 No open positions to liquidate. Bot successfully paused.")
            return

        liquidated = []
        for pos in open_positions:
            # Look up coingecko ID
            async with async_session() as session:
                coin_stmt = select(CryptoCoin).where(CryptoCoin.id == pos.coin_id)
                res = await session.execute(coin_stmt)
                coin = res.scalar_one_or_none()
            
            if coin:
                close_res = await close_paper_position(
                    coin_id=coin.id,
                    symbol=coin.symbol,
                    coingecko_id=coin.coingecko_id,
                    mode=settings.mode,
                    reason="TELEGRAM_EMERGENCY_LIQUIDATION"
                )
                if close_res:
                    liquidated.append(close_res)

        # Build summary
        summary = ["🚨 <b>Emergency liquidation complete:</b>\n"]
        for l in liquidated:
            color = "🟢" if l['pnl_inr'] >= 0 else "🔴"
            summary.append(f"• <b>{l['symbol']}</b>: {color} {l['pnl_pct']}% (₹{l['pnl_inr']:,.2f})")

        await update.message.reply_html("\n".join(summary))
    except Exception as e:
        await update.message.reply_text(f"❌ Error during liquidation: {e}")


# ─── Bot Lifecycle ─────────────────────────────────────────────────────────────

async def init_telegram_bot():
    """Build the python-telegram-bot application."""
    global telegram_app, telegram_bot
    if not TOKEN or TOKEN.strip() == "":
        logger.warning("telegram_bot_init_skipped", reason="TELEGRAM_BOT_TOKEN empty")
        return

    try:
        app = ApplicationBuilder().token(TOKEN).build()

        # Add command handlers
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("holdings", cmd_holdings))
        app.add_handler(CommandHandler("pause", cmd_pause))
        app.add_handler(CommandHandler("resume", cmd_resume))
        app.add_handler(CommandHandler("performance", cmd_performance))
        app.add_handler(CommandHandler("toptrades", cmd_toptrades))
        app.add_handler(CommandHandler("worst", cmd_worst))
        app.add_handler(CommandHandler("switch", cmd_switch))
        app.add_handler(CommandHandler("stop", cmd_stop))

        # Initialise app but don't run_polling blockingly
        await app.initialize()
        telegram_app = app
        telegram_bot = app.bot
        logger.info("telegram_bot_initialized")
    except Exception as e:
        logger.error("telegram_bot_init_failed", error=str(e))


async def start_telegram_bot():
    """Start polling loop in an asyncio task context."""
    global telegram_app, bot_task
    if not telegram_app:
        logger.warning("cannot_start_telegram_bot_not_initialized")
        return

    async def bot_poll():
        try:
            logger.info("telegram_bot_polling_started")
            await telegram_app.start()
            await telegram_app.updater.start_polling()
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("telegram_bot_polling_cancelled")
        except Exception as e:
            logger.error("telegram_bot_polling_error", error=str(e))

    bot_task = asyncio.create_task(bot_poll())


async def stop_telegram_bot():
    """Gracefully shutdown the bot updater."""
    global telegram_app, bot_task
    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass

    if telegram_app:
        logger.info("telegram_bot_shutting_down")
        try:
            await telegram_app.updater.stop()
            await telegram_app.stop()
            await telegram_app.shutdown()
        except Exception as e:
            logger.error("telegram_bot_shutdown_error", error=str(e))
