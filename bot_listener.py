# bot_listener.py
import logging
import re
import psycopg2
from urllib.parse import urlparse
import json

# Import the necessary psycopg2 extension for JSONB handling
from psycopg2.extras import Json

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Import your custom parser and configuration
# NOTE: Ensure config.py contains TELEGRAM_BOT_TOKEN and DATABASE_URL
from config import TELEGRAM_BOT_TOKEN, DATABASE_URL
from parser import parse_alert_request 

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- 1. Centralized DB Connection Function ---

def get_db_connection():
    """Returns an active PostgreSQL connection object using DATABASE_URL."""
    try:
        url = urlparse(DATABASE_URL)
        conn = psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port
        )
        return conn
    except psycopg2.Error as e:
        logger.error(f"Database connection error: {e}")
        return None

# --- 2. Database Management Functions (CRUD) ---

def save_alert_to_db(user_id, parsed_params, is_telegram_alert=False):
    """
    Inserts a new alert into the PostgreSQL public.alerts table.
    """
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        cursor = conn.cursor()
        
        # Ensure we pass a copy, as we pop items here
        params_copy = parsed_params.copy()
        asset = params_copy.pop('asset')
        timeframe = params_copy.pop('timeframe')
        alert_type = params_copy.pop('type')
        condition_text = params_copy.get('condition', 'N/A') # Extract human-readable text

        # The rest of the parameters go into the JSONB column
        params_json = Json(params_copy)
        
        # FIX: Using public.alerts schema
        sql = """
            INSERT INTO public.alerts (user_id, asset, timeframe, alert_type, params, status, condition_text)
            VALUES (%s, %s, %s, %s, %s, 'ACTIVE', %s)
        """
        cursor.execute(sql, (str(user_id), asset, timeframe, alert_type, params_json, condition_text))
        conn.commit()
        cursor.close()
        conn.close()
        return True

    except psycopg2.Error as e:
        logger.error(f"Database insertion error for user {user_id}: {e}")
        if conn: conn.rollback()
        return False
    except Exception as e:
        logger.error(f"Error preparing alert data for insertion: {e}")
        return False


def link_telegram_user(user_uuid, chat_id):
    """
    Links a unique web user_uuid to their Telegram chat_id in the 'public.users' table.
    """
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        cursor = conn.cursor()
        # FIX: Using public.users schema
        cursor.execute("""
            UPDATE public.users 
            SET telegram_chat_id = %s
            WHERE user_uuid = %s;
        """, (str(chat_id), user_uuid))
        conn.commit()
        rows_updated = cursor.rowcount
        cursor.close()
        conn.close()
        return rows_updated > 0
    except Exception as e:
        logger.error(f"Error linking user {user_uuid} to chat {chat_id}: {e}")
        if conn: conn.rollback()
        return False

def deactivate_alert(alert_id, status='TRIGGERED'):
    """
    Sets an alert's status to TRIGGERED, EXPIRED, or DELETED in the public.alerts table.
    This function will be used by the Alert Engine and the Web API for deletion.
    """
    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        # FIX: Using public.alerts schema
        cursor.execute("""
            UPDATE public.alerts 
            SET status = %s
            WHERE id = %s;
        """, (status, alert_id))
        conn.commit()
        rows_updated = cursor.rowcount
        cursor.close()
        conn.close()
        return rows_updated > 0
    except Exception as e:
        logger.error(f"Error deactivating alert ID {alert_id}: {e}")
        if conn: conn.rollback()
        return False
    
def fetch_user_alerts(user_id):
    """
    NEW: Retrieves all active alerts for a given user_id, 
    used by the Web API's /api/my-alerts endpoint.
    """
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        # Retrieve all necessary columns from the public.alerts table 
        cursor.execute("""
            SELECT id, user_id, asset, timeframe, alert_type, params, status, created_at, condition_text
            FROM public.alerts
            -- Assume 'user_id' in alerts table corresponds to the UUID from the web dashboard
            WHERE user_id = %s AND status = 'ACTIVE'
            ORDER BY created_at DESC;
        """, (str(user_id),))
        
        # Get column names to create a list of dictionaries (easy for JSON conversion)
        columns = [desc[0] for desc in cursor.description]
        alerts = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        return alerts
        
    except Exception as e:
        logger.error(f"Error fetching alerts for user {user_id}: {e}")
        if conn: conn.close()
        return []


# --- 3. Telegram Command Handlers (Async) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and instructions."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}! 👋\n\n"
        "I'm Crypto Pulse. **First, you must link me to your web account!**\n\n"
        "1. Go to your web dashboard.\n"
        "2. Find your unique User ID.\n"
        "3. Send the command: `/link YOUR_UNIQUE_USER_ID`\n\n"
        "**To set an alert (once linked):** Just send the phrase, e.g., `Alert if BTC drops below 60K`"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message."""
    await update.message.reply_text("Send me a phrase like 'Alert if BTC drops below 60K' or use /link <ID> to connect your account.")

async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /link <ID> command to link a Telegram chat ID to a web user UUID."""
    user_id = str(update.effective_chat.id)
    args = context.args

    if not args:
        await update.message.reply_text("Usage Error: Please send the command in the format: `/link YOUR_UNIQUE_USER_ID`")
        return
        
    user_uuid = args[0].strip()
    
    # Basic UUID-like structure check
    if not re.match(r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$', user_uuid, re.IGNORECASE):
         await update.message.reply_text("Invalid ID format. Please ensure you are copying the full unique ID from your dashboard.")
         return

    if link_telegram_user(user_uuid, user_id):
        await update.message.reply_text(
            f"✅ **Account Linked!**\n\n"
            f"Your web account is now linked to this Telegram chat. You can now create alerts via the dashboard or directly in this chat."
        )
        logger.info(f"User {user_id} successfully linked to UUID: {user_uuid}")
    else:
        await update.message.reply_text(
            "❌ **Linking Failed.**\n\n"
            "The Unique User ID was not found or a database error occurred. Please double-check the ID or try again later."
        )


# --- 4. Main Message Handler ---

async def alert_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Parses the user's text input (excluding commands), saves the alert, and confirms.
    """
    user_id = str(update.effective_chat.id)
    user_text = update.message.text
    
    # 1. Parse the user's input
    parsed_params = parse_alert_request(user_text)

    # 2. Check for parsing errors
    if 'error' in parsed_params:
        await update.message.reply_text(
            f"❌ **Parsing Error**:\n{parsed_params['error']}\n\n"
            "Please try rephrasing your alert. Examples: `Alert if BTC drops below 60K` or `Notify when ETH 50 MA crosses 200 MA on the 4h chart`"
        )
        return
    
    # 3. Save the alert to the database (Using chat_id as user_id for simplicity here)
    if save_alert_to_db(user_id, parsed_params, is_telegram_alert=True):
        
        confirmation_message = (
            f"✅ **Alert Created!**\n\n"
            f"**Asset:** {parsed_params.get('asset')}\n"
            f"**Type:** {parsed_params.get('type').replace('_', ' ')}\n"
            f"**Timeframe:** {parsed_params.get('timeframe')}\n"
            f"I will notify you here when the condition is met."
        )
        await update.message.reply_text(confirmation_message, parse_mode='Markdown')
        
    else:
        await update.message.reply_text("⚠️ **Database Error:** Sorry, I couldn't save your alert right now. Please check the API logs.")


# --- 5. Main Bot Runner ---

def main() -> None:
    """Start the bot."""
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is missing in config.py. Bot cannot start.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("link", link_command)) 

    # Register the message handler (This catches all non-command text messages)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, alert_handler))

    logger.info("Bot is running...")
    
    application.run_polling(poll_interval=1.0)

if __name__ == '__main__':
    main()