import os
import asyncio
import pandas as pd
import pandas_ta as ta
import ccxt.async_support as ccxt
import logging
import aiohttp
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SignalEngine")

# --- CONFIGURATION ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- EXCHANGE CONFIG ---
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
        'adjustForTimeDifference': True
    }
})
exchange.urls['api']['public'] = 'https://data-api.binance.vision/api/v3'

# --- HELPER FUNCTIONS ---

async def send_telegram_message(chat_id, message):
    """Sends a message to the user via Telegram."""
    if not chat_id or not BOT_TOKEN:
        logger.error("❌ Missing Chat ID or Bot Token")
        return
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to send TG message: {await resp.text()}")
                else:
                    logger.info(f"✅ Message sent to {chat_id}")
        except Exception as e:
            logger.error(f"Telegram Error: {e}")

async def get_live_price(symbol):
    try:
        ticker = await exchange.fetch_ticker(symbol)
        return ticker['last']
    except Exception as e:
        logger.error(f"Error fetching price for {symbol}: {e}")
        return None

# --- CORE LOGIC 1: TECHNICAL ANALYSIS ---

async def analyze_asset(symbol, timeframe):
    """Fetches data, calculates indicators, and saves signals to Supabase."""
    try:
        # Fetch enough data to find the crossover start
        bars = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=300)
        if not bars or len(bars) < 250: 
            return
        
        df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
        df[['open', 'high', 'low', 'close', 'vol']] = df[['open', 'high', 'low', 'close', 'vol']].apply(pd.to_numeric)
        
        # Timestamp
        last_closed_row = df.iloc[-2]
        last_closed_ts = datetime.fromtimestamp(last_closed_row['ts'] / 1000, tz=timezone.utc)
        asset_name = symbol.replace('/USDT', '')

        # Indicators
        df.ta.rsi(length=14, append=True)
        df.ta.sma(length=50, append=True)
        df.ta.sma(length=200, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.bbands(length=20, std=2, append=True)
        
        def get_col(prefix):
            match = [c for c in df.columns if c.startswith(prefix)]
            return match[0] if match else None

        cols = {
            'rsi': get_col('RSI_14'),
            'sma50': get_col('SMA_50'),
            'sma200': get_col('SMA_200'),
            'macd': get_col('MACD_12_26_9'),
            'macds': get_col('MACDs_12_26_9'),
            'bbu': get_col('BBU_20'), 
            'bbl': get_col('BBL_20')
        }

        if None in cols.values(): return
        
        # Analyze the LAST CLOSED candle (index -2)
        curr_idx = len(df) - 2
        last = df.iloc[curr_idx]
        prev = df.iloc[curr_idx - 1]
        
        avg_vol = df['vol'].rolling(20).mean().iloc[curr_idx]
        vol_surge = last['vol'] > (avg_vol * 2.0)

        findings = []

        # =========================================
        # 1. GOLDEN CROSS PULLBACK (Updated)
        # =========================================
        # Condition: 50MA > 200MA (Golden Zone)
        if last[cols['sma50']] > last[cols['sma200']]:
            # Trigger: Price touched MA50 or MA200 AND Green Candle
            touched_ma = (last['low'] <= last[cols['sma50']]) or (last['low'] <= last[cols['sma200']])
            is_green = last['close'] > last['open']
            
            if touched_ma and is_green:
                # Check for "First Pullback" - Scan backwards until the crossover
                is_first_pullback = True
                for i in range(curr_idx - 1, -1, -1):
                    row = df.iloc[i]
                    # Stop if we hit the crossover point (Trend started here)
                    if row[cols['sma50']] <= row[cols['sma200']]:
                        break
                    
                    # Check if a pullback already happened before
                    prev_touch = (row['low'] <= row[cols['sma50']]) or (row['low'] <= row[cols['sma200']])
                    prev_green = row['close'] > row['open']
                    
                    if prev_touch and prev_green:
                        is_first_pullback = False
                        break
                
                if is_first_pullback:
                    findings.append("GOLDEN_CROSS") # Storing as standard ID for alerts

        # =========================================
        # 2. DEATH CROSS PULLBACK (Updated)
        # =========================================
        # Condition: 50MA < 200MA (Death Zone)
        if last[cols['sma50']] < last[cols['sma200']]:
            # Trigger: Price touched MA50 or MA200 AND Red Candle
            touched_ma = (last['high'] >= last[cols['sma50']]) or (last['high'] >= last[cols['sma200']])
            is_red = last['close'] < last['open']
            
            if touched_ma and is_red:
                # Check for "First Pullback"
                is_first_pullback = True
                for i in range(curr_idx - 1, -1, -1):
                    row = df.iloc[i]
                    if row[cols['sma50']] >= row[cols['sma200']]:
                        break
                    
                    prev_touch = (row['high'] >= row[cols['sma50']]) or (row['high'] >= row[cols['sma200']])
                    prev_red = row['close'] < row['open']
                    
                    if prev_touch and prev_red:
                        is_first_pullback = False
                        break
                
                if is_first_pullback:
                    findings.append("DEATH_CROSS")

        # =========================================
        # 3. OTHER SIGNALS (Standard)
        # =========================================
        if last[cols['macd']] > last[cols['macds']] and prev[cols['macd']] <= prev[cols['macds']]:
            findings.append("MACD_BULL_CROSS")
        
        if last[cols['rsi']] < 35 and last['low'] <= last[cols['bbl']] and vol_surge:
            findings.append("SNIPER_BUY_REVERSAL")
            
        if last[cols['rsi']] > 65 and last['high'] >= last[cols['bbu']] and vol_surge:
            findings.append("SNIPER_SELL_REJECTION")
            
        if last[cols['macd']] > last[cols['macds']] and prev[cols['macd']] <= prev[cols['macds']] and vol_surge:
             findings.append("MOMENTUM_BREAKOUT")

        # --- SAVE TO DB ---
        if findings:
            for signal in findings:
                data = {
                    "asset": asset_name,
                    "timeframe": timeframe,
                    "signal_type": signal,
                    "detected_at": last_closed_ts.isoformat()
                }
                supabase.table('market_scans').upsert(data, on_conflict="asset,timeframe,signal_type").execute()
                logger.info(f"✅ Signal Saved: {asset_name} | {timeframe} | {signal}")

    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {e}")

# --- CORE LOGIC 2: ALERT CHECKER ---

async def check_alerts():
    """Checks for Price Targets and Database Signals."""
    
    try:
        response = supabase.table('alerts').select("*").execute()
        alerts = response.data
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return

    if not alerts: return

    for alert in alerts:
        user_uuid = alert['user_id']
        asset = alert['asset']
        alert_type = alert['alert_type']
        is_recurring = alert.get('is_recurring', False)
        last_triggered = alert.get('last_triggered_at')

        # 1. Look up Telegram ID
        try:
            user_res = supabase.table('users').select('telegram_chat_id').eq('user_uuid', user_uuid).execute()
            if not user_res.data or not user_res.data[0].get('telegram_chat_id'):
                continue
            chat_id = user_res.data[0]['telegram_chat_id']
        except Exception as e:
            logger.error(f"Chat ID Error: {e}")
            continue

        should_trigger = False
        trigger_msg = ""
        trigger_timestamp = datetime.now(timezone.utc).isoformat()

        # --- A. PRICE ALERTS ---
        if 'PRICE_TARGET' in alert_type:
            if is_recurring and last_triggered:
                last_time = datetime.fromisoformat(last_triggered)
                if (datetime.now(timezone.utc) - last_time).total_seconds() < 3600:
                    continue 

            target_price = float(alert.get('target_price', 0))
            current_price = await get_live_price(asset)
            
            if current_price:
                if (alert_type == 'PRICE_TARGET_ABOVE' and current_price >= target_price) or \
                   (alert_type == 'PRICE_TARGET_BELOW' and current_price <= target_price) or \
                   (alert_type == 'PRICE_TARGET' and current_price >= target_price):
                    
                    emoji = "📈" if "ABOVE" in alert_type else "📉"
                    trigger_msg = f"{emoji} <b>PRICE ALERT:</b>\n#{asset} reached <b>${current_price}</b>\n(Target: ${target_price})"
                    should_trigger = True
        
        # --- B. TECHNICAL ALERTS ---
        else:
            lookback_time = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            search_asset = asset.replace('/USDT', '') 
            
            try:
                scan_res = supabase.table('market_scans')\
                    .select("*")\
                    .eq('asset', search_asset)\
                    .eq('timeframe', alert['timeframe'])\
                    .eq('signal_type', alert_type)\
                    .gte('detected_at', lookback_time)\
                    .order('detected_at', desc=True)\
                    .execute()
                
                if scan_res.data:
                    newest_signal = scan_res.data[0]
                    signal_time = datetime.fromisoformat(newest_signal['detected_at'])
                    trigger_timestamp = newest_signal['detected_at']

                    if is_recurring and last_triggered:
                        last_alert_time = datetime.fromisoformat(last_triggered)
                        if signal_time <= last_alert_time:
                            continue 

                    # Custom Message for Pullbacks
                    signal_display = alert_type.replace('_', ' ')
                    if alert_type == "GOLDEN_CROSS":
                        signal_display = "GOLDEN CROSS (PULLBACK ENTRY)"
                    elif alert_type == "DEATH_CROSS":
                        signal_display = "DEATH CROSS (PULLBACK ENTRY)"

                    trigger_msg = f"🚀 <b>SIGNAL ALERT:</b>\n#{asset} ({alert['timeframe']})\n<b>{signal_display}</b> detected!"
                    should_trigger = True
            except Exception as e:
                logger.error(f"Error checking signals: {e}")

        # --- EXECUTE TRIGGER ---
        if should_trigger:
            await send_telegram_message(chat_id, trigger_msg)
            
            if is_recurring:
                supabase.table('alerts').update({'last_triggered_at': trigger_timestamp}).eq('id', alert['id']).execute()
                logger.info(f"🔄 Recurring Alert Updated: {asset} {alert_type}")
            else:
                supabase.table('alerts').delete().eq('id', alert['id']).execute()
                logger.info(f"🗑️ One-Time Alert Deleted: {asset} {alert_type}")

async def close_exchange():
    if exchange:
        await exchange.close()