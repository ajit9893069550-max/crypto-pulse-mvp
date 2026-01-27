import os
import asyncio
import gc
import pandas as pd
import pandas_ta as ta
import ccxt.async_support as ccxt
import logging
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StrategyEngine")

# --- CONFIGURATION ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

# --- WATCHLISTS ---
MAJOR_COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'LINK', 'MATIC']
UNLOCK_TOKENS = {
    'ENA': 2, 'ZK': 17, 'ZRO': 20, 'W': 3, 'STRK': 15, 
    'PIXEL': 19, 'MANTA': 18, 'ALT': 25, 'DYM': 6
}

DAYS_BEFORE_UNLOCK = 7    
BTC_PUMP_THRESHOLD = 7.0  
TIMEFRAME_UNLOCK = '4h'
TIMEFRAME_TREND = '1h' 

class StrategyEngine:
    def __init__(self):
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.exchange = None 

    async def init_exchange(self):
        """Initialize Exchange Connection with Minimal Caching"""
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True,
            }
        })
        self.exchange.urls['api']['public'] = 'https://data-api.binance.vision/api/v3'
        self.exchange.enableRateLimit = True

    async def fetch_ohlcv(self, symbol, timeframe, limit=300):
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
        df = await self.fetch_ohlcv('BTC/USDT', '4h', limit=20)
        if df is None: return False
        
        current_price = df.iloc[-1]['close']
        old_price = df.iloc[0]['open'] 
        change_pct = ((current_price - old_price) / old_price) * 100
        
        del df
        gc.collect()

        if change_pct > BTC_PUMP_THRESHOLD:
            logger.warning(f"⚠️ BTC Pumping ({change_pct:.2f}%). Short Strategies PAUSED.")
            return False
        return True

    async def save_signal(self, asset, timeframe, signal_type, detected_at):
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

    # --- UPDATED: UNLOCK STRATEGY (Pure Signal, No Past Data) ---
    async def run_unlock_strategy(self):
        is_safe = await self.check_btc_safety()
        if not is_safe: return 

        for token, unlock_day in UNLOCK_TOKENS.items():
            symbol = f"{token}/USDT"
            
            next_unlock = self.get_next_unlock_date(unlock_day)
            window_start = next_unlock - timedelta(days=DAYS_BEFORE_UNLOCK)
            now = datetime.now()

            # Only run if we are inside the 7-day window before unlock
            if not (window_start <= now <= next_unlock):
                continue 

            df = await self.fetch_ohlcv(symbol, TIMEFRAME_UNLOCK)
            if df is None: continue

            # Indicator: Bollinger Bands
            df.ta.bbands(close=df['close'], length=20, std=2, append=True)
            bbu_col = 'BBU_20_2.0'

            # Logic: Price touched Upper Band AND closed Red (Rejection)
            last_candle = df.iloc[-2]
            touched_band = last_candle['high'] >= last_candle[bbu_col]
            is_red = last_candle['close'] < last_candle['open']

            if touched_band and is_red:
                await self.save_signal(token, TIMEFRAME_UNLOCK, "STRATEGY_UNLOCK_SHORT", datetime.now().isoformat())
            
            # Cleanup
            del df
            gc.collect()
            await asyncio.sleep(1)

    # --- UPDATED: 200MA STRATEGY (Bullish & Bearish, Pure Signal) ---
    async def run_trend_strategy(self):
        for token in MAJOR_COINS:
            symbol = f"{token}/USDT"
            
            # Fetch just enough candles for 200 SMA
            df = await self.fetch_ohlcv(symbol, TIMEFRAME_TREND, limit=210) 
            if df is None or len(df) < 200: 
                del df
                gc.collect()
                continue

            df.ta.sma(length=200, append=True)
            df.ta.rsi(length=14, append=True)
            
            sma_col = 'SMA_200'
            rsi_col = 'RSI_14'

            # Analyze the last closed candle
            curr = df.iloc[-1]
            
            price = curr['close']
            sma200 = curr[sma_col]
            rsi = curr[rsi_col]
            
            is_green = curr['close'] > curr['open']
            is_red = curr['close'] < curr['open']

            # 1. BULLISH SETUP:
            # - Trend: Price > 200 MA
            # - Trigger: RSI <= 35 (Oversold)
            # - Confirmation: Green Candle
            if (price > sma200) and (rsi <= 35) and is_green:
                await self.save_signal(token, TIMEFRAME_TREND, "STRATEGY_BULLISH_200MA_RSI", datetime.now().isoformat())

            # 2. BEARISH SETUP:
            # - Trend: Price < 200 MA
            # - Trigger: RSI >= 65 (Overbought)
            # - Confirmation: Red Candle
            elif (price < sma200) and (rsi >= 65) and is_red:
                await self.save_signal(token, TIMEFRAME_TREND, "STRATEGY_BEARISH_200MA_RSI", datetime.now().isoformat())
            
            # Cleanup
            del df
            gc.collect()
            await asyncio.sleep(1)

    async def run_all(self):
        logger.info("🚀 Starting Strategy Scan...")
        await self.init_exchange()
        
        await self.run_unlock_strategy()
        await self.run_trend_strategy()
        
        logger.info("🏁 Scan Complete.")
        await self.exchange.close()
        self.exchange = None
        gc.collect()