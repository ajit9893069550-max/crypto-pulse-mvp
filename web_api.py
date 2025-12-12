import re
import os
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS 
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager
from supabase import create_client, Client
from supabase_auth.errors import AuthApiError

# --- CONFIGURATION & INITIALIZATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Supabase Configuration ---
# BEST PRACTICE: Use environment variables in production (e.g., on Render)
SUPABASE_URL = os.environ.get("SUPABASE_URL", 'https://eblmnwfnhjlvkkevgqeh.supabase.co')
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVibG1ud2ZuaGpsdmtrZXZncWVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUyMTAzOTgsImV4cCI6MjA4MDc4NjM5OH0.7i_Vk6bnMgNez1lQpFMGCjrQ6OsFATl2BWSOZ5Yb1zI')

if SUPABASE_URL == 'https://eblmnwfnhjlvkkevgqeh.supabase.co':
    logger.warning("Supabase URL is a placeholder. UPDATE YOUR CREDENTIALS!")

try:
    # Initialize the Supabase Client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    # The app will likely fail to start if the client cannot be created

app = Flask(__name__)

# --- JWT Configuration ---
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "super-secret-key-change-me") # CHANGE ME!
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)
jwt = JWTManager(app)

# Allow all origins for API endpoints
CORS(app, resources={r"/api/*": {"origins": "*"}})

# --- Helper Functions ---
def default_serializer(obj):
    """Custom JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

def parse_alert_phrase(phrase):
    """
    Parses a plain English phrase into structured alert data, 
    handling PRICE_TARGET, GOLDEN_CROSS, and DEATH_CROSS (Goal 1).
    """
    phrase = phrase.upper().strip()
    
    # 1. Check for Complex MA Cross Alerts (50 MA / 200 MA)
    if 'CROSS' in phrase:
        if 'GOLDEN' in phrase:
            sub_type = 'GOLDEN_CROSS'
        elif 'DEATH' in phrase:
            sub_type = 'DEATH_CROSS'
        else:
            raise ValueError("Crossover alert must specify 'Golden Cross' or 'Death Cross'.")
            
        # Regex to find asset (e.g., BTC, ETH) and timeframe (e.g., 1D, 4H)
        match = re.search(r'(BTC|ETH|SOL|LTC|BNB|ADA|XRP)\s*.*?(\d+[HDWM])', phrase)
        
        if match:
            asset = match.group(1)
            timeframe = match.group(2)
            
            return {
                'alert_type': sub_type, 
                'asset': asset, 
                'timeframe': timeframe, 
                'operator': None, 
                'target_value': None
            }
        else:
            raise ValueError("Crossover alert requires an asset (e.g., BTC) and a timeframe (e.g., 1D).")
            
    # 2. Check for Simple Price Alerts
    match = re.search(r'(BTC|ETH|SOL|LTC|BNB|ADA|XRP)\s*([<>])\s*([\d,.]+)', phrase)
    if match:
        asset = match.group(1)
        operator = match.group(2)
        target_value = float(match.group(3).replace(',', ''))
        
        return {
            'alert_type': 'PRICE_TARGET', 
            'asset': asset, 
            'operator': operator, 
            'target_value': target_value, 
            'timeframe': None
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
#                 API ROUTES
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
        # Supabase Auth: Creates the user in auth.users table
        response = supabase.auth.sign_up(
            credentials={
              'email': email,
              'password' : password
            },  
            options={'data': {'telegram_user_id': None}} # Initialize custom metadata
        )
        # If successful, response.user contains the UUID
        if response.user:
             # NOTE: You should have an RLS policy and trigger to auto-create the 'profiles' row here.
            return jsonify({"message": "User registered successfully! Check email for confirmation.", "user_id": response.user.id}), 201
        
    except AuthApiError as e:
         return jsonify({"error": f"Registration failed: {e.message}"}), 409
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
        # Supabase Auth: Verifies credentials
        response = supabase.auth.sign_in_with_password(email=email, password=password)
        
        if response.user:
            # Create the tokens using Flask-JWT-Extended
            user_id = response.user.id
            access_token = create_access_token(identity=user_id)
            return jsonify(access_token=access_token, user_id=user_id), 200
        else:
            return jsonify({"error": "Invalid email or password."}), 401
            
    except AuthApiError as e:
        # Supabase returns AuthApiError for invalid credentials
        return jsonify({"error": "Invalid email or password."}), 401
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return jsonify({"error": "Internal server error during login.", "details": str(e)}), 500


# --- 3. POST /api/manual-telegram-link (GOAL 2) ---
@app.route('/api/manual-telegram-link', methods=['POST'])
@jwt_required()
def manual_telegram_link():
    """Manually links a Telegram User ID to the authenticated user's account."""
    try:
        user_uuid = get_jwt_identity() # Get user UUID from JWT
        data = request.get_json()
        telegram_id = data.get('telegram_user_id')

        if not telegram_id:
            return jsonify({"error": "Missing telegram_user_id"}), 400

        try:
            telegram_id = int(telegram_id)
        except ValueError:
            return jsonify({"error": "telegram_user_id must be a valid integer"}), 400

        # Supabase Update: Update the profiles table
        response = supabase.table('profiles').update({ 
            'telegram_user_id': telegram_id 
        }).eq('id', user_uuid).execute() 

        if len(response.data) > 0:
            return jsonify({
                "message": f"Telegram ID {telegram_id} successfully linked to user {user_uuid}.",
                "user_id": user_uuid
            }), 200
        else:
            # This happens if the user profile record is not found
            return jsonify({"error": "User profile not found in database."}), 404

    except Exception as e:
        logger.error(f"Telegram Link Error: {e}")
        return jsonify({"error": "Internal server error during link process.", "details": str(e)}), 500


# --- 4. POST /api/create-alert (GOAL 1: Crossover Logic) ---
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

        # 1. Parse the request using the new function (handles crosses)
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


# --- PRODUCTION EXECUTION ---
if __name__ == '__main__':
    # Only runs for local testing, Render will use Gunicorn
    app.run(debug=True)