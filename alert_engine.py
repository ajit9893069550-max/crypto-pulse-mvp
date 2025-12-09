# alert_engine.py

import ccxt
import talib
import numpy as np
import pandas as pd
import time
import asyncio
import logging
from datetime import datetime

# Database imports
import psycopg2 
from urllib.parse import urlparse
from psycopg2.extras import Json # Used for robust JSON handling

# Telegram imports (must be async)
from telegram import Bot
from telegram.constants import ParseMode

# Import configurations
from config import TELEGRAM_BOT_TOKEN, DATABASE_URL

# --- Configuration ---
CHECK_INTERVAL_SECONDS = 60  # Check for alerts every 60 seconds
EXCHANGE_ID = 'binance'      # The exchange to use

# --- Setup Logging ---
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize the Telegram Bot and the Exchange (for async use)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
exchange = getattr(ccxt, EXCHANGE_ID)({'enableRateLimit': True})

# --- 1. DATABASE CONNECTION AND MANAGEMENT ---

def get_db_connection():
    """Returns an active PostgreSQL connection object."""
    try:
        url = urlparse(DATABASE_URL)
        conn = psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port
        )
        return conn
    except psycopg2.Error as e:
        logger.error(f"Database connection error: {e}")
        return None

def fetch_active_alerts():
    """
    FIXED: Retrieves all 'ACTIVE' alerts by joining with the 'public.users' 
    table to get the necessary Telegram chat_id.
    """
    conn = get_db_connection()
    if not conn:
        return []
        
    try:
        cursor = conn.cursor()
        # SQL JOIN to retrieve active alerts and the associated chat_id
        cursor.execute("""
            SELECT 
                a.id, a.user_id, a.asset, a.timeframe, a.alert_type, 
                a.params, a.condition_text, u.telegram_chat_id
            FROM 
                public.alerts a
            JOIN 
                public.users u ON a.user_id = u.user_uuid
            WHERE 
                a.status = 'ACTIVE' AND u.telegram_chat_id IS NOT NULL;
        """)
        
        # Get column names to structure the results
        columns = [desc[0] for desc in cursor.description]
        alerts = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        return alerts
        
    except Exception as e:
        logger.error(f"Error fetching active alerts: {e}")
        if conn: conn.close()
        return []

def deactivate_alert(alert_id, status='TRIGGERED'):
    """
    FIXED: Sets an alert's status to TRIGGERED or other status 
    in the public.alerts table.
    """
    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE public.alerts 
            SET status = %s
            WHERE id = %s;
        """, (status, alert_id))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating alert ID {alert_id}: {e}")
        if conn: conn.rollback()
        return False

# --- 2. TELEGRAM FUNCTION (ASYNC) ---

async def send_telegram_alert(message, chat_id):
    """Sends a message to the specified Telegram chat ID using the async bot."""
    try:
        await bot.send_message(
            chat_id=chat_id, 
            text=message, 
            parse_mode=ParseMode.MARKDOWN
        )
        logger.info(f"Telegram Alert Sent to {chat_id}")
        return True
    except Exception as e:
        logger.error(f"Error sending Telegram alert to {chat_id}: {e}")
        return False

# --- 3. ALERT CHECKING FUNCTIONS (MAINTAINING PANDAS/TALIB LOGIC) ---

def check_ma_cross(ohlcv_data, alert):
    """Checks for a Golden Cross or Death Cross."""
    # The 'params' are now nested under the alert object from the DB query
    params = alert['params']
    
    fast_ma_period = params.get('fast_ma', 50)
    slow_ma_period = params.get('slow_ma', 200)
    condition = params.get('condition', 'ABOVE') # 'ABOVE' or 'BELOW'
    
    # Calculate EMA using talib
    fast_ma = talib.EMA(ohlcv_data['Close'].values, timeperiod=fast_ma_period)
    slow_ma = talib.EMA(ohlcv_data['Close'].values, timeperiod=slow_ma_period)

    # Need at least two closing values for crossover logic
    if len(fast_ma) < 2 or len(slow_ma) < 2:
        return None

    was_below = (fast_ma[-2] < slow_ma[-2])
    is_above  = (fast_ma[-1] > slow_ma[-1])
    was_above = (fast_ma[-2] > slow_ma[-2])
    is_below  = (fast_ma[-1] < slow_ma[-1])
    
    alert_message = None

    if condition == 'ABOVE' and was_below and is_above:
        alert_message = (
            f"🔥 **GOLDEN CROSS ALERT** for {alert['asset']} ({alert['timeframe']})!\n"
            f"Fast EMA ({fast_ma_period}) crossed **ABOVE** Slow EMA ({slow_ma_period})."
        )
    elif condition == 'BELOW' and was_above and is_below:
        alert_message = (
            f"💀 **DEATH CROSS ALERT** for {alert['asset']} ({alert['timeframe']})!\n"
            f"Fast EMA ({fast_ma_period}) crossed **BELOW** Slow EMA ({slow_ma_period})."
        )

    return alert_message

def check_price_level(ohlcv_data, alert):
    """Checks if the price has crossed a specific target level."""
    params = alert['params']

    target_price = params.get('target_price')
    condition = params.get('condition')
    
    if target_price is None or condition is None:
        return None
        
    current_close = ohlcv_data['Close'].iloc[-1]
    
    alert_message = None

    if condition == 'ABOVE' and current_close >= target_price:
        alert_message = (
            f"🎯 **PRICE ALERT (ABOVE)** for {alert['asset']} ({alert['timeframe']})!\n"
            f"Price is now ${current_close:.2f}, crossing target **${target_price:.2f}**."
        )
    elif condition == 'BELOW' and current_close <= target_price:
        alert_message = (
            f"📉 **PRICE ALERT (BELOW)** for {alert['asset']} ({alert['timeframe']})!\n"
            f"Price is now ${current_close:.2f}, crossing target **${target_price:.2f}**."
        )
    
    return alert_message

# --- 4. MAIN EXECUTION LOOP ---

async def run_alert_check(alert):
    """Fetches data and runs the check for a single alert."""
    alert_id = alert.get('id')
    asset = alert.get('asset')
    timeframe = alert.get('timeframe')
    alert_type = alert.get('alert_type') # Use the database column name
    chat_id = alert.get('telegram_chat_id') 

    if not all([asset, timeframe, alert_type, chat_id, alert_id]):
        logger.warning(f"Skipping alert due to missing crucial data: {alert_id}")
        return
    
    logger.info(f"-> Checking alert {alert_id}: {alert_type} for {asset} ({timeframe})")
    
    try:
        # Fetch OHLCV data using ccxt
        ohlcv = await exchange.fetch_ohlcv(asset, timeframe, limit=300) 
        
        if not ohlcv or len(ohlcv) < 200:
            logger.warning(f"Insufficient data for deep checks on {asset} ({timeframe}). Skipping.")
            return

        df = pd.DataFrame(ohlcv, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        
        message = None
        
        # Dispatch logic uses the correct 'alert_type'
        if alert_type == 'MA_CROSS':
            message = check_ma_cross(df, alert)
        elif alert_type == 'PRICE_LEVEL':
            message = check_price_level(df, alert)
        
        if message:
            # 1. Send the notification
            await send_telegram_alert(message, chat_id) 
            
            # 2. Deactivate the alert in the database
            if deactivate_alert(alert_id, status='TRIGGERED'):
                logger.info(f"Alert {alert_id} successfully deactivated after trigger.")
            else:
                logger.error(f"Failed to deactivate alert {alert_id} in DB.")

    except Exception as e:
        logger.error(f"An error occurred during data fetch/check for {asset}: {e}")

async def main_worker_loop():
    """The main loop that runs the alert checking process."""
    logger.info(f"--- Starting Crypto Pulse Alert Engine ---")
    logger.info(f"Worker started. Checking every {CHECK_INTERVAL_SECONDS} seconds.")
    
    while True:
        start_time = time.time()
        
        try:
            active_alerts = fetch_active_alerts()
            if not active_alerts:
                logger.info("No active alerts found.")
            else:
                logger.info(f"Fetched {len(active_alerts)} active alerts to check.")
                
                # Use asyncio.gather to check alerts concurrently (if possible)
                # Ensure you manage ccxt rate limits if checking many symbols at once.
                await asyncio.gather(*(run_alert_check(alert) for alert in active_alerts))
                
        except Exception as e:
            logger.critical(f"Critical error in main worker loop: {e}")
            
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        sleep_duration = max(0, CHECK_INTERVAL_SECONDS - elapsed_time)
        logger.info(f"Cycle complete in {elapsed_time:.2f}s. Sleeping for {sleep_duration:.2f}s.")
        time.sleep(sleep_duration)


# --- Production Execution ---

if __name__ == '__main__':
    try:
        # Run the main async loop
        asyncio.run(main_worker_loop())
    except KeyboardInterrupt:
        logger.info("Alert Engine Worker stopped by user (KeyboardInterrupt).")