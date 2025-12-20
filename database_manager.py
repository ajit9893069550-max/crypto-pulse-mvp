import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

# Configuration
DATABASE_URL = os.getenv('DATABASE_URL')
logger = logging.getLogger("DatabaseManager")

def get_db_connection():
    """
    Establishes connection with sanitization for common Supabase/Render string errors.
    """
    if not DATABASE_URL:
        logger.error("❌ DATABASE_URL is missing from environment variables!")
        return None
     
    # --- SANITIZATION LOGIC ---
    # 1. Fix the "ppostgresql" typo if it exists
    db_url = DATABASE_URL
    if db_url.startswith("ppostgresql"):
        db_url = db_url.replace("ppostgresql", "postgresql", 1)
        logger.info("Fixed connection string typo: changed 'ppostgresql' to 'postgresql'")

    try:
        # 2. Establish connection with SSL required for Supabase
        conn = psycopg2.connect(
            db_url, 
            sslmode='require',
            cursor_factory=RealDictCursor
        )
        return conn
    except Exception as e:
        logger.error(f"❌ Connection failed: {e}")
        # Suggesting a fix if the DSN error persists
        if "missing \"=\"" in str(e):
            logger.error("💡 Hint: Ensure DATABASE_URL is a valid URI starting with 'postgresql://'")
        return None

def upsert_signal(asset, timeframe, signal_type):
    """Inserts a new signal or updates the timestamp of an existing one."""
    conn = get_db_connection()
    if not conn: 
        logger.error("Skipping upsert: No database connection.")
        return
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO public.market_scans (asset, timeframe, signal_type, detected_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (asset, timeframe, signal_type) 
                DO UPDATE SET detected_at = NOW();
            """, (asset, timeframe, signal_type))
            conn.commit()
            logger.info(f"DB Upsert Success: {asset} | {timeframe} | {signal_type}")
    except Exception as e:
        logger.error(f"DB Upsert Error: {e}")
    finally:
        conn.close()

def fetch_triggered_alerts():
    """Finds ACTIVE alerts and matches them with recent scans."""
    conn = get_db_connection()
    if not conn: 
        return []
    
    try:
        with conn.cursor() as cur:
            # Ensure there is NO comma after 'public.alerts a'
            # Ensure we cast the TEXT user_uuid to UUID using ::uuid
            query = """
                SELECT 
                    a.id, 
                    a.asset, 
                    a.timeframe, 
                    a.alert_type, 
                    u.telegram_chat_id
                FROM public.alerts a
                JOIN public.users u ON a.user_id = u.user_uuid::uuid
                JOIN public.market_scans s ON 
                    a.asset = s.asset 
                    AND a.timeframe = s.timeframe 
                    AND a.alert_type = s.signal_type
                WHERE a.status = 'ACTIVE' 
                AND u.telegram_chat_id IS NOT NULL
                AND s.detected_at > NOW() - INTERVAL '20 minutes';
            """
            cur.execute(query)
            results = cur.fetchall()
            logger.info(f"Successfully fetched {len(results)} triggered alerts.")
            return results
    except Exception as e:
        logger.error(f"Error in fetch_triggered_alerts: {e}")
        return []
    finally:
        conn.close()