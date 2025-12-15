import re
import os
import json
import logging
import asyncio 
from datetime import datetime, timedelta, timezone 
from flask import Flask, request, jsonify, render_template 
from flask_cors import CORS 
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager
from supabase import create_client, Client
from supabase_auth.errors import AuthApiError
import ccxt.async_support as ccxt 

# --- CONFIGURATION & INITIALIZATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Supabase Configuration ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.critical("FATAL: SUPABASE_URL and SUPABASE_KEY environment variables must be set.")

try:
    # Initialize the Supabase Client (This will fail if SUPABASE_URL/KEY are missing)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    # The app will continue to run, but auth routes relying on 'supabase' will fail.

# IMPORTANT: Flask will look for HTML files in a folder named 'templates'
app = Flask(__name__)

# --- JWT Configuration ---
# 🛑 CRITICAL FIX: Load JWT_SECRET_KEY securely from the environment
app.config["JWT_SECRET_KEY"] = os.environ.get("SUPABASE_JWT_SECRET") 

if not app.config["JWT_SECRET_KEY"]:
    raise EnvironmentError(
        "FATAL: SUPABASE_JWT_SECRET environment variable must be set (Key used: SUPABASE_JWT_SECRET)."
    )

app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)
jwt = JWTManager(app)

# =================================================================
# --- CRITICAL FIX: Custom JWT Error Handlers (Ensures clean 401s) ---
# =================================================================
@jwt.unauthorized_loader
def unauthorized_callback(callback):
    """Handler for missing token, e.g., no 'Authorization' header."""
    return jsonify({
        "error": "Authorization failed: Missing token in request header. Please log in.",
        "status_code": 401
    }), 401

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    """Handler for expired tokens."""
    return jsonify({
        "error": "Authorization failed: The token has expired. Please log in again.",
        "status_code": 401
    }), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    """Handler for tokens that are structurally invalid, malformed, or have a bad signature."""
    return jsonify({
        "error": "Authorization failed: Token is invalid or malformed. Please re-login.",
        "details": str(error),
        "status_code": 401
    }), 401

# --- CORS Configuration ---
# Allow all origins for API endpoints for simplicity, or specify your Render domain (better security)
# CORS(app, resources={r"/api/*": {"origins": "https://crypto-pulse-dashboard1.onrender.com"}})
CORS(app, resources={r"/api/*": {"origins": "*"}})

# --- CCXT Configuration ---
EXCHANGE_ID = 'binanceus' 

async def get_exchange():
    """Returns an exchange object with rate limiting enabled."""
    return ccxt.__getattribute__(EXCHANGE_ID)({'enableRateLimit': True})


# -----------------------------------------------------------------
# --- SUPPORTED ASSETS (MUST MATCH PARSER) ---
SUPPORTED_TOKENS = ['BTC', 'ETH', 'SOL', 'BNB', 'ADA', 'XRP', 'DOGE'] 
# -----------------------------------------------------------------


# --- Helper Functions ---
def default_serializer(obj):
    """Custom JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

def parse_alert_phrase(phrase):
    """
    Parses a plain English phrase into structured alert data, 
    handling PRICE_TARGET, GOLDEN_CROSS, and DEATH_CROSS.
    """
    phrase = phrase.upper().strip()
    
    # List of supported assets for parsing (matching SUPPORTED_TOKENS list)
    SUPPORTED_ASSETS_REGEX = r'(BTC|ETH|SOL|BNB|ADA|DOGE|XRP)'
    
    # 1. Check for Complex MA Cross Alerts (50 MA / 200 MA)
    if 'CROSS' in phrase:
        if 'GOLDEN' in phrase:
            sub_type = 'MA_CROSS' 
            condition = 'ABOVE'
        elif 'DEATH' in phrase:
            sub_type = 'MA_CROSS' 
            condition = 'BELOW'
        else:
            raise ValueError("Crossover alert must specify 'Golden Cross' or 'Death Cross'.")
            
        # Regex to find asset (e.g., BTC, ETH) and timeframe (e.g., 1D, 4H)
        match = re.search(f'{SUPPORTED_ASSETS_REGEX}\\s*.*?(\\d+[HDWM])', phrase)
        
        if match:
            asset = match.group(1)
            timeframe = match.group(2)
            
            # CRITICAL FIX: Convert timeframe to lowercase for CCXT compatibility
            timeframe = timeframe.lower() 
            
            return {
                'alert_type': sub_type, 
                'asset': asset, 
                'timeframe': timeframe, 
                'operator': None, 
                'target_value': None,
                'params': { 
                    'condition': condition, 
                    'fast_ma': 50,  # Default periods for engine
                    'slow_ma': 200
                }
            }
        else:
            raise ValueError("Crossover alert requires an asset (e.g., BTC) and a timeframe (e.g., 1D).")
            
    # 2. Check for Simple Price Alerts
    match = re.search(f'{SUPPORTED_ASSETS_REGEX}\\s*([<>])\\s*([\\d,.]+)', phrase)
    if match:
        asset = match.group(1)
        operator = match.group(2)
        target_value = float(match.group(3).replace(',', ''))
        
        return {
            'alert_type': 'PRICE_TARGET', 
            'asset': asset, 
            'operator': operator, 
            'target_value': target_value, 
            'timeframe': None, 
            'params': {
                'target_price': target_value,
                'condition': 'ABOVE' if operator == '>' else 'BELOW'
            }
        }
    
    raise ValueError("Invalid alert format. Please use: 'BTC > 65000' or 'Golden Cross on ETH 4H'.")

# --- Database Helper Functions (Using Supabase) ---

def fetch_user_alerts(user_id):
    """Fetches ACTIVE alerts from the database for the given user_id."""
    if not supabase: return []
    response = supabase.table('alerts').select('*').eq('user_id', user_id).eq('status', 'ACTIVE').execute()
    return response.data

def deactivate_alert(alert_id, user_id, status='DELETED'):
    """
    Logic for soft deletion (marking status as 'DELETED').
    FIXED: Only updates the 'status' column, solving the 400/500 error 
    caused by a non-existent 'updated_at' column in the Supabase schema.
    """
    if not supabase: return False
    
    # --- CRITICAL FIX: Only update the 'status' column ---
    response = supabase.table('alerts').update({
        'status': status, 
        # 'updated_at' is REMOVED from the dictionary
    }).eq('id', alert_id).eq('user_id', user_id).execute()

    return len(response.data) > 0 # Returns True if a row was updated
    
# =================================================================
#                         API ROUTES
# =================================================================

# --- 0. HTML Serving Routes ---
@app.route('/')
@app.route('/index.html')
def index_page():
    """Serves the main dashboard page."""
    return render_template('index.html')

@app.route('/login.html')
def login_page():
    """Serves the login page. Endpoint used by url_for('login_page') in HTML."""
    return render_template('login.html')

@app.route('/register.html')
def register_page():
    """Serves the registration page. Endpoint used by url_for('register_page') in HTML."""
    return render_template('register.html')


# --- 9. GET /api/config ---
@app.route('/api/config', methods=['GET'])
def get_config():
    """
    Exposes non-sensitive environment variables to the frontend.
    """
    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_KEY')

    if not supabase_url or not supabase_key:
        logger.error("Configuration request failed: Supabase credentials missing on server.")
        return jsonify({
            "error": "Supabase configuration missing on server.",
            "details": "Check if SUPABASE_URL and SUPABASE_KEY are set in environment variables."
        }), 500

    return jsonify({
        "SUPABASE_URL": supabase_url,
        "SUPABASE_KEY": supabase_key
    }), 200


# --- 1. POST /api/register ---
@app.route('/api/register', methods=['POST'])
def register():
    if not supabase: return jsonify({"error": "Auth service is unavailable."}), 503
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    try:
        response = supabase.auth.sign_up(
            credentials={
                'email': email,
                'password': password
            }
        )
        if response.user:
            return jsonify({"message": "User registered successfully! Check email for confirmation.", "user_id": response.user.id}), 201
        
    except AuthApiError as e:
        logger.warning(f"Registration failed for {email}: {e.message}")
        status_code = 409 if 'already exists' in e.message.lower() else 400
        return jsonify({"error": f"Registration failed: {e.message}"}), status_code
    except Exception as e:
        logger.error(f"Error during registration: {e}")
        return jsonify({"error": "Internal server error during registration.", "details": str(e)}), 500


# --- 2. POST /api/login ---
@app.route('/api/login', methods=['POST'])
def login():
    if not supabase: return jsonify({"error": "Auth service is unavailable."}), 503
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
    
    try:
        response = supabase.auth.sign_in_with_password(
            credentials={
                'email': email,
                'password': password
            }
        )
        
        if response.user:
            user_id = response.user.id
            access_token = create_access_token(identity=user_id)
            return jsonify(access_token=access_token, user_id=user_id), 200
        else:
            return jsonify({"error": "Invalid email or password."}), 401
            
    except AuthApiError as e:
        logger.warning(f"Login failed for {email}: {e.message}")
        return jsonify({"error": "Invalid email or password."}), 401
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return jsonify({"error": "Internal server error during login.", "details": str(e)}), 500


# --- 3. POST /api/manual-telegram-link ---
@app.route('/api/manual-telegram-link', methods=['POST'])
@jwt_required()
def manual_telegram_link():
    """Manually links a Telegram User ID to the authenticated user's account."""
    if not supabase: return jsonify({"error": "Database service is unavailable."}), 503
    try:
        user_uuid = get_jwt_identity()
        data = request.get_json()
        telegram_id = data.get('telegram_user_id')

        if not telegram_id:
            return jsonify({"error": "Missing telegram_user_id"}), 400

        try:
            telegram_id = int(telegram_id)
        except ValueError:
            return jsonify({"error": "telegram_user_id must be a valid integer"}), 400

        # Update the users table (assuming 'users' is your profile table and 'user_uuid' is the primary key)
        response = supabase.table('users').update({ 
            'telegram_chat_id': telegram_id # Changed field name for clarity and consistency with alert engine
        }).eq('user_uuid', user_uuid).execute() 

        if len(response.data) > 0:
            return jsonify({
                "message": f"Telegram ID {telegram_id} successfully linked to user {user_uuid}.",
                "user_id": user_uuid
            }), 200
        else:
            return jsonify({"error": "User profile not found in database."}), 404

    except Exception as e:
        logger.error(f"Telegram Link Error: {e}")
        return jsonify({"error": "Internal server error during link process.", "details": str(e)}), 500


# --- 4. POST /api/create-alert ---
@app.route('/api/create-alert', methods=['POST'])
@jwt_required()
def create_alert():
    """Endpoint for the web dashboard to create a new alert using the parser."""
    if not supabase: return jsonify({"error": "Database service is unavailable."}), 503
    user_id = get_jwt_identity() 

    try:
        data = request.get_json()
        alert_phrase = data.get('alert_phrase')
        
        if not alert_phrase:
            return jsonify({"error": "Missing required field: alert_phrase"}), 400

        # 1. Parse the request using the updated function
        parsed_data = parse_alert_phrase(alert_phrase)
        parsed_data['user_id'] = user_id
        parsed_data['status'] = 'ACTIVE' # Set default status

        # 2. Save the structured alert to the database
        response = supabase.table('alerts').insert(parsed_data).execute()
        
        logger.info(f"Alert created for user {user_id}: {parsed_data.get('asset')} - {parsed_data.get('alert_type')}")
        return jsonify({
            "message": "Alert created successfully.",
            "alert_type": parsed_data.get('alert_type'),
            "details": parsed_data
        }), 201

    except ValueError as ve:
        logger.warning(f"Parsing failed for user {user_id}: {ve}")
        return jsonify({"error": "Could not understand your alert phrase.", "details": str(ve)}), 400
    except Exception as e:
        logger.error(f"Error in create_alert API for user {user_id}: {e}")
        return jsonify({"error": "Internal server error.", "details": str(e)}), 500

# --- 5. GET /api/my-alerts ---
@app.route('/api/my-alerts', methods=['GET'])
@jwt_required()
def get_my_alerts():
    """Endpoint to fetch all ACTIVE alerts for the logged-in user, and ENSURE their public profile exists."""
    if not supabase: return jsonify({"error": "Database service is unavailable."}), 503
    user_id = get_jwt_identity()
    
    try:
        # 1. CRITICAL: CHECK AND CREATE USER PROFILE IF MISSING (Handles Google Sign-in)
        profile_table_name = 'users' # Use the table name from your schema
        profile_id_column = 'user_uuid' # Use the column name from your schema
        
        profile_response = supabase.table(profile_table_name).select(profile_id_column).eq(profile_id_column, user_id).limit(1).execute()
        
        # If no profile found, create one immediately
        if not profile_response.data:
            logger.info(f"Creating missing public profile for new user: {user_id}")
            supabase.table(profile_table_name).insert({
                profile_id_column: user_id, 
                'created_at': datetime.now(timezone.utc).isoformat()
            }).execute()
        
        # 2. Proceed to fetch alerts
        alerts = fetch_user_alerts(user_id) 
        json_alerts = json.dumps(alerts, default=default_serializer) 
        
        logger.info(f"Fetched {len(alerts)} active alerts for user {user_id}.")
        
        return app.response_class(
            response=json_alerts,
            status=200,
            mimetype='application/json'
        )

    except Exception as e:
        logger.error(f"Error fetching alerts for user {user_id}: {e}")
        return jsonify({"error": "Internal server error while fetching alerts.", "details": str(e)}), 500

# --- 6. POST /api/delete-alert ---
@app.route('/api/delete-alert', methods=['POST'])
@jwt_required()
def delete_alert():
    """Endpoint to logically delete (deactivate) an alert by ID, verified against the user ID."""
    if not supabase: return jsonify({"error": "Database service is unavailable."}), 503
    user_id = get_jwt_identity()
    
    try:
        data = request.get_json()
        alert_id = data.get('alert_id')
        
        if not alert_id:
            return jsonify({"error": "Missing required field: alert_id"}), 400
            
        # Use the soft delete helper function defined above
        if deactivate_alert(alert_id, user_id=user_id, status='DELETED'):
            logger.info(f"Alert ID {alert_id} logically deleted by user {user_id}.")
            return jsonify({"message": f"Alert ID {alert_id} deleted successfully."}), 200
        else:
            # This returns if the alert_id doesn't exist or doesn't belong to the user
            return jsonify({"error": f"Failed to delete alert ID {alert_id}. Alert not found or does not belong to user."}), 404 

    except Exception as e:
        # 💡 CRITICAL FIX: Use repr(e) to guarantee a serializable string representation.
        error_details = repr(e) 
        logger.error(f"Error in delete_alert API for user {user_id}: {error_details}")
        
        # This will now reliably send the error details back without a serialization crash
        return jsonify({"error": "Internal server error.", "details": error_details}), 500

# --- 7. GET /api/supported-pairs (FIXED FILTERING) ---
@app.route('/api/supported-pairs', methods=['GET'])
def get_supported_pairs():
    """
    Fetches and returns the list of ONLY the trading pairs supported 
    by the parser (BTC, ETH, etc., paired with USDT).
    """
    
    async def fetch_markets_async():
        exchange = await get_exchange()
        try:
            markets = await exchange.fetch_markets() 
            await exchange.close() 
            
            # CRITICAL FILTERING LOGIC 
            symbols = sorted([
                m['symbol'].replace('/', '') # Simplify for frontend display (e.g., BTCUSDT)
                for m in markets 
                if m.get('spot') and 
                    m['symbol'].endswith('/USDT') and
                    m['symbol'].split('/')[0] in SUPPORTED_TOKENS
            ])
            return symbols
            
        except Exception as e:
            logger.error(f"CCXT fetch_markets error: {e}")
            return {"error": "Failed to fetch markets from exchange.", "details": str(e)}, 500

    try:
        # Run the async CCXT call using asyncio.run
        result = asyncio.run(fetch_markets_async())
        
        # Check if the result is an error dict
        if isinstance(result, tuple) and len(result) == 2 and 'error' in result[0]:
            return jsonify(result[0]), result[1] 

        return jsonify({
            "exchange": EXCHANGE_ID, 
            "supported_pairs": result, 
            "count": len(result)
        }), 200

    except Exception as e:
        logger.error(f"Error in get_supported_pairs route: {e}")
        return jsonify({"error": "Internal server error during market fetch."}), 500

# --- 8. GET /api/market-summary (FOR PRICE/CHANGE) ---
@app.route('/api/market-summary', methods=['GET'])
def get_market_summary():
    """
    Fetches the current price and 24h change for all supported pairs.
    """
    global SUPPORTED_TOKENS 
    
    async def fetch_tickers_async():
        exchange = await get_exchange()
        try:
            # Create a list of the full pair symbols (e.g., ['BTC/USDT', 'ETH/USDT', ...])
            symbols = [f'{token}/USDT' for token in SUPPORTED_TOKENS]
            
            # Fetch specific tickers only
            tickers = await exchange.fetch_tickers(symbols) 
            await exchange.close()
            
            # Format the output for the frontend
            summary = []
            for symbol in symbols:
                ticker = tickers.get(symbol)
                if ticker:
                    summary.append({
                        'symbol': ticker['symbol'].replace('/', ''), # Simplify to BTCUSDT
                        'price': ticker['last'],
                        'change_percent': ticker['percentage'],
                        'change_absolute': ticker['change']
                    })
            return summary
            
        except Exception as e:
            logger.error(f"CCXT fetch_tickers error: {e}")
            return {"error": "Failed to fetch market data.", "details": str(e)}, 500

    try:
        result = asyncio.run(fetch_tickers_async())
        
        if isinstance(result, tuple) and len(result) == 2 and 'error' in result[0]:
            return jsonify(result[0]), result[1] 

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error in get_market_summary route: {e}")
        return jsonify({"error": "Internal server error during market summary fetch."}), 500


# --- PRODUCTION EXECUTION ---
if __name__ == '__main__':
    # Only runs for local testing, Render will use Gunicorn
    app.run(debug=True)