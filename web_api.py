import re
import os
import json
import logging
import asyncio # Required for running CCXT async calls
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS 
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager
from supabase import create_client, Client
from supabase_auth.errors import AuthApiError
import ccxt.async_support as ccxt # Import CCXT for fetching market data

# --- CONFIGURATION & INITIALIZATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Supabase Configuration ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise EnvironmentError(
        "FATAL: SUPABASE_URL and SUPABASE_KEY environment variables must be set."
    )

try:
    # Initialize the Supabase Client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    raise

app = Flask(__name__)

# --- JWT Configuration ---
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY")

if not app.config["JWT_SECRET_KEY"]:
    raise EnvironmentError(
        "FATAL: JWT_SECRET_KEY environment variable must be set."
    )

app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)
jwt = JWTManager(app)

# Allow all origins for API endpoints
CORS(app, resources={r"/api/*": {"origins": "*"}})

# --- CCXT Configuration ---
# Set the exchange you want to fetch pairs from
EXCHANGE_ID = 'binanceus' 

async def get_exchange():
    """Returns an exchange object with rate limiting enabled."""
    return ccxt.__getattribute__(EXCHANGE_ID)({'enableRateLimit': True})


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
    
    # List of supported assets for parsing (added USDT)
    SUPPORTED_ASSETS = r'(BTC|ETH|SOL|LTC|BNB|ADA|XRP|USDT)'
    
    # 1. Check for Complex MA Cross Alerts (50 MA / 200 MA)
    if 'CROSS' in phrase:
        if 'GOLDEN' in phrase:
            # Standardize type to MA_CROSS, condition is ABOVE
            sub_type = 'MA_CROSS' 
            condition = 'ABOVE'
        elif 'DEATH' in phrase:
            # Standardize type to MA_CROSS, condition is BELOW
            sub_type = 'MA_CROSS' 
            condition = 'BELOW'
        else:
            raise ValueError("Crossover alert must specify 'Golden Cross' or 'Death Cross'.")
            
        # Regex to find asset (e.g., BTC, ETH) and timeframe (e.g., 1D, 4H)
        # Uses the improved SUPPORTED_ASSETS regex
        match = re.search(f'{SUPPORTED_ASSETS}\\s*.*?(\\d+[HDWM])', phrase)
        
        if match:
            asset = match.group(1)
            timeframe = match.group(2)
            
            return {
                'alert_type': sub_type, 
                'asset': asset, 
                'timeframe': timeframe, 
                'operator': None, 
                'target_value': None,
                # NEW: Store specific MA cross details in params
                'params': { 
                    'condition': condition, 
                    'fast_ma': 50,  # Default periods for engine
                    'slow_ma': 200
                }
            }
        else:
            raise ValueError("Crossover alert requires an asset (e.g., BTC) and a timeframe (e.g., 1D).")
            
    # 2. Check for Simple Price Alerts
    # Uses the improved SUPPORTED_ASSETS regex
    match = re.search(f'{SUPPORTED_ASSETS}\\s*([<>])\\s*([\\d,.]+)', phrase)
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
            # NEW: Store specific Price details in params
            'params': {
                'target_price': target_value,
                'condition': 'ABOVE' if operator == '>' else 'BELOW'
            }
        }
    
    raise ValueError("Invalid alert format. Please use: 'BTC > 65000' or 'Golden Cross on ETH 4H'.")

# --- Database Helper Functions (Using Supabase) ---

def fetch_user_alerts(user_id):
    """Fetches ACTIVE alerts from the database for the given user_id."""
    # Ensure RLS policy allows this operation for the 'authenticated' role
    response = supabase.table('alerts').select('*').eq('user_id', user_id).eq('status', 'ACTIVE').execute()
    return response.data

def deactivate_alert(alert_id, user_id, status='DELETED'):
    """Deactivates alert after verifying ownership."""
    response = supabase.table('alerts').update({
        'status': status, 
        'updated_at': datetime.now().isoformat()
    }).eq('id', alert_id).eq('user_id', user_id).execute()

    return len(response.data) > 0 # Returns True if a row was updated
    
# =================================================================
#                         API ROUTES
# =================================================================

# --- 0. Root Route / Health Check ---
@app.route('/')
def index():
    return jsonify({
        "status": "OK", 
        "service": "Crypto Pulse API is Running",
        "timestamp": datetime.now().isoformat()
    }), 200

# --- 1. POST /api/register ---
@app.route('/api/register', methods=['POST'])
def register():
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
        # Supabase often returns 409 (Conflict) or 400 (Bad Request) for "user already exists" or "weak password"
        logger.warning(f"Registration failed for {email}: {e.message}")
        # Return 409 for conflict, otherwise 400 or 500
        status_code = 409 if 'already exists' in e.message.lower() else 400
        return jsonify({"error": f"Registration failed: {e.message}"}), status_code
    except Exception as e:
        logger.error(f"Error during registration: {e}")
        return jsonify({"error": "Internal server error during registration.", "details": str(e)}), 500


# --- 2. POST /api/login ---
@app.route('/api/login', methods=['POST'])
def login():
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
        # Catch common auth errors like invalid credentials
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

        # Update the profiles table
        response = supabase.table('profiles').update({ 
            'telegram_user_id': telegram_id 
        }).eq('id', user_uuid).execute() 

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
    """Endpoint to fetch all ACTIVE alerts for the logged-in user."""
    user_id = get_jwt_identity()
    
    try:
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
    user_id = get_jwt_identity()
    
    try:
        data = request.get_json()
        alert_id = data.get('alert_id')
        
        if not alert_id:
            return jsonify({"error": "Missing required field: alert_id"}), 400
            
        if deactivate_alert(alert_id, user_id=user_id, status='DELETED'):
            logger.info(f"Alert ID {alert_id} logically deleted by user {user_id}.")
            return jsonify({"message": f"Alert ID {alert_id} deleted successfully."}), 200
        else:
            return jsonify({"error": f"Failed to delete alert ID {alert_id}. Alert not found or does not belong to user."}), 404 

    except Exception as e:
        logger.error(f"Error in delete_alert API for user {user_id}: {e}")
        return jsonify({"error": "Internal server error.", "details": str(e)}), 500

# --- 7. GET /api/supported-pairs (NEW) ---
@app.route('/api/supported-pairs', methods=['GET'])
def get_supported_pairs():
    """Fetches and returns the list of all trading pairs (markets) from the exchange."""
    
    # We must run the CCXT call asynchronously
    async def fetch_markets_async():
        exchange = await get_exchange()
        try:
            # Fetch all markets
            markets = await exchange.fetch_markets() 
            await exchange.close() # Close the connection
            
            # Extract symbol, filtering for SPOT markets and USDT pairs
            symbols = sorted([
                m['symbol'] 
                for m in markets 
                if m.get('spot') and '/USDT' in m['symbol']
            ])
            return symbols
            
        except Exception as e:
            logger.error(f"CCXT fetch_markets error: {e}")
            # Return error message and status code for easy handling
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


# --- PRODUCTION EXECUTION ---
if __name__ == '__main__':
    # Only runs for local testing, Render will use Gunicorn
    app.run(debug=True)