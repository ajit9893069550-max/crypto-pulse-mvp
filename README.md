# 🚀 CryptoPulse Intelligence Dashboard
A real-time cryptocurrency signal scanner and personal alert system. This project combines a technical analysis engine with a web dashboard and a Telegram bot handshake for instant notifications.



## 🛠 Features
* **Market Scanner:** Monitors 7+ major pairs (BTC, ETH, SOL, etc.) across 15m, 1h, and 4h timeframes.
* **Technical Indicators:** Detects Golden Cross, RSI Oversold, MACD Bullish Crossovers, and Bollinger Squeezes.
* **Web Dashboard:** Live signal feed with "NEW" tags for fresh signals and theme-aware UI.
* **Deep-Link Handshake:** Seamlessly link your web account to Telegram via a single click.
* **Personal Alerts:** Create custom alerts via dropdowns and get notified on Telegram when conditions are met.

## 📂 Project Structure
* `run_bot.py`: Combined orchestrator (Scanner + Telegram Handshake).
* `web_api.py`: Flask-based REST API for the web dashboard.
* `new_alert_engine.py`: The TA logic and technical analysis processor.
* `database_manager.py`: Centralized PostgreSQL/Supabase connection handler.
* `templates/`: HTML files (`index.html`, `login.html`).
* `static/`: Frontend assets (`scripts.js`, `styles.css`).

## ⚙️ Setup Instructions

### 1. Prerequisites
* Python 3.10+
* Supabase Account (PostgreSQL)
* Telegram Bot Token (via @BotFather)

### 2. Environment Variables
Create a `.env` file in the root directory:
```env
TELEGRAM_BOT_TOKEN=your_bot_token
DATABASE_URL=your_supabase_postgres_url
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_JWT_SECRET=your_jwt_secret_for_auth