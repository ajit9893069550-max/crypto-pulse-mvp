import asyncio
import logging
import os
import gc
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from supabase import create_client, Client
from dotenv import load_dotenv

# --- UPDATED IMPORTS ---
from strategy_engine import StrategyEngine 
from new_alert_engine import analyze_asset, check_alerts, close_exchange

load_dotenv()

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Worker")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not all([SUPABASE_URL, SUPABASE_KEY, TELEGRAM_BOT_TOKEN]):
    logger.critical("❌ Missing Secrets! Check .env file.")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
# Symbols to scan (Standard)
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT', 'BNB/USDT', 'DOGE/USDT'] 
TIMEFRAMES = ['15m', '1h', '4h']

# ==========================================================
# 1. TELEGRAM HANDSHAKE (/start user_id)
# ==========================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Links user Telegram ID to their Web Account."""
    chat_id = update.effective_chat.id
    if context.args:
        user_uuid = context.args[0]
        try:
            # Update user profile with chat_id
            response = supabase.table('users').update({'telegram_chat_id': str(chat_id)})\
                .eq('user_uuid', user_uuid).execute()
            
            if response.data:
                await update.message.reply_text("✅ *Linked!* You will now receive alerts here.", parse_mode='Markdown')
                logger.info(f"Linked User {user_uuid} to Chat {chat_id}")
            else:
                await update.message.reply_text("❌ Account not found. Please login to the dashboard first.")
        except Exception as e:
            logger.error(f"Link Error: {e}")
            await update.message.reply_text("⚠️ Database error.")
    else:
        await update.message.reply_text("👋 Welcome! Go to your Dashboard and click 'Link Telegram Bot'.")

# ==========================================================
# 2. ALERT DISPATCHER (Runs Every 60 Seconds)
# ==========================================================
async def alert_loop():
    """Watches for Price Targets (Live) and DB Signals (Delayed)."""
    logger.info("👀 Alert Watcher Started (60s cycle)...")
    
    while True:
        try:
            # This function (from new_alert_engine.py) handles:
            # A. Checking Live Price vs Target Price
            # B. Checking Database for new Technical Signals
            await check_alerts()
            
        except Exception as e:
            logger.error(f"Alert Loop Error: {e}")
            
        # Run every 60 seconds to catch Price Targets quickly
        await asyncio.sleep(60)

# ==========================================================
# 3. MARKET SCANNER (Runs Every 15 Minutes)
# ==========================================================
async def scanner_loop():
    """Scans market data aligned to 15-minute candles."""
    logger.info("📉 Market Scanner Started (15m alignment)...")
    
    while True:
        try:
            # 1. Calculate wait time for next 15m candle (00, 15, 30, 45)
            # This ensures we scan exactly when a candle closes
            now = datetime.now()
            minutes_to_next = 15 - (now.minute % 15)
            next_mark = now.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_next)
            wait_time = (next_mark - now).total_seconds()

            # If we are very close (e.g. < 5s), scan immediately, otherwise wait
            if wait_time > 5:
                logger.info(f"Scanner sleeping {int(wait_time)}s until next candle...")
                await asyncio.sleep(wait_time)
                # Small buffer to ensure exchange has processed the candle close
                await asyncio.sleep(2) 
            
            # 2. Run Technical Analysis Scan
            logger.info("--- Starting 15m Scan Cycle ---")
            for symbol in SYMBOLS:
                for tf in TIMEFRAMES:
                    try:
                        # Calls engine logic to calculate indicators & save to DB
                        await analyze_asset(symbol, tf)
                        await asyncio.sleep(0.5) # Rate limit protection
                    except Exception as e:
                        logger.error(f"Scan Error {symbol}: {e}")
            
            logger.info("--- Scan Cycle Complete ---")
            
            # Buffer sleep to prevent double-triggering in the same minute
            await asyncio.sleep(20) 
            
        except Exception as e:
            logger.error(f"Scanner Crash: {e}")
            await asyncio.sleep(60)

# ==========================================================
# 4. STRATEGY ENGINE (Runs Every Hour at XX:02)
# ==========================================================
async def strategy_loop():
    """Runs complex strategies every hour at minute 02 (e.g., 09:02, 10:02)."""
    logger.info("♟️ Strategy Engine Started (Aligned to XX:02)...")
    
    while True:
        try:
            # 1. Calculate time until next XX:02
            now = datetime.now()
            
            # Target time is the 2nd minute of the current hour
            target_time = now.replace(minute=2, second=0, microsecond=0)
            
            # If we are already past XX:02 today, move to next hour
            if now >= target_time:
                target_time += timedelta(hours=1)
                
            wait_seconds = (target_time - now).total_seconds()
            
            logger.info(f"♟️ Strategy sleeping {int(wait_seconds)}s until {target_time.strftime('%H:%M')}...")
            await asyncio.sleep(wait_seconds)
            
            # --- AGGRESSIVE MEMORY MANAGEMENT START ---
            # 2. CREATE ENGINE TEMPORARILY
            logger.info("⚙️ Initializing Engine...")
            engine = StrategyEngine() 
            
            # 3. Run All Strategies (Unlock + Bullish 200MA)
            await engine.run_all()
            
            # 4. DESTROY ENGINE & CLEANUP
            logger.info("🗑️ Destroying Engine to free RAM...")
            del engine 
            gc.collect() # Force RAM release
            # --- AGGRESSIVE MEMORY MANAGEMENT END ---
            
            # 5. Buffer to ensure we don't double-trigger (sleep 60s)
            await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"Strategy Loop Error: {e}")
            await asyncio.sleep(60)

# ==========================================================
# 5. MAIN ENTRY POINT
# ==========================================================
async def main():
    # Setup Telegram Bot Listener
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    logger.info("✅ Telegram Bot Listener Active.")

    # Run Scanner, Alerter, and Strategy Engine Concurrently
    try:
        await asyncio.gather(
            scanner_loop(),  # The 15-minute Technical Scan
            alert_loop(),    # The 60-second Alert/Price Check
            strategy_loop()  # The Hourly Strategy Check (Updated)
        )
    except Exception as e:
        logger.error(f"Global Crash: {e}")
    finally:
        await application.stop()
        await close_exchange()

if __name__ == "__main__":
    try:
        # Windows Loop Policy Fix (For Local Testing)
        if os.name == 'nt':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
