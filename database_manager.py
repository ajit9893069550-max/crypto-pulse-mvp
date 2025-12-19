import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# Configuration
DATABASE_URL = os.getenv('DATABASE_URL')
logger = logging.getLogger("DatabaseManager")

def get_db_connection():
    """Establishes connection with SSL enabled for Supabase/Render."""
    if not DATABASE_URL:
        logger.error("❌ DATABASE_URL is missing from environment variables!")
        return None
        
    try:
        # psycopg2 can parse the DSN URL directly
        conn = psycopg2.connect(
            DATABASE_URL, 
            sslmode='require',
            cursor_factory=RealDictCursor
        )
        return conn
    except Exception as e:
        logger.error(f"❌ Connection failed: {e}")
        return None

def upsert_signal(asset, timeframe, signal_type):
    """Inserts a new signal or updates the timestamp of an existing one."""
    conn = get_db_connection()
    if not conn: return
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO public.market_scans (asset, timeframe, signal_type, detected_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (asset, timeframe, signal_type) 
                DO UPDATE SET detected_at = NOW();
            """, (asset, timeframe, signal_type))
            conn.commit()
            logger.info(f"DB Upsert: {asset} | {timeframe} | {signal_type}")
    except Exception as e:
        logger.error(f"DB Upsert Error: {e}")
    finally:
        conn.close()

def fetch_triggered_alerts():
    """
    Finds ACTIVE alerts that match recent market scans.
    Filters for users who have linked their Telegram.
    """
    conn = get_db_connection()
    if not conn: return []
    
    try:
        with conn.cursor() as cur:
            # Matches alerts with scans from the last 20 mins to ensure no signals are missed
            cur.execute("""
                SELECT 
                    a.id, 
                    a.asset, 
                    a.timeframe, 
                    a.alert_type, 
                    u.telegram_chat_id
                FROM public.alerts a
                JOIN public.users u ON a.user_id = u.user_uuid
                JOIN public.market_scans s ON 
                    a.asset = s.asset 
                    AND a.timeframe = s.timeframe 
                    AND a.alert_type = s.signal_type
                WHERE a.status = 'ACTIVE' 
                AND u.telegram_chat_id IS NOT NULL
                AND s.detected_at > NOW() - INTERVAL '20 minutes';
            """)
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error fetching triggered alerts: {e}")
        return []
    finally:
        conn.close()