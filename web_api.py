import os
import time
import json
import re
import requests
import logging
import pandas as pd
import ccxt
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv

# --- AI & ANALYTICS IMPORTS ---
from google import genai
from nixtla import NixtlaClient

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("WebAPI")

# Setup Keys & Clients
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "CryptoPulse_Bot")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NIXTLA_API_KEY = os.environ.get("NIXTLA_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.critical("❌ Missing Supabase Config!")
    exit(1)

# Initialize Clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Gemini Client
client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.error(f"Gemini Init Error: {e}")

# Nixtla Client (For Price Prediction)
nixtla_client = None
if NIXTLA_API_KEY:
    try:
        nixtla_client = NixtlaClient(api_key=NIXTLA_API_KEY)
    except Exception as e:
        logger.error(f"Nixtla Init Error: {e}")
else:
    logger.warning("⚠️ NIXTLA_API_KEY is missing! Price predictions will not work.")

# CCXT Exchange (For fetching historical data for Nixtla)
exchange = ccxt.binance({'enableRateLimit': True})

# ==============================================================================
#  HELPER FUNCTIONS (Nixtla & Data Fetching)
# ==============================================================================

def fetch_ohlcv_data(symbol, timeframe='4h', limit=500):
    """
    Fetches historical candle data using CCXT (Binance).
    Returns a DataFrame formatted for Nixtla (ds, y).
    """
    try:
        # Normalize symbol for CCXT (e.g. "BINANCE:BTCUSDT" -> "BTC/USDT")
        clean_symbol = symbol.replace('BINANCE:', '').replace(':', '')
        if '/' not in clean_symbol and 'USDT' in clean_symbol:
            clean_symbol = clean_symbol.replace('USDT', '/USDT')
        
        # Normalize timeframe (e.g. "1D" -> "1d")
        timeframe = timeframe.lower()
        
        # Fetch Data
        ohlcv = exchange.fetch_ohlcv(clean_symbol, timeframe, limit=limit)
        
        # Convert to Pandas DataFrame
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Format for Nixtla: 'ds' (Date) and 'y' (Target Value/Close Price)
        nixtla_df = df[['timestamp', 'close']].rename(columns={'timestamp': 'ds', 'close': 'y'})
        return nixtla_df, clean_symbol
        
    except Exception as e:
        logger.error(f"Data Fetch Error: {e}")
        return None, symbol

def get_nixtla_prediction(symbol, timeframe):
    """
    Uses Nixtla TimeGPT to predict the next price points.
    """
    if not nixtla_client:
        return "Nixtla API Key missing. Prediction unavailable."

    df, clean_symbol = fetch_ohlcv_data(symbol, timeframe)
    if df is None or df.empty:
        return "Not enough historical data for prediction."

    try:
        # Predict the next 12 periods (horizon)
        # freq='H' for hourly, 'D' for daily, etc. logic handled by Nixtla auto-infer or we pass simple freq
        forecast_df = nixtla_client.forecast(df=df, h=12, level=[80, 90])
        
        # Extract key insights
        current_price = df['y'].iloc[-1]
        future_price = forecast_df['TimeGPT'].iloc[-1]
        
        trend_direction = "UP" if future_price > current_price else "DOWN"
        pct_change = ((future_price - current_price) / current_price) * 100
        
        summary = f"""
        Quantitative Forecast for {clean_symbol} ({timeframe}):
        - Current Price: ${current_price:.2f}
        - Predicted Price (+12 candles): ${future_price:.2f}
        - Direction: {trend_direction} ({pct_change:.2f}%)
        - 80% Confidence Interval: ${forecast_df['TimeGPT-lo-80'].iloc[-1]:.2f} to ${forecast_df['TimeGPT-hi-80'].iloc[-1]:.2f}
        """
        return summary

    except Exception as e:
        logger.error(f"Nixtla Prediction Failed: {e}")
        return f"Prediction Error: {str(e)}"

# ==============================================================================
#  API ROUTES
# ==============================================================================

@app.route('/healthz', methods=['GET'])
def health_check():
    return jsonify({"status": "ok"}), 200

@app.route('/api/config')
def api_config():
    return jsonify({
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": os.environ.get("SUPABASE_KEY"),
        "BOT_USERNAME": BOT_USERNAME
    })

@app.route('/api/signals')
def api_signals():
    sig_type = request.args.get('type', 'ALL')
    try:
        query = supabase.table('market_scans').select("*").order('detected_at', desc=True).limit(50)
        if sig_type != 'ALL':
            query = query.eq('signal_type', sig_type)
        response = query.execute()
        return jsonify(response.data)
    except Exception as e:
        logger.error(f"Signal API Error: {e}")
        return jsonify([])

@app.route('/api/my-alerts')
def api_my_alerts():
    user_id = request.args.get('user_id')
    if not user_id: return jsonify([])
    try:
        response = supabase.table('alerts').select("*").eq('user_id', user_id).execute()
        return jsonify(response.data)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/create-alert', methods=['POST'])
def api_create_alert():
    try:
        data = request.json
        asset = data.get('asset')
        target_price = data.get('target_price')
        signal_type = data.get('signal_type')
        is_recurring = data.get('is_recurring', False)

        if signal_type == 'PRICE_TARGET' and target_price:
            try:
                symbol_clean = asset.replace('/', '') 
                url = f"https://data-api.binance.vision/api/v3/ticker/price?symbol={symbol_clean}"
                price_res = requests.get(url, timeout=2).json()
                current_price = float(price_res['price'])
                target = float(target_price)
                signal_type = "PRICE_TARGET_ABOVE" if target > current_price else "PRICE_TARGET_BELOW"
            except Exception as e:
                logger.error(f"Price fetch failed: {e}")

        response = supabase.table('alerts').insert({
            "user_id": data.get('user_id'),
            "asset": asset,
            "timeframe": data.get('timeframe'),
            "alert_type": signal_type,
            "target_price": target_price,
            "is_recurring": is_recurring,
            "status": "ACTIVE"
        }).execute()
        return jsonify({"success": True, "data": response.data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/delete-alert/<int:alert_id>', methods=['DELETE'])
def api_delete_alert(alert_id):
    try:
        supabase.table('alerts').delete().eq('id', alert_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/telegram-status')
def api_telegram_status():
    user_id = request.args.get('user_id')
    if not user_id: return jsonify({"linked": False})
    
    try:
        res = supabase.table('users').select('telegram_chat_id').eq('user_uuid', user_id).execute()
        if res.data and res.data[0].get('telegram_chat_id'):
            return jsonify({"linked": True})
    except:
        pass
    return jsonify({"linked": False})

@app.route('/api/strategies')
def api_strategies():
    try:
        strategies_res = supabase.table('strategies').select("*").execute()
        strategies = strategies_res.data
        for strat in strategies:
            perf_res = supabase.table('strategy_performance').select("*").eq('strategy_id', strat['id']).execute()
            strat['performance'] = perf_res.data
        return jsonify(strategies)
    except Exception as e:
        logger.error(f"Strategy API Error: {e}")
        return jsonify([])

# --- ROUTE: AI ANALYSIS (UPDATED: Uses Nixtla + Gemini, No Screenshots) ---
@app.route('/api/analyze', methods=['POST'])
def api_analyze_chart():
    if not client: return jsonify({"error": "Gemini API Key missing"}), 500
    
    data = request.json
    symbol = data.get('symbol', 'BINANCE:BTCUSDT')
    interval = data.get('interval', '4h') 
    
    try:
        # 1. Get Mathematical Forecast from Nixtla
        nixtla_summary = get_nixtla_prediction(symbol, interval)
        
        # 2. Prepare Prompt for Gemini
        # We pass the exact math from Nixtla so Gemini doesn't hallucinate numbers
        prompt = f"""
        You are a professional crypto trader. 
        I have run a quantitative prediction model (TimeGPT) for {symbol} on the {interval} timeframe.
        
        Here is the data:
        {nixtla_summary}
        
        Based on this quantitative forecast, provide a structured trading signal.
        Return ONLY valid JSON with no extra text:
        {{ 
            "trend": "Bullish/Bearish/Neutral", 
            "support": "Estimated Support Level", 
            "resistance": "Estimated Resistance Level", 
            "signal": "BUY/SELL/WAIT", 
            "reasoning": "Brief technical explanation combining the forecast with general market structure (max 20 words)." 
        }}
        """

        # 3. Call AI (Using updated model name)
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=[prompt]
            )
        except Exception as ai_error:
            if "429" in str(ai_error):
                return jsonify({"error": "AI Rate Limit. Please wait."}), 429
            if "404" in str(ai_error):
                return jsonify({"error": "AI Model Not Found."}), 404
            raise ai_error
        
        # 4. Parse Response
        text = re.sub(r"```json|```", "", response.text.strip()).strip()
        try: ai_data = json.loads(text)
        except: ai_data = {}
        
        data = {k.lower(): v for k, v in ai_data.items()}
        
        return jsonify({
            "trend": data.get("trend", "Neutral"),
            "support": data.get("support", "--"),
            "resistance": data.get("resistance", "--"),
            "signal": data.get("signal", "WAIT").upper(),
            "reasoning": data.get("reasoning", "Analysis complete.")
        })

    except Exception as e:
        logger.error(f"Analysis Failed: {e}")
        return jsonify({"error": str(e)}), 500

# --- ROUTE: SEARCH PROXY ---
@app.route('/api/search', methods=['GET'])
def api_search_proxy():
    query = request.args.get('q', '')
    if not query: return jsonify([])
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=6&newsCount=0"
        response = requests.get(url, headers=headers)
        data = response.json()
        results = []
        if 'quotes' in data:
            for item in data['quotes']:
                symbol = item.get('symbol', '')
                exchange = item.get('exchange', '')
                tv_exchange = 'BINANCE'
                tv_symbol = symbol
                
                # Simple Mapping for Yahoo -> TradingView symbols
                if exchange == 'NSI': tv_exchange = 'NSE'; tv_symbol = symbol.replace('.NS', '')
                elif exchange == 'BSE': tv_exchange = 'BSE'; tv_symbol = symbol.replace('.BO', '')
                elif item.get('quoteType') == 'CRYPTOCURRENCY': tv_symbol = symbol.replace('-', '') + 'T'

                results.append({"symbol": f"{tv_exchange}:{tv_symbol}", "name": item.get('shortname', symbol)})
        return jsonify(results)
    except: return jsonify([])

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if path.startswith('api/'): return jsonify({"error": "Not Found"}), 404
    if path == "login.html": return render_template('login.html', bot_username=BOT_USERNAME)
    return render_template('index.html', bot_username=BOT_USERNAME)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)