import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from telegram import Bot
from telegram.constants import ParseMode
from dotenv import load_dotenv

# Importing your custom modules
from new_alert_engine import analyze_asset, close_exchange
from database_manager import fetch_triggered_alerts, get_db_connection

# 1. Load Environment Variables
load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT', 'BNB/USDT', 'DOGE/USDT'] 
TIMEFRAMES = ['1h', '4h']

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Orchestrator")

# Initialize Telegram Bot
if not TELEGRAM_BOT_TOKEN:
    logger.critical("TELEGRAM_BOT_TOKEN not found in environment variables!")
    exit(1)

bot = Bot(token=TELEGRAM_BOT_TOKEN)

async def send_telegram_alert(m):
    """Helper to format and send Telegram messages."""
    msg = (f"🔔 *SIGNAL:* {m['alert_type']}\n"
           f"*Asset:* {m['asset']}\n"
           f"*TF:* {m['timeframe']}\n"
           f"*Status:* Triggered (IST Aligned)")
    try:
        await bot.send_message(
            chat_id=m['telegram_chat_id'], 
            text=msg, 
            parse_mode=ParseMode.MARKDOWN
        )
        return True
    except Exception as e:
        logger.error(f"Telegram Notification Failed for {m['asset']}: {e}")
        return False

async def run_cycle():
    """Executes one full scan and processes database alerts."""
    logger.info("--- Starting Signal Scan Cycle ---")
    
    # 1. Analyze Assets
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            try:
                # Engine logic handles IST offset by analyzing closed candles
                await analyze_asset(symbol, tf)
                # Respect rate limits (0.5s pause)
                await asyncio.sleep(0.5) 
            except Exception as e:
                logger.error(f"Error scanning {symbol} on {tf}: {e}")

    # 2. Process Personal Database Alerts
    conn = None
    try:
        matches = fetch_triggered_alerts()
        if matches:
            conn = get_db_connection()
            cur = conn.cursor()
            for m in matches:
                success = await send_telegram_alert(m)
                if success:
                    # Mark as triggered in DB
                    cur.execute(
                        "UPDATE public.alerts SET status = 'TRIGGERED' WHERE id = %s", 
                        (m['id'],)
                    )
                    logger.info(f"Telegram alert sent and DB updated for {m['asset']}")
            
            conn.commit()
            cur.close()
    except Exception as e:
        logger.error(f"Database sync failed: {e}")
    finally:
        if conn:
            conn.close()

def get_seconds_until_next_interval(interval_minutes=15):
    """Calculates seconds until the next 15-minute mark (00, 15, 30, 45)."""
    now = datetime.now()
    minutes_to_next = interval_minutes - (now.minute % interval_minutes)
    next_mark = now.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_next)
    delta = (next_mark - now).total_seconds()
    return delta

async def main():
    """Main loop aligned with clock time."""
    logger.info("Bot started. Syncing with IST Candle intervals (offset :30)...")
    
    try:
        while True:
            wait_time = get_seconds_until_next_interval(15)
            
            if wait_time > 2:
                logger.info(f"Waiting {int(wait_time)}s for next clock-aligned interval...")
                await asyncio.sleep(wait_time)
            
            start_time = time.time()
            await run_cycle()
            
            duration = time.time() - start_time
            logger.info(f"Scan completed in {int(duration)}s.")
            
            # Prevent double-firing if the cycle finishes extremely fast
            await asyncio.sleep(5) 
            
    except Exception as e:
        logger.error(f"Main loop crashed: {e}")
    finally:
        logger.info("Shutting down exchange sessions...")
        await close_exchange()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Scanner stopped by user.")