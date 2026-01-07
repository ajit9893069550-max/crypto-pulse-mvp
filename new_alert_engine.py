import os
import pandas as pd
import pandas_ta as ta
import ccxt.async_support as ccxt
import logging
import asyncio
from datetime import datetime, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SignalEngine")

# --- SUPABASE CONFIG ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
# Use Service Role Key if available for better write permissions, otherwise generic key
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- EXCHANGE CONFIG ---
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
        'adjustForTimeDifference': True
    }
})

# Use the reliable data mirror for market data to bypass US/Restricted restrictions
exchange.urls['api']['public'] = 'https://data-api.binance.vision/api/v3'

async def analyze_asset(symbol, timeframe):
    """Fetches data, calculates indicators, and saves signals to Supabase."""
    try:
        # 1. Fetch OHLCV Data
        bars = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=250)
        if not bars or len(bars) < 200: 
            return
        
        df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
        df[['open', 'high', 'low', 'close', 'vol']] = df[['open', 'high', 'low', 'close', 'vol']].apply(pd.to_numeric)
        
        # 2. Timing Logic
        # -2 is the last CLOSED candle to avoid repainting signals
        last_closed_row = df.iloc[-2]
        last_closed_ts = datetime.fromtimestamp(last_closed_row['ts'] / 1000, tz=timezone.utc)
        asset_name = symbol.replace('/USDT', '')

        # 3. CALCULATE INDICATORS
        # Ensure 'append=True' so they are added to the DataFrame
        df.ta.rsi(length=14, append=True)
        df.ta.sma(length=50, append=True)
        df.ta.sma(length=200, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.bbands(length=20, std=2, append=True)
        df.ta.stochrsi(length=14, rsi_length=14, k=3, d=3, append=True)
        
        # --- DYNAMIC COLUMN MAPPING ---
        # This prevents "KeyError" by finding the column name that matches the indicator prefix
        def get_col(prefix):
            match = [c for c in df.columns if c.startswith(prefix)]
            if not match:
                # Fallback or strict error
                return None 
            return match[0]

        cols = {
            'rsi': get_col('RSI_14'),
            'sma50': get_col('SMA_50'),
            'sma200': get_col('SMA_200'),
            'ema20': get_col('EMA_20'),
            'macd': get_col('MACD_12_26_9'),
            'macds': get_col('MACDs_12_26_9'),
            'bbu': get_col('BBU_20'), 
            'bbl': get_col('BBL_20'), 
            'bbm': get_col('BBM_20'),
            'stochk': get_col('STOCHRSIk'),
            'stochd': get_col('STOCHRSId')
        }

        # Validate we found all columns before proceeding
        if None in cols.values():
            return
        
        
        # 4. SIGNAL LOGIC
        last = df.iloc[-2]
        prev = df.iloc[-3]
        
        # Helper: Calculate Average Volume (last 20 candles)
        avg_vol = df['vol'].rolling(20).mean().iloc[-2]
        vol_surge = last['vol'] > (avg_vol * 2.0) # Volume is 200% of average

        findings = []

        # --- A. CLASSIC TREND SIGNALS ---
        # Golden Cross / Death Cross
        if last[cols['sma50']] > last[cols['sma200']] and prev[cols['sma50']] <= prev[cols['sma200']]:
            findings.append("GOLDEN_CROSS")
        if last[cols['sma50']] < last[cols['sma200']] and prev[cols['sma50']] >= prev[cols['sma200']]:
            findings.append("DEATH_CROSS")

        # MACD logic
        if last[cols['macd']] > last[cols['macds']] and prev[cols['macd']] <= prev[cols['macds']]:
            findings.append("MACD_BULL_CROSS")
        if last[cols['macd']] < last[cols['macds']] and prev[cols['macd']] >= prev[cols['macds']]:
            findings.append("MACD_BEAR_CROSS")

        # --- B. SNIPER SETUPS (High Probability) ---
        
        # Sniper Buy (Reversal at Support)
        if last[cols['rsi']] < 35 and last['low'] <= last[cols['bbl']] and vol_surge:
            findings.append("SNIPER_BUY_REVERSAL")

        # Sniper Sell (Rejection at Resistance)
        if last[cols['rsi']] > 65 and last['high'] >= last[cols['bbu']] and vol_surge:
            findings.append("SNIPER_SELL_REJECTION")

        # Momentum Breakout
        if last[cols['macd']] > last[cols['macds']] and prev[cols['macd']] <= prev[cols['macds']] and vol_surge:
             findings.append("MOMENTUM_BREAKOUT")

        # 5. SAVE TO SUPABASE
        if findings:
            for signal in findings:
                data = {
                    "asset": asset_name,
                    "timeframe": timeframe,
                    "signal_type": signal,
                    "detected_at": last_closed_ts.isoformat()
                }
                try:
                    # Clean upsert call
                    supabase.table('market_scans').upsert(data, on_conflict="asset,timeframe,signal_type").execute()
                    logger.info(f"✅ Signal Saved: {asset_name} | {timeframe} | {signal}")
                except Exception as db_err:
                    logger.error(f"Supabase Upsert Failed for {asset_name}: {db_err}")

    except Exception as e:
        logger.error(f"Error analyzing {symbol} on {timeframe}: {e}")

async def close_exchange():
    """Closes the exchange session gracefully."""
    if exchange:
        await exchange.close()
        logger.info("Exchange connection closed.")