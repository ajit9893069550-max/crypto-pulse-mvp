import asyncio
import logging
import os
from telegram.ext import ApplicationBuilder, CommandHandler
from telegram import Update
from telegram.ext import ContextTypes

# Import the logic from your existing modules
from main import run_cycle, get_seconds_until_next_interval
from new_alert_engine import close_exchange
from database_manager import get_db_connection

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("CombinedBot")

# ==========================================================
# 1. TELEGRAM HANDSHAKE LOGIC (From telegram_bot_auth)
# ==========================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if context.args:
        user_uuid = context.args[0]
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE public.users 
                        SET telegram_chat_id = %s 
                        WHERE user_uuid = %s RETURNING user_uuid;
                    """, (chat_id, user_uuid))
                    if cur.fetchone():
                        conn.commit()
                        await update.message.reply_text("✅ *Linked!* Your alerts will now arrive here.", parse_mode='Markdown')
                    else:
                        await update.message.reply_text("❌ Account not found. Please log in to the web dashboard.")
            finally:
                conn.close()
    else:
        await update.message.reply_text("Welcome! Link your account via the Web Dashboard to receive signals.")

# ==========================================================
# 2. SCANNER LOOP LOGIC (From main.py)
# ==========================================================
async def scanner_loop():
    logger.info("Scanner Loop Started: Syncing with IST 15m intervals...")
    try:
        while True:
            wait_time = get_seconds_until_next_interval(15)
            if wait_time > 2:
                logger.info(f"Scanner sleeping for {int(wait_time)}s...")
                await asyncio.sleep(wait_time)
            
            # Run the scanning cycle
            await run_cycle()
            
            # Buffer to prevent double-firing
            await asyncio.sleep(10)
    except Exception as e:
        logger.error(f"Scanner Loop Error: {e}")

# ==========================================================
# 3. MAIN RUNNER (Combines Both)
# ==========================================================
async def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.critical("TELEGRAM_BOT_TOKEN missing!")
        return

    # Initialize Telegram Application
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start_command))

    # Initialize the application components
    await application.initialize()
    await application.start()
    
    # Start polling for updates
    # We use 'updater' specifically for background polling in a manual loop
    await application.updater.start_polling()
    logger.info("Telegram Bot Handshake Listener Active.")

    try:
        # Run the Scanner Loop
        # We don't need to gather the bot polling separately because 
        # start_polling() runs in its own task background
        await scanner_loop()
    except Exception as e:
        logger.error(f"Global Loop Error: {e}")
    finally:
        # Graceful shutdown
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    # Standard entry point
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Unexpected crash: {e}")
    finally:
        # Final cleanup for CCXT
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(close_exchange())
            else:
                loop.run_until_complete(close_exchange())
        except Exception:
            # Fallback for closed loops
            asyncio.run(close_exchange())
        logger.info("Exchange connections closed. Goodbye!")