import os
import asyncio
import pandas as pd
import pandas_ta as ta
import ccxt.async_support as ccxt
import logging
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# --- LOGGING SETUP ---
logger = logging.getLogger("StrategyEngine")

# --- CONFIGURATION ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Strategy Settings
DAYS_BEFORE_UNLOCK = 7    
BTC_PUMP_THRESHOLD = 7.0  # If BTC pumps > 7% in 3 days, pause strategy
TIMEFRAME = '4h'          

# The "Fresh Blood" Watchlist (Symbol: Unlock Day)
TOKEN_PATTERNS = {
    'ENA': 2, 'ZK': 17, 'ZRO': 20, 'W': 3, 'STRK': 15, 
    'PIXEL': 19, 'MANTA': 18, 'ALT': 25, 'DYM': 6
}

# --- EXCHANGE SETUP ---
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})
exchange.urls['api']['public'] = 'https://data-api.binance.vision/api/v3'

# --- HELPER FUNCTIONS ---

def get_next_unlock_date(day):
    """Calculates the next occurrence of the unlock day."""
    now = datetime.now()
    try:
        candidate = datetime(now.year, now.month, day)
        if candidate >= now: return candidate
    except ValueError: pass

    next_month = now.month + 1 if now.month < 12 else 1
    next_year = now.year if now.month < 12 else now.year + 1
    try:
        return datetime(next_year, next_month, day)
    except ValueError:
        return datetime(next_year, next_month + 1, day)

async def check_btc_safety():
    """Returns False if BTC pumped > 7% in last 3 days."""
    try:
        # Fetch 3 days of 4h candles (approx 18 candles)
        bars = await exchange.fetch_ohlcv('BTC/USDT', timeframe='4h', limit=20)
        if not bars: return False
        
        df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
        current_price = df.iloc[-1]['close']
        old_price = df.iloc[0]['open'] # Price ~3 days ago
        
        change_pct = ((current_price - old_price) / old_price) * 100
        
        if change_pct > BTC_PUMP_THRESHOLD:
            logger.warning(f"⚠️ BTC Pumping ({change_pct:.2f}%). Strategy PAUSED.")
            return False
        return True
    except Exception as e:
        logger.error(f"BTC Check Error: {e}")
        return False

# --- MAIN STRATEGY LOGIC ---

async def run_unlock_strategy():
    """Scans for the Unlock Short setup."""
    logger.info("🧠 Starting Unlock Strategy Scan...")
    
    # 1. Market Safety Filter
    is_safe = await check_btc_safety()
    if not is_safe:
        return # Stop if market is unsafe

    # 2. Iterate Tokens
    for token, unlock_day in TOKEN_PATTERNS.items():
        symbol = f"{token}/USDT"
        
        try:
            # A. Check Date Window
            next_unlock = get_next_unlock_date(unlock_day)
            window_start = next_unlock - timedelta(days=DAYS_BEFORE_UNLOCK)
            now = datetime.now()
            
            if not (window_start <= now <= next_unlock):
                # logger.info(f"Skipping {token} (Outside Window)")
                continue

            # B. Fetch Data
            bars = await exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
            if not bars: continue

            df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
            
            # C. Calculate Indicators (Bollinger Bands)
            # pandas_ta automatically adds columns: BBL_20_2.0, BBM_20_2.0, BBU_20_2.0
            df.ta.bbands(close=df['close'], length=20, std=2, append=True)
            
            # Get latest COMPLETED candle (index -2)
            last_candle = df.iloc[-2]
            last_ts = datetime.fromtimestamp(last_candle['ts'] / 1000, tz=timezone.utc)
            
            # Dynamic Column Name for Upper Band
            bbu_col = 'BBU_20_2.0'
            
            # D. The "Sniper" Logic
            # 1. Price touched or broke Upper Band
            touched_bb = last_candle['high'] >= last_candle[bbu_col]
            
            # 2. Candle Closed RED (Close < Open)
            is_red = last_candle['close'] < last_candle['open']

            if touched_bb and is_red:
                signal_type = "STRATEGY_UNLOCK_SHORT"
                
                # Save to Database
                data = {
                    "asset": token,
                    "timeframe": TIMEFRAME,
                    "signal_type": signal_type,
                    "detected_at": last_ts.isoformat()
                }
                
                # Upsert to DB
                supabase.table('market_scans').upsert(data, on_conflict="asset,timeframe,signal_type").execute()
                logger.info(f"✅ STRATEGY SIGNAL: {token} Short Triggered!")

        except Exception as e:
            logger.error(f"Error scanning {token}: {e}")
            
    logger.info("🧠 Strategy Scan Complete.")

async def close_strategy_engine():
    await exchange.close()