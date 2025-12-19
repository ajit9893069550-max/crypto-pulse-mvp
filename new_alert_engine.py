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

# --- EXCHANGE CONFIG (SYNCED WITH WEB_API) ---
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
        'adjustForTimeDifference': True
    }
})
# Use the reliable data mirror for market data to bypass US restrictions
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
        
        # 2. Alignment Logic
        # Use -2 for the last COMPLETED candle to avoid repaint
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
        
        # FIXED: Dynamic Column Mapping for StochRSI (handles case sensitivity)
        cols = {
            'rsi': 'RSI_14',
            'sma50': 'SMA_50',
            'sma200': 'SMA_200',
            'ema20': 'EMA_20',
            'macd': 'MACD_12_26_9',
            'macds': 'MACDs_12_26_9',
            'bbu': 'BBU_20_2.0',
            'bbl': 'BBL_20_2.0',
            'bbm': 'BBM_20_2.0',
            # Pandas_ta column names can vary (STOCHRSIk vs STOCHRSIk_14_14_3_3)
            'stochk': [c for c in df.columns if 'STOCHRSIk' in c][0],
            'stochd': [c for c in df.columns if 'STOCHRSId' in c][0]
        }

        # 4. SIGNAL LOGIC
        last = df.iloc[-2]
        prev = df.iloc[-3]
        findings = []

        # Trend & Crossovers
        if last[cols['sma50']] > last[cols['sma200']] and prev[cols['sma50']] <= prev[cols['sma200']]:
            findings.append("GOLDEN_CROSS")
        if last[cols['sma50']] < last[cols['sma200']] and prev[cols['sma50']] >= prev[cols['sma200']]:
            findings.append("DEATH_CROSS")
        
        # Overbought / Oversold
        if last[cols['rsi']] < 30: findings.append("RSI_OVERSOLD")
        if last[cols['rsi']] > 70: findings.append("RSI_OVERBOUGHT")
        
        # MACD
        if last[cols['macd']] > last[cols['macds']] and prev[cols['macd']] <= prev[cols['macds']]:
            findings.append("MACD_BULL_CROSS")
        if last[cols['macd']] < last[cols['macds']] and prev[cols['macd']] >= prev[cols['macds']]:
            findings.append("MACD_BEAR_CROSS")
        
        # Volatility & Bollinger
        bb_width = (last[cols['bbu']] - last[cols['bbl']]) / last[cols['bbm']]
        if bb_width < 0.05: findings.append("BB_SQUEEZE")
        if last['close'] > last[cols['bbu']]: findings.append("BB_UPPER_BREAKOUT")
        if last['low'] < last[cols['bbl']]: findings.append("BB_LOWER_TOUCH")
        
        # Volume & Momentum
        if last['vol'] > df['vol'].rolling(20).mean().iloc[-2] * 2.5: 
            findings.append("VOLUME_SURGE")
        if last[cols['stochd']] < 20 and last[cols['stochk']] > last[cols['stochd']]: 
            findings.append("STOCH_RSI_BULLISH")
        if last['close'] >= df['high'].shift(1).rolling(24).max().iloc[-2]: 
            findings.append("NEW_HIGH")

        # 5. SAVE TO SUPABASE (Using ISO strings for detected_at)
        if findings:
            for signal in findings:
                data = {
                    "asset": asset_name,
                    "timeframe": timeframe,
                    "signal_type": signal,
                    "detected_at": last_closed_ts.strftime('%Y-%m-%dT%H:%M:%S+00:00')
                }
                # Ensure you have a UNIQUE CONSTRAINT on (asset, timeframe, signal_type) in Supabase
                supabase.table('market_scans').upsert(data).execute()
                logger.info(f"✅ {asset_name} | {timeframe} | {signal}")

    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {e}")

async def close_exchange():
    """Closes the exchange session gracefully."""
    if exchange:
        await exchange.close()
        logger.info("Exchange connection closed.")