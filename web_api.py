import os
import logging
from datetime import timedelta
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("WebAPI")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
# CRITICAL: Use Service Role Key for Admin tasks (like creating users)
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")

if not all([SUPABASE_URL, SUPABASE_KEY, JWT_SECRET]):
    logger.critical("❌ Missing Secrets! Check .env file.")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__, template_folder='templates')

# --- SECURITY ---
limiter = Limiter(get_remote_address, app=app, default_limits=["1000 per day"], storage_uri="memory://")
app.config["JWT_SECRET_KEY"] = JWT_SECRET
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)
jwt = JWTManager(app)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# --- API ROUTES ---

@app.route('/api/config', methods=['GET'])
def get_config():
    """Sends public config to Frontend."""
    return jsonify({
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": os.environ.get("SUPABASE_KEY"), # Send ANON key to frontend
        "BOT_USERNAME": os.environ.get("BOT_USERNAME", "CryptoPulse_Dev_Bot") # Dynamic Bot Name
    }), 200

@app.route('/api/login', methods=['POST'])
@limiter.limit("10 per hour")
def login():
    data = request.get_json()
    try:
        response = supabase.auth.sign_in_with_password({"email": data['email'], "password": data['password']})
        if response.user:
            token = create_access_token(identity=str(response.user.id))
            return jsonify(access_token=token, user_id=response.user.id), 200
    except Exception as e:
        logger.error(f"Login failed: {e}")
        return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/signup', methods=['POST'])
@limiter.limit("5 per hour")
def signup():
    data = request.get_json()
    try:
        response = supabase.auth.sign_up({"email": data['email'], "password": data['password']})
        if response.user:
            return jsonify({"message": "Success", "user_id": response.user.id}), 201
        return jsonify({"error": "Signup failed"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400

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
    try:
        # Optimized: Use Supabase Client (No more database_manager.py)
        response = supabase.table('alerts').insert({
            "user_id": user_uuid,
            "asset": data['asset'],
            "timeframe": data['timeframe'],
            "alert_type": data['signal_type'],
            "status": "ACTIVE"
        }).execute()
        return jsonify({"success": True}), 201
    except Exception as e:
        logger.error(f"Create Alert Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/my-alerts', methods=['GET'])
@jwt_required()
def get_my_alerts():
    user_id = get_jwt_identity()
    try:
        # Sync User Profile if missing
        user_check = supabase.table('users').select('user_uuid', count='exact').eq('user_uuid', user_id).execute()
        if user_check.count == 0:
            supabase.table('users').insert({'user_uuid': user_id}).execute()
            
        response = supabase.table('alerts').select('*').eq('user_id', user_id).eq('status', 'ACTIVE').execute()
        return jsonify(response.data), 200
    except Exception as e:
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

# --- FRONTEND SERVING ---
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if path.startswith('api/'): return jsonify({"error": "Not Found"}), 404
    if path == "login.html": return render_template('login.html')
    if path == "register.html": return render_template('register.html')
    return render_template('index.html')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=True)