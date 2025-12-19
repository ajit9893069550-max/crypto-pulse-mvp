import re
import os
import json
import logging
from datetime import datetime, timedelta, timezone 
from flask import Flask, request, jsonify, render_template 
from flask_cors import CORS 
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
import ccxt 
from dotenv import load_dotenv

# Import database connection helper
from database_manager import get_db_connection

load_dotenv()

# --- CONFIGURATION & INITIALIZATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")

if not all([SUPABASE_URL, SUPABASE_KEY, JWT_SECRET]):
    logger.critical("FATAL: SUPABASE_URL, SUPABASE_KEY, and SUPABASE_JWT_SECRET must be set.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)

# --- JWT Configuration ---
app.config["JWT_SECRET_KEY"] = JWT_SECRET 
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)
jwt = JWTManager(app)

# --- CORS ---
CORS(app, resources={r"/api/*": {"origins": "*"}})

# --- CCXT CONFIGURATION (FIXED FOR RENDER/US RESTRICTIONS) ---
EXCHANGE = ccxt.binance({
    'enableRateLimit': True,
    'urls': {
        'api': {
            'public': 'https://data.binance.com/api/v3',
            'private': 'https://api.binance.com/api/v3',
        }
    }
})
SUPPORTED_TOKENS = ['BTC', 'ETH', 'SOL', 'BNB', 'ADA', 'XRP', 'DOGE'] 

# =================================================================
#                 FRONT-END ROUTES & GOOGLE AUTH FIX
# =================================================================

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    """
    FIX: This 'catch-all' route ensures that when Google redirects back 
    with a #access_token fragment, Flask serves index.html instead of a 404.
    """
    if path == "login.html":
        return render_template('login.html')
    if path == "register.html":
        return render_template('register.html')
    return render_template('index.html')

# =================================================================
#                         API AUTH ROUTES
# =================================================================

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    try:
        response = supabase.auth.sign_up({"email": email, "password": password})
        return jsonify({"message": "User created successfully", "user_id": response.user.id}), 201
    except Exception as e:
        logger.error(f"Signup Error: {e}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email, password = data.get('email'), data.get('password')
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if response.user:
            token = create_access_token(identity=response.user.id)
            return jsonify(access_token=token, user_id=response.user.id), 200
    except Exception as e:
        return jsonify({"error": "Invalid credentials"}), 401

# =================================================================
#                      DATA & ALERTS ROUTES
# =================================================================

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify({"SUPABASE_URL": SUPABASE_URL, "SUPABASE_KEY": SUPABASE_KEY}), 200

@app.route('/api/signals', methods=['GET'])
def get_signals():
    signal_type = request.args.get('type') 
    try:
        query = supabase.table('market_scans').select('*')
        if signal_type and signal_type != 'ALL':
            query = query.eq('signal_type', signal_type)
        response = query.order('detected_at', desc=True).limit(50).execute()
        results = [{"asset": r['asset'], "timeframe": r['timeframe'], "signal_type": r['signal_type'], "created_at": r['detected_at']} for r in response.data]
        return jsonify(results)
    except Exception as e:
        logger.error(f"API Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/create-alert', methods=['POST'])
@jwt_required()
def create_alert():
    user_uuid = get_jwt_identity() 
    data = request.get_json()

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
        
    try:
        with conn.cursor() as cur:
            # We use user_id::uuid cast in the policy, so string format is fine here
            cur.execute("""
                INSERT INTO public.alerts (user_id, asset, timeframe, alert_type, status)
                VALUES (%s, %s, %s, %s, 'ACTIVE')
            """, (user_uuid, data['asset'], data['timeframe'], data['signal_type']))
            conn.commit()
        return jsonify({"success": True}), 201
    except Exception as e:
        logger.error(f"Create Alert Error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/my-alerts', methods=['GET'])
@jwt_required()
def get_my_alerts():
    user_id = get_jwt_identity()
    try:
        # Check if profile exists (helps Google users initialize their row)
        profile = supabase.table('users').select('user_uuid').eq('user_uuid', user_id).execute()
        if not profile.data:
            supabase.table('users').insert({'user_uuid': user_id}).execute()
        
        response = supabase.table('alerts').select('*').eq('user_id', user_id).eq('status', 'ACTIVE').execute()
        return jsonify(response.data), 200
    except Exception as e:
        logger.error(f"My Alerts Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete-alert', methods=['POST'])
@jwt_required()
def delete_alert():
    user_id = get_jwt_identity()
    data = request.get_json()
    alert_id = data.get('alert_id')
    try:
        response = supabase.table('alerts')\
            .update({'status': 'DELETED'})\
            .eq('id', alert_id)\
            .eq('user_id', user_id)\
            .execute()
        
        if response.data:
            return jsonify({"message": "Deleted successfully"}), 200
        return jsonify({"error": "Alert not found"}), 404
    except Exception as e:
        logger.error(f"Delete Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/market-summary', methods=['GET'])
def get_market_summary():
    try:
        symbols = [f'{token}/USDT' for token in SUPPORTED_TOKENS]
        tickers = EXCHANGE.fetch_tickers(symbols)
        summary = [{'symbol': t['symbol'].replace('/', ''), 'price': t['last'], 'change_percent': t['percentage']} for t in tickers.values()]
        return jsonify(summary), 200
    except Exception as e:
        logger.error(f"Market Summary Error: {e}")
        return jsonify({"error": str(e)}), 500

@jwt.unauthorized_loader
def unauthorized_callback(c):
    return jsonify({"error": "No token provided"}), 401

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001)) 
    app.run(host='0.0.0.0', port=port)