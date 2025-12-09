# web_api.py

from flask import Flask, request, jsonify
from flask_cors import CORS 
import json
import logging
from datetime import datetime

# Import the necessary functions from bot_listener.py
from bot_listener import (
    save_alert_to_db, 
    parse_alert_request,
    fetch_user_alerts,   
    deactivate_alert     
)

# Set up basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# --- Helper Function for JSON Serialization ---
def default_serializer(obj):
    """Custom JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, list) and len(obj) == 1:
        return obj[0]
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

# --- 1. POST /api/create-alert ---
@app.route('/api/create-alert', methods=['POST'])
def create_alert():
    """Endpoint for the web dashboard to create a new alert."""
    try:
        data = request.get_json()
        
        if not data or 'alert_phrase' not in data or 'user_id' not in data:
            return jsonify({"error": "Missing required fields: alert_phrase and user_id"}), 400
        
        user_id = data['user_id']
        alert_phrase = data['alert_phrase']

        # 1. Parse the request
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
            return jsonify({"error": "Database error: Failed to save the alert."}), 500

    except Exception as e:
        logger.error(f"Error in create_alert API: {e}")
        return jsonify({"error": "Internal server error.", "details": str(e)}), 500

# --- 2. GET /api/my-alerts/<user_id> ---
@app.route('/api/my-alerts/<string:user_id>', methods=['GET'])
def get_my_alerts(user_id):
    """
    Endpoint to fetch all ACTIVE alerts for a specific user.
    """
    if not user_id:
        return jsonify({"error": "User ID is required."}), 400

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

# --- 3. POST /api/delete-alert ---
@app.route('/api/delete-alert', methods=['POST'])
def delete_alert():
    """
    Endpoint to logically delete (deactivate) an alert by ID.
    """
    try:
        data = request.get_json()
        alert_id = data.get('alert_id')
        
        if not alert_id:
            return jsonify({"error": "Missing required field: alert_id"}), 400
            
        if deactivate_alert(alert_id, status='DELETED'):
            logger.info(f"Alert ID {alert_id} logically deleted.")
            return jsonify({"message": f"Alert ID {alert_id} deleted successfully."}), 200
        else:
            return jsonify({"error": f"Failed to delete alert ID {alert_id}. ID may not exist or database error occurred."}), 404

    except Exception as e:
        logger.error(f"Error in delete_alert API: {e}")
        return jsonify({"error": "Internal server error.", "details": str(e)}), 500


# --- PRODUCTION EXECUTION ---
# The standard 'if __name__ == '__main__': app.run(...)' block is REMOVED.
# The application is now run by Gunicorn using the command: gunicorn web_api:app