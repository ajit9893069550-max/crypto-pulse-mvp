import asyncio
import logging
import os
import gc
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from supabase import create_client, Client
from dotenv import load_dotenv

# --- IMPORTS ---
# We now only use signal_engine (which contains ALL strategies)
import signal_engine  

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

# Symbols to scan
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT', 'BNB/USDT', 'DOGE/USDT', 'AVAX/USDT', 'LINK/USDT', 'MATIC/USDT'] 

# Timeframes to scan (Updated to 1h, 4h, 1d)
TIMEFRAMES = ['1h', '4h', '1d'] 

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
            # Call the signal engine to check alerts
            await signal_engine.check_alerts()
            
        except Exception as e:
            logger.error(f"Alert Loop Error: {e}")
            
        # Run every 60 seconds to catch Price Targets quickly
        await asyncio.sleep(60)

# ==========================================================
# 3. MARKET SCANNER (Runs Every HOUR at XX:00)
# ==========================================================
async def scanner_loop():
    """Scans market data aligned to Hourly candles."""
    logger.info("📉 Hourly Market Scanner Started...")
    
    while True:
        try:
            # 1. Calculate wait time for next Hour (XX:00)
            now = datetime.now()
            # Calculate minutes until the next hour
            minutes_to_next = 60 - now.minute
            next_mark = now.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_next)
            
            # If we are slightly past the hour (e.g., 09:00:05), it handles it correctly
            if now.minute == 0 and now.second < 10:
                # We are at the top of the hour, run immediately!
                wait_time = 0
            else:
                wait_time = (next_mark - now).total_seconds()

            if wait_time > 5:
                logger.info(f"Scanner sleeping {int(wait_time)}s until next Hour ({next_mark.strftime('%H:%M')})...")
                await asyncio.sleep(wait_time)
                # Small buffer to ensure exchange has processed the candle close
                await asyncio.sleep(5) 
            
            # 2. Run Technical Analysis Scan (Supertrend / Crosses / Unlock / Trend)
            logger.info("--- Starting Hourly Scan Cycle ---")
            for symbol in SYMBOLS:
                for tf in TIMEFRAMES:
                    try:
                        # Calls engine logic to calculate indicators & save to DB
                        # This now includes ALL logic (Supertrend, Unlock, etc.)
                        await signal_engine.analyze_asset(symbol, tf)
                        await asyncio.sleep(0.5) # Rate limit protection
                    except Exception as e:
                        logger.error(f"Scan Error {symbol}: {e}")
            
            logger.info("--- Scan Cycle Complete ---")
            
            # Buffer sleep to prevent double-triggering
            await asyncio.sleep(60) 
            
        except Exception as e:
            logger.error(f"Scanner Crash: {e}")
            await asyncio.sleep(60)

# ==========================================================
# 4. MAIN ENTRY POINT
# ==========================================================
async def main():
    # Setup Telegram Bot Listener
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    logger.info("✅ Telegram Bot Listener Active.")

    # Run Scanner and Alerter Concurrently
    try:
        await asyncio.gather(
            scanner_loop(),  # The Hourly Technical Scan (All Strategies)
            alert_loop(),    # The 60s Alert Check (Price/Signals)
        )
    except Exception as e:
        logger.error(f"Global Crash: {e}")
    finally:
        await application.stop()
        await signal_engine.close_exchange() # Cleanup connection

if __name__ == "__main__":
    try:
        # Windows Loop Policy Fix
        if os.name == 'nt':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass