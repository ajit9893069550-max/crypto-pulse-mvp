import asyncio
import logging
import os
import time
import requests
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from supabase import create_client, Client
from dotenv import load_dotenv

# Logic imports
from new_alert_engine import analyze_asset, close_exchange

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
        await update.message.reply_text("👋 Welcome! Go to your Dashboard and click 'Connect Telegram'.")

# ==========================================================
# 2. ALERT DISPATCHER (Sends Notifications)
# ==========================================================
def send_telegram_message(chat_id, message):
    """Sends message via HTTP to avoid async loop conflict."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"Failed to send Telegram: {e}")

async def alert_loop():
    """Watches DB for new signals and matches them to alerts."""
    logger.info("👀 Alert Watcher Started...")
    
    # Start checking for signals created AFTER now
    last_processed_time = datetime.utcnow().isoformat()

    while True:
        try:
            # 1. Fetch NEW signals
            response = supabase.table('market_scans')\
                .select('*')\
                .gt('detected_at', last_processed_time)\
                .order('detected_at', desc=False)\
                .execute()

            if response.data:
                last_processed_time = response.data[-1]['detected_at']

                for signal in response.data:
                    asset = signal['asset']
                    tf = signal['timeframe']
                    sig_type = signal['signal_type']

                    # 2. Find Users who want this signal
                    matches = supabase.table('alerts')\
                        .select('user_id, users(telegram_chat_id)')\
                        .eq('asset', asset)\
                        .eq('timeframe', tf)\
                        .eq('alert_type', sig_type)\
                        .eq('status', 'ACTIVE')\
                        .execute()

                    if matches.data:
                        logger.info(f"⚡ Dispatching {len(matches.data)} alerts for {asset}")
                        for alert in matches.data:
                            user = alert.get('users')
                            if user and user.get('telegram_chat_id'):
                                emoji = "🟢" if "BULL" in sig_type else "🔴"
                                msg = (f"{emoji} *CryptoPulse Alert*\n\n"
                                       f"🪙 *{asset}*\n⏱ *{tf}*\n📊 *{sig_type.replace('_', ' ')}*")
                                
                                # Run in thread to not block the scanner
                                await asyncio.to_thread(send_telegram_message, user['telegram_chat_id'], msg)

            await asyncio.sleep(10) # Check every 10 seconds

        except Exception as e:
            logger.error(f"Alert Loop Error: {e}")
            await asyncio.sleep(10)

# ==========================================================
# 3. MARKET SCANNER (Replaces main.py)
# ==========================================================
async def scanner_loop():
    logger.info("📉 Market Scanner Started (15m cycles)...")
    while True:
        try:
            # Calculate wait time for next 15m candle (00, 15, 30, 45)
            now = datetime.now()
            minutes_to_next = 15 - (now.minute % 15)
            next_mark = now.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_next)
            wait_time = (next_mark - now).total_seconds()

            if wait_time > 5:
                logger.info(f"Scanner sleeping {int(wait_time)}s...")
                await asyncio.sleep(wait_time)
            
            # --- RUN SCAN ---
            logger.info("--- Starting Scan Cycle ---")
            for symbol in SYMBOLS:
                for tf in TIMEFRAMES:
                    try:
                        # Call your existing engine logic
                        await analyze_asset(symbol, tf)
                        await asyncio.sleep(0.5) # Rate limit
                    except Exception as e:
                        logger.error(f"Scan Error {symbol}: {e}")
            
            logger.info("--- Scan Cycle Complete ---")
            await asyncio.sleep(20) # Buffer
            
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

    # Run Scanner & Alerter Concurrently
    try:
        await asyncio.gather(
            scanner_loop(),
            alert_loop()
        )
    except Exception as e:
        logger.error(f"Global Crash: {e}")
    finally:
        await application.stop()
        await close_exchange()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass