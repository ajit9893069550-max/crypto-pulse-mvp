import os
import logging
from flask import Flask, render_template, jsonify, request
from supabase import create_client, Client
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
app = Flask(__name__, static_folder='static', template_folder='templates')

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("WebAPI")

# Setup Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "CryptoPulse_Bot")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.critical("❌ Missing Supabase Config!")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==============================================================================
#  API ROUTES (Must be defined BEFORE the catch-all)
# ==============================================================================

@app.route('/api/config')
def api_config():
    """Returns public config for the frontend."""
    return jsonify({
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": os.environ.get("SUPABASE_KEY"), # Public Anon Key
        "BOT_USERNAME": BOT_USERNAME
    })

@app.route('/api/signals')
def api_signals():
    """Returns market scans filtered by type."""
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
    """Returns active alerts for a specific user."""
    user_id = request.args.get('user_id')
    if not user_id: 
        return jsonify([])
    
    try:
        response = supabase.table('alerts').select("*").eq('user_id', user_id).execute()
        return jsonify(response.data)
    except Exception as e:
        logger.error(f"My Alerts API Error: {e}")
        return jsonify({"error": str(e)})


@app.route('/api/create-alert', methods=['POST'])
def api_create_alert():
    """Creates a new alert with Recurring option."""
    try:
        data = request.json
        asset = data.get('asset')
        target_price = data.get('target_price')
        signal_type = data.get('signal_type')
        is_recurring = data.get('is_recurring', False) # New Field

        # --- SMART DIRECTION LOGIC (Same as before) ---
        if signal_type == 'PRICE_TARGET' and target_price:
            try:
                symbol_clean = asset.replace('/', '') 
                url = f"https://data-api.binance.vision/api/v3/ticker/price?symbol={symbol_clean}"
                price_res = requests.get(url, timeout=2).json()
                current_price = float(price_res['price'])
                target = float(target_price)

                if target > current_price:
                    signal_type = "PRICE_TARGET_ABOVE"
                else:
                    signal_type = "PRICE_TARGET_BELOW"
            except Exception as e:
                logger.error(f"Price fetch failed: {e}")

        # 3. Save to Database
        response = supabase.table('alerts').insert({
            "user_id": data.get('user_id'),
            "asset": asset,
            "timeframe": data.get('timeframe'),
            "alert_type": signal_type,
            "target_price": target_price,
            "is_recurring": is_recurring, # <--- Save this
            "status": "ACTIVE"
        }).execute()
        
        return jsonify({"success": True, "data": response.data})
    except Exception as e:
        logger.error(f"Create Alert Error: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/delete-alert/<int:alert_id>', methods=['DELETE'])
def api_delete_alert(alert_id):
    """Deletes an alert."""
    try:
        supabase.table('alerts').delete().eq('id', alert_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/telegram-status')
def api_telegram_status():
    """Checks if user has linked Telegram."""
    user_id = request.args.get('user_id')
    if not user_id: return jsonify({"linked": False})
    
    try:
        res = supabase.table('users').select('telegram_chat_id').eq('user_uuid', user_id).execute()
        if res.data and res.data[0].get('telegram_chat_id'):
            return jsonify({"linked": True})
    except:
        pass
    return jsonify({"linked": False})

# --- NEW ROUTE: STRATEGIES ---
@app.route('/api/strategies')
def api_strategies():
    """Returns all strategies with their performance data."""
    try:
        # 1. Fetch Strategies
        strategies_res = supabase.table('strategies').select("*").execute()
        strategies = strategies_res.data

        # 2. Fetch Performance Data for each strategy
        for strat in strategies:
            perf_res = supabase.table('strategy_performance')\
                .select("*")\
                .eq('strategy_id', strat['id'])\
                .execute()
            strat['performance'] = perf_res.data

        return jsonify(strategies)
    except Exception as e:
        logger.error(f"Strategy API Error: {e}")
        return jsonify([])

# ==============================================================================
#  FRONTEND SERVING (Catch-All)
# ==============================================================================

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    # 1. Block invalid API calls that fell through
    if path.startswith('api/'): 
        return jsonify({"error": "Not Found"}), 404
    
    # 2. Serve Login Page (Pass bot username)
    if path == "login.html": 
        return render_template('login.html', bot_username=BOT_USERNAME)

    # 3. Default: Serve Dashboard
    return render_template('index.html', bot_username=BOT_USERNAME)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)