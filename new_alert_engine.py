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
        bars = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=250)
        if not bars or len(bars) < 200: 
            return
        
        df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
        df[['open', 'high', 'low', 'close', 'vol']] = df[['open', 'high', 'low', 'close', 'vol']].apply(pd.to_numeric)
        
        # Use Open Time for consistency
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
        
        last = df.iloc[-2]
        prev = df.iloc[-3]
        avg_vol = df['vol'].rolling(20).mean().iloc[-2]
        vol_surge = last['vol'] > (avg_vol * 2.0)

        findings = []

        # Signals
        if last[cols['sma50']] > last[cols['sma200']] and prev[cols['sma50']] <= prev[cols['sma200']]:
            findings.append("GOLDEN_CROSS")
        if last[cols['sma50']] < last[cols['sma200']] and prev[cols['sma50']] >= prev[cols['sma200']]:
            findings.append("DEATH_CROSS")
        if last[cols['macd']] > last[cols['macds']] and prev[cols['macd']] <= prev[cols['macds']]:
            findings.append("MACD_BULL_CROSS")
        if last[cols['rsi']] < 35 and last['low'] <= last[cols['bbl']] and vol_surge:
            findings.append("SNIPER_BUY_REVERSAL")
        if last[cols['rsi']] > 65 and last['high'] >= last[cols['bbu']] and vol_surge:
            findings.append("SNIPER_SELL_REJECTION")
        if last[cols['macd']] > last[cols['macds']] and prev[cols['macd']] <= prev[cols['macds']] and vol_surge:
             findings.append("MOMENTUM_BREAKOUT")

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
        
        # --- A. PRICE ALERTS ---
        if 'PRICE_TARGET' in alert_type:
            if is_recurring and last_triggered:
                last_time = datetime.fromisoformat(last_triggered)
                # 1 Hour Cooldown for Price Alerts
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
            # FIX: Look back 24 hours to catch candle Open Times
            lookback_time = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            
            try:
                # FIX: Order by newest first
                scan_res = supabase.table('market_scans')\
                    .select("*")\
                    .eq('asset', asset)\
                    .eq('timeframe', alert['timeframe'])\
                    .eq('signal_type', alert_type)\
                    .gte('detected_at', lookback_time)\
                    .order('detected_at', desc=True)\
                    .execute()
                
                if scan_res.data:
                    newest_signal = scan_res.data[0]
                    signal_time = datetime.fromisoformat(newest_signal['detected_at'])

                    # RECURRING CHECK: Only fire if we found a NEW signal
                    if is_recurring and last_triggered:
                        last_alert_time = datetime.fromisoformat(last_triggered)
                        if signal_time <= last_alert_time:
                            continue # We already alerted for this one

                    trigger_msg = f"🚀 <b>SIGNAL ALERT:</b>\n#{asset} ({alert['timeframe']})\n<b>{alert_type.replace('_', ' ')}</b> detected!"
                    should_trigger = True
            except Exception as e:
                logger.error(f"Error checking signals: {e}")

        # --- EXECUTE TRIGGER ---
        if should_trigger:
            await send_telegram_message(chat_id, trigger_msg)
            
            if is_recurring:
                now_iso = datetime.now(timezone.utc).isoformat()
                supabase.table('alerts').update({'last_triggered_at': now_iso}).eq('id', alert['id']).execute()
                logger.info(f"🔄 Recurring Alert Updated: {asset} {alert_type}")
            else:
                supabase.table('alerts').delete().eq('id', alert['id']).execute()
                logger.info(f"🗑️ One-Time Alert Deleted: {asset} {alert_type}")

async def close_exchange():
    if exchange:
        await exchange.close()