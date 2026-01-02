import asyncio
import logging
import os
import requests
import time
from telegram.ext import ApplicationBuilder, CommandHandler
from telegram import Update
from telegram.ext import ContextTypes
from supabase import create_client, Client
from dotenv import load_dotenv

# Import your existing modules
from main import run_cycle, get_seconds_until_next_interval
from new_alert_engine import close_exchange

# --- CONFIGURATION ---
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("UnifiedWorker")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not all([SUPABASE_URL, SUPABASE_KEY, TELEGRAM_BOT_TOKEN]):
    logger.critical("❌ Missing Secrets! Check .env file.")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================================
# 1. TELEGRAM HANDSHAKE (User Linking)
# ==========================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Links user Telegram ID to their Web Account via /start <user_id>"""
    chat_id = update.effective_chat.id
    if context.args:
        user_uuid = context.args[0]
        try:
            response = supabase.table('users').update({'telegram_chat_id': str(chat_id)})\
                .eq('user_uuid', user_uuid).execute()
            
            if response.data:
                await update.message.reply_text("✅ *Linked!* You will now receive alerts here.", parse_mode='Markdown')
                logger.info(f"Linked User {user_uuid} to Chat {chat_id}")
            else:
                await update.message.reply_text("❌ Account not found. Please login to the dashboard first.")
        except Exception as e:
            logger.error(f"Link Error: {e}")
            await update.message.reply_text("⚠️ Database error. Try again.")
    else:
        await update.message.reply_text("👋 Welcome! Please use the 'Link Telegram' button on the dashboard.")

# ==========================================================
# 2. ALERT DISPATCHER (Sends Messages)
# ==========================================================
def send_telegram_message(chat_id, message):
    """Sends message via HTTP to avoid async conflict with polling"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"Failed to send Telegram: {e}")

async def alert_loop():
    """Watches DB for new signals and sends alerts"""
    logger.info("👀 Alert Watcher Started...")
    
    # Start checking from NOW
    last_processed_time = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

    while True:
        try:
            # 1. Fetch NEW signals
            response = supabase.table('market_scans')\
                .select('*')\
                .gt('detected_at', last_processed_time)\
                .order('detected_at', desc=False)\
                .execute()

            if response.data:
                # Update timestamp to the latest signal
                last_processed_time = response.data[-1]['detected_at']

                for signal in response.data:
                    asset = signal['asset']
                    tf = signal['timeframe']
                    sig_type = signal['signal_type']

                    # 2. Find matching Active Alerts
                    matches = supabase.table('alerts')\
                        .select('user_id, users(telegram_chat_id)')\
                        .eq('asset', asset)\
                        .eq('timeframe', tf)\
                        .eq('alert_type', sig_type)\
                        .eq('status', 'ACTIVE')\
                        .execute()

                    if matches.data:
                        logger.info(f"⚡ Dispatching {len(matches.data)} alerts for {asset} {sig_type}")
                        
                        for alert in matches.data:
                            user = alert.get('users')
                            if user and user.get('telegram_chat_id'):
                                emoji = "🟢" if "BULL" in sig_type or "CROSS" in sig_type else "🔴"
                                msg = (
                                    f"{emoji} *CryptoPulse Alert* {emoji}\n\n"
                                    f"🪙 *Asset:* {asset}\n"
                                    f"⏱ *Time:* {tf}\n"
                                    f"📊 *Signal:* {sig_type.replace('_', ' ')}"
                                )
                                # Run blocking HTTP request in a thread
                                await asyncio.to_thread(send_telegram_message, user['telegram_chat_id'], msg)

            await asyncio.sleep(10) # Check every 10 seconds

        except Exception as e:
            logger.error(f"Alert Loop Error: {e}")
            await asyncio.sleep(10)

# ==========================================================
# 3. MARKET SCANNER (Runs Every 15m)
# ==========================================================
async def scanner_loop():
    logger.info("📉 Market Scanner Started (15m cycles)...")
    while True:
        try:
            wait_time = get_seconds_until_next_interval(15)
            if wait_time > 5:
                logger.info(f"Scanner sleeping {int(wait_time)}s until next candle...")
                await asyncio.sleep(wait_time)
            
            # Run the scanning logic (from main.py)
            await run_cycle()
            
            # Buffer to prevent double-firing
            await asyncio.sleep(20)
            
        except Exception as e:
            logger.error(f"Scanner Error: {e}")
            await asyncio.sleep(60)

# ==========================================================
# 4. MAIN RUNNER
# ==========================================================
async def main():
    # 1. Setup Telegram Bot
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    logger.info("✅ Telegram Bot Listener Active.")

    # 2. Run Scanner and Alerter Concurrently
    try:
        await asyncio.gather(
            scanner_loop(),
            alert_loop()
        )
    except Exception as e:
        logger.error(f"Global Loop Crash: {e}")
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        logger.error(f"Fatal Error: {e}")
    finally:
        asyncio.run(close_exchange())