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
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
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
        prev_closed_row = df.iloc[-3]
        last_closed_ts = datetime.fromtimestamp(last_closed_row['ts'] / 1000, tz=timezone.utc)
        asset_name = symbol.replace('/USDT', '')

        # 3. CALCULATE INDICATORS
        df.ta.rsi(length=14, append=True)
        df.ta.sma(length=50, append=True)
        df.ta.sma(length=200, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.bbands(length=20, std=2, append=True)
        df.ta.stochrsi(length=14, rsi_length=14, k=3, d=3, append=True)
        
        # --- DYNAMIC COLUMN MAPPING ---
        # This prevents "KeyError" by finding the column name that matches the indicator
        def get_col(prefix):
            match = [c for c in df.columns if c.startswith(prefix)]
            if not match:
                raise KeyError(f"Technical Indicator column with prefix '{prefix}' not found.")
            return match[0]

        cols = {
            'rsi': get_col('RSI_14'),
            'sma50': get_col('SMA_50'),
            'sma200': get_col('SMA_200'),
            'ema20': get_col('EMA_20'),
            'macd': get_col('MACD_12_26_9'),
            'macds': get_col('MACDs_12_26_9'),
            'bbu': get_col('BBU_20'), # Matches BBU_20_2.0
            'bbl': get_col('BBL_20'), # Matches BBL_20_2.0
            'bbm': get_col('BBM_20'),
            'stochk': get_col('STOCHRSIk'),
            'stochd': get_col('STOCHRSId')
        }

        # 4. SIGNAL LOGIC
        last = df.iloc[-2]
        prev = df.iloc[-3]
        findings = []

        # Trend Crossovers
        if last[cols['sma50']] > last[cols['sma200']] and prev[cols['sma50']] <= prev[cols['sma200']]:
            findings.append("GOLDEN_CROSS")
        if last[cols['sma50']] < last[cols['sma200']] and prev[cols['sma50']] >= prev[cols['sma200']]:
            findings.append("DEATH_CROSS")
        
        # Overbought / Oversold
        if last[cols['rsi']] < 30: findings.append("RSI_OVERSOLD")
        if last[cols['rsi']] > 70: findings.append("RSI_OVERBOUGHT")
        
        # MACD logic
        if last[cols['macd']] > last[cols['macds']] and prev[cols['macd']] <= prev[cols['macds']]:
            findings.append("MACD_BULL_CROSS")
        if last[cols['macd']] < last[cols['macds']] and prev[cols['macd']] >= prev[cols['macds']]:
            findings.append("MACD_BEAR_CROSS")
        
        # Volatility (Bollinger Squeeze and Breakouts)
        bb_width = (last[cols['bbu']] - last[cols['bbl']]) / last[cols['bbm']]
        if bb_width < 0.05: findings.append("BB_SQUEEZE")
        if last['close'] > last[cols['bbu']]: findings.append("BB_UPPER_BREAKOUT")
        if last['low'] < last[cols['bbl']]: findings.append("BB_LOWER_TOUCH")
        
        # Momentum & Volume
        if last['vol'] > df['vol'].rolling(20).mean().iloc[-2] * 2.5: 
            findings.append("VOLUME_SURGE")
        if last[cols['stochd']] < 20 and last[cols['stochk']] > last[cols['stochd']]: 
            findings.append("STOCH_RSI_BULLISH")

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
                    # Upsert handles the UNIQUE constraint (asset, timeframe, signal_type)
                    supabase.table('market_scans').upsert(data).execute()
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