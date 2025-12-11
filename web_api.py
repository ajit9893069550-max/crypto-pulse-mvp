# web_api.py - COMPLETE CODE (UPDATED for Authentication and Linking)

from flask import Flask, request, jsonify
from flask_cors import CORS 
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager
import json
import logging
from datetime import datetime, timedelta

# Import the necessary functions from bot_listener.py and a new database connector
from bot_listener import (
    save_alert_to_db, 
    parse_alert_request,
    fetch_user_alerts,      
    deactivate_alert      
)

# NOTE: This is a placeholder import. You will need to create a new file 
# with functions like register_user, verify_user, link_telegram_id, etc.
# from database.auth_db_connector import (
#     register_user, verify_user, save_telegram_token, get_chat_id_by_token, delete_telegram_token
# )

# --- CONFIGURATION & INITIALIZATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- JWT Configuration ---
# NOTE: Replace 'super-secret-key' with a strong, random key in production!
app.config["JWT_SECRET_KEY"] = "super-secret-key-replace-me"
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)
jwt = JWTManager(app)

# Allow all origins for API endpoints
CORS(app, resources={r"/api/*": {"origins": "*"}})

# --- 0. Root Route / Health Check ---
@app.route('/')
def index():
    """Returns a simple status message to confirm the web service is alive."""
    return jsonify({
        "status": "OK", 
        "service": "Crypto Pulse API is Running",
        "timestamp": datetime.now().isoformat()
    }), 200

# --- Helper Function for JSON Serialization ---
def default_serializer(obj):
    """Custom JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

# =================================================================
#           PHASE 2: USER AUTHENTICATION & TELEGRAM LINKING
# =================================================================

# --- 1. POST /api/register ---
@app.route('/api/register', methods=['POST'])
def register():
    """Handles new user registration."""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    # NOTE: Placeholder logic. You must implement the register_user function
    # that hashes the password and saves it to the 'users' table.
    try:
        # user_id = register_user(email, password) # <-- Uncomment when implemented
        user_id = "test-user-id" # Placeholder
        if user_id:
            return jsonify({"message": "User registered successfully!", "user_id": user_id}), 201
        else:
            return jsonify({"error": "Registration failed. Email may already be in use."}), 409
    except Exception as e:
        logger.error(f"Error during registration: {e}")
        return jsonify({"error": "Internal server error during registration.", "details": str(e)}), 500


# --- 2. POST /api/login ---
@app.route('/api/login', methods=['POST'])
def login():
    """Handles user login and returns a JWT access token."""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
    
    # NOTE: Placeholder logic. You must implement verify_user 
    # (checking hashed password and returning user_id).
    try:
        # user = verify_user(email, password) # <-- Uncomment when implemented
        user_id = "f3a8d746-5295-4773-b663-3ff337a74372" # Placeholder for successful login
        if user_id:
            # Create the tokens and return them to the user
            access_token = create_access_token(identity=user_id)
            return jsonify(access_token=access_token, user_id=user_id), 200
        else:
            return jsonify({"error": "Invalid email or password."}), 401
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return jsonify({"error": "Internal server error during login.", "details": str(e)}), 500


# --- 3. POST /api/link-telegram-account ---
@app.route('/api/link-telegram-account', methods=['POST'])
@jwt_required() # Requires a valid JWT token
def link_telegram_account():
    """Links the logged-in user's web account to a Telegram chat_id via a token."""
    user_id = get_jwt_identity() # The user ID from the JWT token
    data = request.get_json()
    link_token = data.get('link_token')

    if not link_token:
        return jsonify({"error": "Missing required field: link_token"}), 400

    # NOTE: Placeholder logic. Implement the following in auth_db_connector:
    # 1. Fetch chat_id using link_token from the temporary table.
    # 2. Update the 'users' table, setting the telegram_chat_id for this user_id.
    # 3. Delete the temporary link_token.
    try:
        # chat_id = get_chat_id_by_token(link_token) # <-- Uncomment when implemented
        chat_id = "1234567890" # Placeholder for successful token lookup
        if chat_id:
            # link_telegram_id(user_id, chat_id) # <-- Uncomment when implemented
            # delete_telegram_token(link_token) # <-- Uncomment when implemented
            return jsonify({"message": "Telegram account linked successfully!"}), 200
        else:
            return jsonify({"error": "Invalid or expired link token."}), 404
    except Exception as e:
        logger.error(f"Error linking Telegram account for user {user_id}: {e}")
        return jsonify({"error": "Internal server error during linking.", "details": str(e)}), 500


# =================================================================
#           PHASE 1: PROTECTED ALERT MANAGEMENT ENDPOINTS
# =================================================================

# --- 4. POST /api/create-alert (NOW PROTECTED) ---
@app.route('/api/create-alert', methods=['POST'])
@jwt_required() # Requires a valid JWT token
def create_alert():
    """Endpoint for the web dashboard to create a new alert."""
    # Get the user ID from the JWT token identity
    user_id = get_jwt_identity() 

    try:
        data = request.get_json()
        alert_phrase = data.get('alert_phrase')
        
        if not alert_phrase:
            return jsonify({"error": "Missing required field: alert_phrase"}), 400

        # The user_id is now taken from the secure JWT token, not the request body
        
        # 1. Parse the request (handles new conditions like RSI/EMA/BBAND)
        parsed_params = parse_alert_request(alert_phrase)
        
        if 'error' in parsed_params:
            logger.warning(f"Parsing failed for user {user_id}: {parsed_params['error']}")
            return jsonify({
                "error": "Could not understand your alert phrase.",
                "details": parsed_params['error']
            }), 400

        # 2. Save the alert to the database
        if save_alert_to_db(user_id, parsed_params, is_telegram_alert=False):
            logger.info(f"Alert created for user {user_id}: {parsed_params.get('asset')}")
            return jsonify({
                "message": "Alert created successfully.",
                "alert_type": parsed_params.get('type')
            }), 201
        else:
            # This handles database connection errors that prevent saving
            return jsonify({"error": "Database error: Failed to save the alert."}), 500

    except Exception as e:
        logger.error(f"Error in create_alert API for user {user_id}: {e}")
        return jsonify({"error": "Internal server error.", "details": str(e)}), 500

# --- 5. GET /api/my-alerts (UPDATED FOR JWT) ---
@app.route('/api/my-alerts', methods=['GET'])
@jwt_required() # Requires a valid JWT token
def get_my_alerts():
    """
    Endpoint to fetch all ACTIVE alerts for the logged-in user.
    """
    # Get the user ID from the JWT token identity
    user_id = get_jwt_identity()
    
    try:
        alerts = fetch_user_alerts(user_id)
        # Use custom serializer for datetime objects
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

# --- 6. POST /api/delete-alert (NOW PROTECTED) ---
@app.route('/api/delete-alert', methods=['POST'])
@jwt_required() # Requires a valid JWT token
def delete_alert():
    """
    Endpoint to logically delete (deactivate) an alert by ID, verified against the user ID.
    """
    user_id = get_jwt_identity() # The user must own the alert
    
    try:
        data = request.get_json()
        alert_id = data.get('alert_id')
        
        if not alert_id:
            return jsonify({"error": "Missing required field: alert_id"}), 400
            
        # NOTE: You MUST update deactivate_alert() to ensure the alert belongs 
        # to the current user_id before deleting it for security.
        if deactivate_alert(alert_id, user_id=user_id, status='DELETED'):
            logger.info(f"Alert ID {alert_id} logically deleted by user {user_id}.")
            return jsonify({"message": f"Alert ID {alert_id} deleted successfully."}), 200
        else:
            # Return 404 if not found OR 403 if they don't own it
            return jsonify({"error": f"Failed to delete alert ID {alert_id}. Alert not found or does not belong to user."}), 404 

    except Exception as e:
        logger.error(f"Error in delete_alert API for user {user_id}: {e}")
        return jsonify({"error": "Internal server error.", "details": str(e)}), 500


# --- PRODUCTION EXECUTION ---
# The application is run by Gunicorn using the command: gunicorn web_api:app
# Remember to install Flask-JWT-Extended and bcrypt!