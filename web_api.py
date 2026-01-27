import os
import time
import json
import re
import requests
import logging
import pathlib
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv

# --- AI & BROWSER IMPORTS ---
from google import genai
import PIL.Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from io import BytesIO

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("WebAPI")

# Setup Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "CryptoPulse_Bot")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.critical("❌ Missing Supabase Config!")
    exit(1)

if not GEMINI_API_KEY:
    logger.warning("⚠️ GEMINI_API_KEY is missing! AI Analysis features will not work.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ==============================================================================
#  AI & CHARTING FUNCTIONS (Helper Logic)
# ==============================================================================

def take_server_screenshot(symbol, interval):
    """Captures a screenshot of the TradingView widget via Headless Chrome."""
    logger.info(f"📸 Server: Headless browser for {symbol} on {interval}...")
    
    # 1. Define the correct path explicitly (Fallback for Render)
    # This is where your render-build.sh put the file
    hardcoded_path = "/opt/render/project/src/chrome/opt/google/chrome/google-chrome"
    
    # 2. Chrome Options
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # 3. Find the Binary
    env_bin = os.environ.get("CHROME_BIN")
    if env_bin and os.path.exists(env_bin):
        chrome_options.binary_location = env_bin
        logger.info(f"✅ Using CHROME_BIN from Env: {env_bin}")
    elif os.path.exists(hardcoded_path):
        chrome_options.binary_location = hardcoded_path
        logger.info(f"✅ Using Hardcoded Path: {hardcoded_path}")
    else:
        logger.warning("⚠️ No Custom Chrome found! Trying default system path...")

    # 4. Generate HTML
    # Full TV mapping logic...
    mapping = {
        "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
        "1h": "60", "2h": "120", "4h": "240", "6h": "360", "8h": "480", "12h": "720",
        "1d": "D", "3d": "3D", "1w": "W", "1m_month": "1M" 
    }
    norm_interval = interval.lower()
    if interval == "1M": norm_interval = "1m_month"
    tv_interval = mapping.get(norm_interval, "240")

    html_content = f"""
    <html>
    <body style="margin:0; background:#131722; overflow:hidden;">
        <div class="tradingview-widget-container" style="height:100vh; width:100vw;">
            <div id="tradingview_widget"></div>
            <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
            <script type="text/javascript">
            new TradingView.widget({{
                "autosize": true,
                "symbol": "{symbol}",
                "interval": "{tv_interval}",
                "timezone": "Asia/Kolkata",
                "theme": "dark",
                "style": "1",
                "locale": "en",
                "enable_publishing": false,
                "hide_side_toolbar": true,
                "container_id": "tradingview_widget",
                "studies": ["MASimple@tv-basicstudies", "RSI@tv-basicstudies", "BB@tv-basicstudies"]
            }});
            </script>
        </div>
    </body>
    </html>
    """

    temp_file = os.path.abspath("temp_chart.html")
    with open(temp_file, "w") as f: f.write(html_content)
    file_url = pathlib.Path(temp_file).as_uri()

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(file_url)
        time.sleep(4) 
        png_data = driver.get_screenshot_as_png()
        return PIL.Image.open(BytesIO(png_data))
        
    except Exception as e:
        # CRITICAL: We now raise the error so the frontend sees it
        logger.error(f"Browser Critical Fail: {str(e)}")
        raise Exception(f"Browser Error: {str(e)}") 
        
    finally:
        if driver: driver.quit()
        if os.path.exists(temp_file): os.remove(temp_file)

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

# --- ROUTE: AI ANALYSIS ---
@app.route('/api/analyze', methods=['POST'])
def api_analyze_chart():
    if not client: return jsonify({"error": "Gemini API Key missing"}), 500
    
    data = request.json
    symbol = data.get('symbol', 'BINANCE:BTCUSDT')
    interval = data.get('interval', '4h') 
    
    try:
        # Attempt to get the screenshot
        img = take_server_screenshot(symbol, interval)
        
        # If the function above raised an exception, we jump to the 'except' block below.
        # If it returned None (but no exception), we catch it here:
        if not img: 
            return jsonify({"error": "Screenshot returned Empty Data (Check Logs)"}), 500

        # ... (Rest of your Gemini AI Code) ...
        prompt = f"""
        You are a professional crypto trader. Analyze this {interval} chart for {symbol}.
        Return ONLY valid JSON with no extra text:
        {{ "trend": "Bullish/Bearish/Neutral", "support": "Price Level", "resistance": "Price Level", "signal": "BUY/SELL/WAIT", "reasoning": "Brief technical explanation (max 20 words)." }}
        """
        response = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt, img])
        
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
        # This will now print the REAL browser error to your screen
        logger.error(f"AI/Browser Error: {e}")
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