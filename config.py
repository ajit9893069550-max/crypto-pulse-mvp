# config.py

import os
from dotenv import load_dotenv

# Load variables from a local .env file only for local development
# This line is ignored when deployed to cloud services
load_dotenv() 

# --- CORE CONFIGURATION (Pulled from Environment Variables) ---

# CRITICAL: These must be set as environment variables on your deployment host (e.g., Render, Heroku)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
EXCHANGE_ID = os.getenv("EXCHANGE_ID", "binance") # Default to binance if not specified

# --- ALERT PARAMETERS (Hardcoded, as they are non-sensitive configuration) ---

SUPPORTED_ASSETS = {
    "BTC": "BTC/USDT",
    "ETH": "ETH/USDT",
    "SOL": "SOL/USDT",
    "BNB": "BNB/USDT"
}

SUPPORTED_TIMEFRAMES = {
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "daily": "1d",
    "hourly": "1h"
}

# --- Validation (Stops the app if keys are missing) ---

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set. Check your .env file or deployment settings.")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set. Check your .env file or deployment settings.")