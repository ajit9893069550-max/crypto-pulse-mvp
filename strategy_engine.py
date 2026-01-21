import os
import asyncio
import pandas as pd
import pandas_ta as ta
import ccxt.async_support as ccxt
import logging
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StrategyEngine")

# --- CONFIGURATION ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

# --- WATCHLISTS ---
# 1. Major Coins (For Trend Strategies like 200MA)
MAJOR_COINS = [
    'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'LINK', 'MATIC'
]

# 2. Unlock/Vesting Tokens (Symbol: Day of Month)
UNLOCK_TOKENS = {
    'ENA': 2, 'ZK': 17, 'ZRO': 20, 'W': 3, 'STRK': 15, 
    'PIXEL': 19, 'MANTA': 18, 'ALT': 25, 'DYM': 6
}

# --- STRATEGY SETTINGS ---
DAYS_BEFORE_UNLOCK = 7    
BTC_PUMP_THRESHOLD = 7.0  
TIMEFRAME_UNLOCK = '4h'
TIMEFRAME_TREND = '1h'  # 1H is good for finding 200MA dips

class StrategyEngine:
    def __init__(self):
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        self.exchange.urls['api']['public'] = 'https://data-api.binance.vision/api/v3'

    async def fetch_ohlcv(self, symbol, timeframe, limit=300):
        """Fetches OHLCV data and returns a DataFrame."""
        try:
            bars = await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if not bars: return None
            
            df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
            df['timestamp'] = pd.to_datetime(df['ts'], unit='ms')
            return df
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return None

    def get_next_unlock_date(self, day):
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

    async def check_btc_safety(self):
        """Returns False if BTC pumped > 7% in last 3 days (Unsafe for shorts)."""
        df = await self.fetch_ohlcv('BTC/USDT', '4h', limit=20)
        if df is None: return False
        
        current_price = df.iloc[-1]['close']
        old_price = df.iloc[0]['open'] 
        change_pct = ((current_price - old_price) / old_price) * 100
        
        if change_pct > BTC_PUMP_THRESHOLD:
            logger.warning(f"⚠️ BTC Pumping ({change_pct:.2f}%). Short Strategies PAUSED.")
            return False
        return True

    async def save_signal(self, asset, timeframe, signal_type, detected_at):
        """Saves a detected signal to Supabase."""
        data = {
            "asset": asset,
            "timeframe": timeframe,
            "signal_type": signal_type,
            "detected_at": detected_at
        }
        try:
            self.supabase.table('market_scans').upsert(data, on_conflict="asset,timeframe,signal_type").execute()
            logger.info(f"✅ SIGNAL SAVED: {asset} [{signal_type}]")
        except Exception as e:
            logger.error(f"Database Error: {e}")

    # ---------------------------------------------------------
    # STRATEGY 1: UNLOCK SHORT (Vesting Tokens Only)
    # ---------------------------------------------------------
    async def run_unlock_strategy(self):
        """Scans specific tokens near their unlock dates."""
        is_safe = await self.check_btc_safety()
        if not is_safe: return 

        for token, unlock_day in UNLOCK_TOKENS.items():
            symbol = f"{token}/USDT"
            
            # 1. Date Check
            next_unlock = self.get_next_unlock_date(unlock_day)
            window_start = next_unlock - timedelta(days=DAYS_BEFORE_UNLOCK)
            now = datetime.now()

            if not (window_start <= now <= next_unlock):
                continue # Skip if not in the 7-day window

            # 2. Fetch Data
            df = await self.fetch_ohlcv(symbol, TIMEFRAME_UNLOCK)
            if df is None: continue

            # 3. Indicators (Bollinger Bands)
            df.ta.bbands(close=df['close'], length=20, std=2, append=True)
            bbu_col = 'BBU_20_2.0'

            # 4. Logic (Touch Upper BB + Red Candle)
            last_candle = df.iloc[-2] # Completed candle
            if last_candle['high'] >= last_candle[bbu_col] and last_candle['close'] < last_candle['open']:
                await self.save_signal(token, TIMEFRAME_UNLOCK, "STRATEGY_UNLOCK_SHORT", datetime.now().isoformat())

    # ---------------------------------------------------------
    # STRATEGY 2: BULLISH 200 MA RSI (Major Coins Only)
    # ---------------------------------------------------------
    async def run_trend_strategy(self):
        """Scans Major Coins (BTC, ETH, etc.) for trend pullbacks."""
        for token in MAJOR_COINS:
            symbol = f"{token}/USDT"
            
            # 1. Fetch Data
            df = await self.fetch_ohlcv(symbol, TIMEFRAME_TREND)
            if df is None or len(df) < 200: continue

            # 2. Indicators (SMA 200 & RSI 14)
            df['SMA_200'] = ta.sma(df['close'], length=200)
            df['RSI'] = ta.rsi(df['close'], length=14)

            # 3. Logic:
            # - Price > 200 SMA (Uptrend)
            # - RSI < 35 (Oversold Dip)
            # - Candle is Green (Bounce Started)
            curr = df.iloc[-1] # Current Live Candle is okay for RSI dip detection, or use -2 for confirmed
            
            is_uptrend = curr['close'] > curr['SMA_200']
            is_oversold = curr['RSI'] <= 35
            is_green = curr['close'] > curr['open']

            if is_uptrend and is_oversold and is_green:
                await self.save_signal(token, TIMEFRAME_TREND, "STRATEGY_BULLISH_200MA_RSI", datetime.now().isoformat())

    # ---------------------------------------------------------
    # MAIN RUNNER
    # ---------------------------------------------------------
    async def run_all(self):
        logger.info("🚀 Starting Strategy Scan...")
        await self.run_unlock_strategy()
        await self.run_trend_strategy()
        logger.info("🏁 Scan Complete.")
        await self.exchange.close()

# --- ENTRY POINT ---
if __name__ == "__main__":
    engine = StrategyEngine()
    asyncio.run(engine.run_all())