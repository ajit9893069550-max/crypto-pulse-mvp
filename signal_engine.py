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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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

# --- STRATEGY SETTINGS ---
# 1. Supertrend
ST_PERIOD = 10
ST_FACTOR = 4
ADX_THRESHOLD = 20
RVOL_THRESHOLD = 1.5
RSI_MAX = 70

# 2. Unlock Strategy Data
UNLOCK_TOKENS = {
    'ENA': 2, 'ZK': 17, 'ZRO': 20, 'W': 3, 'STRK': 15, 
    'PIXEL': 19, 'MANTA': 18, 'ALT': 25, 'DYM': 6
}
DAYS_BEFORE_UNLOCK = 7

# ==============================================================================
#  HELPER FUNCTIONS
# ==============================================================================

async def send_telegram_message(chat_id, message):
    if not chat_id or not BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200: logger.error(f"TG Error: {await resp.text()}")
        except Exception as e: logger.error(f"Telegram Error: {e}")

async def get_live_price(symbol):
    try:
        ticker = await exchange.fetch_ticker(symbol)
        return ticker['last']
    except: return None

def get_next_unlock_date(day):
    """Calculates the next occurrence of a specific day of the month."""
    now = datetime.now()
    try:
        candidate = datetime(now.year, now.month, day)
        if candidate >= now: return candidate
    except ValueError: pass
    
    # Move to next month
    next_month = now.month + 1 if now.month < 12 else 1
    next_year = now.year if now.month < 12 else now.year + 1
    try:
        return datetime(next_year, next_month, day)
    except ValueError:
        return datetime(next_year, next_month + 1, day)

# ==============================================================================
#  CORE ANALYSIS LOGIC
# ==============================================================================

async def analyze_asset(symbol, timeframe):
    """
    Runs ALL strategies (Supertrend, Crosses, Unlock, Trend) and saves signals.
    """
    try:
        # 1. Fetch Data
        # limit=300 covers the 200 SMA requirement
        bars = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=300)
        if not bars or len(bars) < 250: return
        
        df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
        df[['open', 'high', 'low', 'close', 'vol']] = df[['open', 'high', 'low', 'close', 'vol']].apply(pd.to_numeric)
        
        # Timestamp info
        last_closed_row = df.iloc[-2]
        last_closed_ts = datetime.fromtimestamp(last_closed_row['ts'] / 1000, tz=timezone.utc)
        asset_name = symbol.replace('/USDT', '')

        # --- 2. CALCULATE ALL INDICATORS ---
        
        # Supertrend (10, 4)
        st = df.ta.supertrend(length=ST_PERIOD, multiplier=ST_FACTOR, append=True)
        st_dir_col = [c for c in df.columns if c.startswith('SUPERTd_')][0] if st is not None else None

        # ADX (14)
        df.ta.adx(length=14, append=True)
        adx_col = [c for c in df.columns if c.startswith('ADX_')][0]

        # RSI (14)
        df.ta.rsi(length=14, append=True)
        
        # SMAs (50, 200)
        df.ta.sma(length=50, append=True)
        df.ta.sma(length=200, append=True)
        
        # Bollinger Bands (20, 2)
        df.ta.bbands(length=20, std=2, append=True)
        
        # Relative Volume (RVOL)
        df['Vol_SMA'] = df['vol'].rolling(20).mean()
        df['RVOL'] = df['vol'] / df['Vol_SMA']

        # Column Helper
        def get_col(prefix):
            match = [c for c in df.columns if c.startswith(prefix)]
            return match[0] if match else None

        cols = {
            'rsi': get_col('RSI_14'),
            'sma50': get_col('SMA_50'),
            'sma200': get_col('SMA_200'),
            'bbu': get_col('BBU_20'),
            'st_dir': st_dir_col,
            'adx': adx_col
        }
        
        if None in cols.values(): return

        # --- 3. EVALUATE STRATEGIES (On Last Closed Candle) ---
        curr_idx = len(df) - 2
        last = df.iloc[curr_idx]
        
        findings = []

        # -------------------------------------------------------
        # STRATEGY A: SUPERTREND MOMENTUM (From Backtest)
        # Logic: Supertrend=1 (Green) + ADX>20 + RVOL>1.5 + RSI<70
        # -------------------------------------------------------
        if (last[cols['st_dir']] == 1 and 
            last[cols['adx']] > ADX_THRESHOLD and 
            last['RVOL'] > RVOL_THRESHOLD and 
            last[cols['rsi']] < RSI_MAX):
            findings.append("SUPERTREND_BUY")

        # -------------------------------------------------------
        # STRATEGY B: CROSSOVER PULLBACKS
        # -------------------------------------------------------
        # Golden Cross Pullback
        if last[cols['sma50']] > last[cols['sma200']]:
            touched_ma = (last['low'] <= last[cols['sma50']]) or (last['low'] <= last[cols['sma200']])
            is_green = last['close'] > last['open']
            if touched_ma and is_green:
                # Ensure it's a fresh pullback
                is_fresh = True
                for i in range(curr_idx - 1, -1, -1):
                    row = df.iloc[i]
                    if row[cols['sma50']] <= row[cols['sma200']]: break
                    if ((row['low'] <= row[cols['sma50']]) or (row['low'] <= row[cols['sma200']])) and (row['close'] > row['open']):
                        is_fresh = False; break
                if is_fresh: findings.append("GOLDEN_CROSS")

        # Death Cross Pullback
        if last[cols['sma50']] < last[cols['sma200']]:
            touched_ma = (last['high'] >= last[cols['sma50']]) or (last['high'] >= last[cols['sma200']])
            is_red = last['close'] < last['open']
            if touched_ma and is_red:
                is_fresh = True
                for i in range(curr_idx - 1, -1, -1):
                    row = df.iloc[i]
                    if row[cols['sma50']] >= row[cols['sma200']]: break
                    if ((row['high'] >= row[cols['sma50']]) or (row['high'] >= row[cols['sma200']])) and (row['close'] < row['open']):
                        is_fresh = False; break
                if is_fresh: findings.append("DEATH_CROSS")

        # -------------------------------------------------------
        # STRATEGY C: 200MA TREND + RSI
        # -------------------------------------------------------
        # Bullish: Price > 200MA + RSI <= 35 + Green Candle
        if (last['close'] > last[cols['sma200']]) and (last[cols['rsi']] <= 35) and (last['close'] > last['open']):
            findings.append("STRATEGY_BULLISH_200MA_RSI")
        
        # Bearish: Price < 200MA + RSI >= 65 + Red Candle
        if (last['close'] < last[cols['sma200']]) and (last[cols['rsi']] >= 65) and (last['close'] < last['open']):
            findings.append("STRATEGY_BEARISH_200MA_RSI")

        # -------------------------------------------------------
        # STRATEGY D: TOKEN UNLOCK SHORT
        # -------------------------------------------------------
        if asset_name in UNLOCK_TOKENS:
            unlock_day = UNLOCK_TOKENS[asset_name]
            next_unlock = get_next_unlock_date(unlock_day)
            window_start = next_unlock - timedelta(days=DAYS_BEFORE_UNLOCK)
            now = datetime.now()

            # Inside 7-day window?
            if window_start <= now <= next_unlock:
                # Logic: Touch Upper BB + Red Candle
                touched_bb = last['high'] >= last[cols['bbu']]
                is_red = last['close'] < last['open']
                if touched_bb and is_red:
                    findings.append("STRATEGY_UNLOCK_SHORT")

        # --- 4. SAVE TO SUPABASE ---
        if findings:
            for signal in findings:
                data = {
                    "asset": asset_name,
                    "timeframe": timeframe,
                    "signal_type": signal,
                    "detected_at": last_closed_ts.isoformat()
                }
                # Upsert to DB
                supabase.table('market_scans').upsert(data, on_conflict="asset,timeframe,signal_type").execute()
                logger.info(f"✅ Signal Saved: {asset_name} | {timeframe} | {signal}")

    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {e}")

# ==============================================================================
#  ALERT CHECKER
# ==============================================================================

async def check_alerts():
    """Checks alerts table and sends Telegram messages."""
    try:
        response = supabase.table('alerts').select("*").execute()
        alerts = response.data
    except Exception as e: return

    if not alerts: return

    for alert in alerts:
        user_uuid = alert['user_id']
        asset = alert['asset']
        alert_type = alert['alert_type']
        is_recurring = alert.get('is_recurring', False)
        last_triggered = alert.get('last_triggered_at')

        # Get Chat ID
        try:
            user_res = supabase.table('users').select('telegram_chat_id').eq('user_uuid', user_uuid).execute()
            if not user_res.data or not user_res.data[0].get('telegram_chat_id'): continue
            chat_id = user_res.data[0]['telegram_chat_id']
        except: continue

        should_trigger = False
        trigger_msg = ""
        trigger_timestamp = datetime.now(timezone.utc).isoformat()

        # Check Signal Recency
        lookback = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        search_asset = asset.replace('/USDT', '')

        # 1. Price Alerts
        if 'PRICE_TARGET' in alert_type:
            # (Logic handled in loop: cooldown check + live price fetch)
            if is_recurring and last_triggered:
                try:
                    if (datetime.now(timezone.utc) - datetime.fromisoformat(last_triggered)).total_seconds() < 3600: continue
                except: pass
            
            tgt = alert.get('target_price')
            if tgt:
                curr = await get_live_price(asset)
                if curr and ((alert_type == 'PRICE_TARGET_ABOVE' and curr >= tgt) or 
                             (alert_type == 'PRICE_TARGET_BELOW' and curr <= tgt)):
                    trigger_msg = f"💰 <b>PRICE ALERT:</b>\n#{asset} reached ${curr} (Target: ${tgt})"
                    should_trigger = True

        # 2. Strategy Alerts (Supertrend, Crosses, etc.)
        else:
            try:
                res = supabase.table('market_scans').select("*")\
                    .eq('asset', search_asset)\
                    .eq('timeframe', alert['timeframe'])\
                    .eq('signal_type', alert_type)\
                    .gte('detected_at', lookback)\
                    .order('detected_at', desc=True)\
                    .execute()
                
                if res.data:
                    signal = res.data[0]
                    sig_time = datetime.fromisoformat(signal['detected_at'])
                    trigger_timestamp = signal['detected_at']

                    # Recurring check
                    if is_recurring and last_triggered:
                        if sig_time <= datetime.fromisoformat(last_triggered): continue

                    # Message Formatting
                    readable_type = alert_type.replace('_', ' ')
                    if "SUPERTREND" in alert_type: readable_type = "SUPERTREND BUY (High Momentum)"
                    elif "UNLOCK" in alert_type: readable_type = "TOKEN UNLOCK SHORT"
                    
                    trigger_msg = f"🚀 <b>SIGNAL ALERT:</b>\n#{asset} ({alert['timeframe']})\n<b>{readable_type}</b> detected!"
                    should_trigger = True
            except: pass

        # Send
        if should_trigger:
            await send_telegram_message(chat_id, trigger_msg)
            if is_recurring:
                supabase.table('alerts').update({'last_triggered_at': trigger_timestamp}).eq('id', alert['id']).execute()
            else:
                supabase.table('alerts').delete().eq('id', alert['id']).execute()

async def close_exchange():
    if exchange: await exchange.close()