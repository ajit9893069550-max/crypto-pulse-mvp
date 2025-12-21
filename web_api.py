import re
import os
import json
import logging
from datetime import datetime, timedelta, timezone 
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS 
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager
from supabase import create_client, Client
import ccxt 
from dotenv import load_dotenv

# Import database connection helper
from database_manager import get_db_connection

load_dotenv()

# --- CONFIGURATION & INITIALIZATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebAPI")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
# CRITICAL: Backend uses Service Role Key to bypass RLS for admin tasks
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")

if not all([SUPABASE_URL, SUPABASE_KEY, JWT_SECRET]):
    logger.critical("FATAL: Missing SUPABASE_URL, SUPABASE_KEY, or JWT_SECRET.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__, template_folder='templates')

# --- JWT Configuration ---
app.config["JWT_SECRET_KEY"] = JWT_SECRET 
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)
jwt = JWTManager(app)

# --- CORS ---
CORS(app, resources={r"/api/*": {"origins": "*"}})

# --- CCXT CONFIGURATION ---
EXCHANGE = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot', 'adjustForTimeDifference': True},
    'urls': { 'api': { 'public': 'https://data-api.binance.vision/api/v3' } }
})
SUPPORTED_TOKENS = ['BTC', 'ETH', 'SOL', 'BNB', 'ADA', 'XRP', 'DOGE'] 

# =================================================================
#                         API ROUTES (JSON)
# =================================================================

@app.route('/api/config', methods=['GET'])
def get_config():
    """Provides keys for the frontend. Frontend uses ANON_KEY."""
    return jsonify({
        "SUPABASE_URL": SUPABASE_URL, 
        "SUPABASE_KEY": os.environ.get("SUPABASE_KEY") 
    }), 200

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()
    try:
        response = supabase.auth.sign_up({"email": data['email'], "password": data['password']})
        return jsonify({"message": "Success", "user_id": response.user.id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    try:
        response = supabase.auth.sign_in_with_password({"email": data['email'], "password": data['password']})
        if response.user:
            token = create_access_token(identity=str(response.user.id))
            return jsonify(access_token=token, user_id=response.user.id), 200
    except Exception as e:
        return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/signals', methods=['GET'])
def get_signals():
    signal_type = request.args.get('type') 
    try:
        query = supabase.table('market_scans').select('*')
        if signal_type and signal_type != 'ALL':
            query = query.eq('signal_type', signal_type)
        response = query.order('detected_at', desc=True).limit(50).execute()
        return jsonify(response.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/create-alert', methods=['POST'])
@jwt_required()
def create_alert():
    user_uuid = get_jwt_identity() 
    data = request.get_json()
    conn = get_db_connection()
    if not conn: return jsonify({"error": "DB Fail"}), 500
    try:
        with conn.cursor() as cur:
            # Explicitly cast %s to uuid to satisfy the PostgreSQL type checker
            cur.execute("""
                INSERT INTO public.alerts (user_id, asset, timeframe, alert_type, status)
                VALUES (%s::uuid, %s, %s, %s, 'ACTIVE')
            """, (user_uuid, data['asset'], data['timeframe'], data['signal_type']))
            conn.commit()
        return jsonify({"success": True}), 201
    except Exception as e:
        logger.error(f"SQL Insert Error: {e}")
        return jsonify({"error": "Database error"}), 500
    finally:
        conn.close()

@app.route('/api/my-alerts', methods=['GET'])
@jwt_required()
def get_my_alerts():
    user_id = get_jwt_identity()
    try:
        # Check profile exists. Service Role bypasses RLS here.
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
    try:
        supabase.table('alerts').update({'status': 'DELETED'})\
            .eq('id', data['alert_id']).eq('user_id', user_id).execute()
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/market-summary', methods=['GET'])
def get_market_summary():
    try:
        symbols = [f'{token}/USDT' for token in SUPPORTED_TOKENS]
        tickers = EXCHANGE.fetch_tickers(symbols)
        summary = []
        for t in tickers.values():
            summary.append({
                'symbol': t['symbol'].replace('/', ''), 
                'price': t['last'], 
                'change_percent': t['percentage']
            })
        return jsonify(summary), 200
    except Exception as e:
        logger.error(f"Market Summary Error: {e}")
        return jsonify({"error": str(e)}), 500

# =================================================================
#                   FRONT-END ROUTES (HTML)
# =================================================================

@app.route('/login.html')
def login_page():
    return render_template('login.html')

@app.route('/register.html')
def register_page():
    return render_template('register.html')

@app.route('/', defaults={'path': ''}, endpoint='dashboard_home')
@app.route('/<path:path>')
def catch_all(path):
    if path.startswith('api/'):
        return jsonify({"error": "API Route Not Found"}), 404
    return render_template('index.html')

# =================================================================
#                        ERROR HANDLERS
# =================================================================

@jwt.unauthorized_loader
def unauthorized_callback(c):
    return jsonify({"error": "No token provided"}), 401

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({"error": "Token expired"}), 401

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001)) 
    app.run(host='0.0.0.0', port=port)