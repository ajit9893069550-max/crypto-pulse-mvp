import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Logging Setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("BotAuth")

# Config from .env
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if context.args:
        user_uuid_from_link = context.args[0]
        logger.info(f"Linking User {user_uuid_from_link} with Chat ID {chat_id}")

        try:
            # FIX: We must target the 'user_uuid' column because that's where 
            # your long string ID is stored in the database.
            response = supabase.table('users').update({
                'telegram_chat_id': str(chat_id)
            }).eq('user_uuid', user_uuid_from_link).execute()

            if response.data and len(response.data) > 0:
                await update.message.reply_text(
                    "✅ *Telegram Linked!*\n\n"
                    "Your dashboard will now show the connected status.",
                    parse_mode='Markdown'
                )
            else:
                # If this fails, the UUID in your link doesn't match the 'user_uuid' column
                await update.message.reply_text("❌ Link failed. Account not found.")
                logger.warning(f"No match found for user_uuid: {user_uuid_from_link}")

        except Exception as e:
            logger.error(f"Error: {e}")
            await update.message.reply_text("⚠️ A database error occurred. Please try again later.")
    
    else:
        # Standard start without a UUID
        await update.message.reply_text(
            "Welcome to CryptoPulse Bot! 🚀\n\n"
            "To receive alerts here, please go to your Web Dashboard and click "
            "'Connect Telegram Bot' in the My Alerts section."
        )

if __name__ == '__main__':
    if not TOKEN or not SUPABASE_URL:
        print("Missing config in .env file (TOKEN or SUPABASE_URL)")
        exit()

    application = ApplicationBuilder().token(TOKEN).build()
    
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)
    
    print("Bot Handshake listener is running...")
    application.run_polling()