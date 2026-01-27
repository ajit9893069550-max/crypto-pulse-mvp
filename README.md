# 🚀 CryptoPulse Intelligence Dashboard (MVP)

**A real-time cryptocurrency signal scanner, AI-powered analyst, and personal alert system.**

This project combines a robust Technical Analysis (TA) engine with a modern Web Dashboard, AI Chart Analysis (via Google Gemini), and a Telegram Bot handshake for instant notifications. It creates a seamless loop between detecting market opportunities and alerting the user.

---

## 🛠 Key Features

### 📊 **Intelligent Market Scanner**
* **Multi-Timeframe Monitoring:** Scans **15m, 1h, and 4h** charts for 10+ major pairs (BTC, ETH, SOL, XRP, etc.).
* **Advanced Signals:** Detects complex setups like **Golden Cross (Pullback Entry)**, **Death Cross**, **RSI Divergence**, and **Volume Surges**.
* **Algorithmic Strategies:**
    * **Bullish 200MA + RSI:** Buys dips in strong uptrends.
    * **Unlock Token Short:** Identifies shorting opportunities before major token unlocks.

### 🤖 **AI Chart Analyst (New!)**
* **One-Click Analysis:** Takes a live screenshot of the chart using **Headless Chrome**.
* **Google Gemini Integration:** Sends the chart image to Google's Gemini Flash 2.5 AI.
* **Instant Insights:** Returns a structured summary: **Trend, Support/Resistance levels, and a Buy/Sell/Wait verdict**.

### 🔔 **Smart Alerts System**
* **Bulk Creation:** Create alerts for multiple assets and timeframes in a single click.
* **Telegram Handshake:** Securely links your web dashboard to your Telegram account via a deep link.
* ** recurring Alerts:** Option to set one-time or recurring notifications.

---

## 📂 Project Structure

### **Backend (Python)**
* `web_api.py`: **Core API**. Handles the Flask server, AI requests, and Selenium (Headless Chrome) for screenshots.
* `run_bot.py`: **Orchestrator**. Runs the Telegram Bot and the background Scanner loop.
* `new_alert_engine.py`: **TA Logic**. Calculates indicators (RSI, MACD, BB) and triggers technical alerts.
* `strategy_engine.py`: **Strategy Logic**. Handles specialized strategies like the 200MA Pullback.
* `database_manager.py`: Centralized Supabase (PostgreSQL) connection handler.

### **Frontend (HTML/JS)**
* `templates/index.html`: The main dashboard UI (3-column layout).
* `static/ui.js`: Handles UI logic, Chart rendering (TradingView), and Modal interactions.
* `static/api.js`: Handles data fetching from the backend.
* `static/auth.js`: Manages user login/logout via Supabase Auth.
* `static/style.css`: Dark-themed responsive styling.

### **Configuration**
* `render.yaml`: **Deployment Config**. Tells Render.com how to install Chrome & Python.
* `requirements.txt`: List of dependencies (Flask, Selenium, Pandas, etc.).

---

## ⚙️ Setup Instructions

### 1. Prerequisites
* **Python 3.10+**
* **Google Chrome** (Required locally for screenshots; auto-installed on Render).
* **Supabase Account** (For Database & Auth).
* **Telegram Bot Token** (via @BotFather).
* **Google Gemini API Key** (For AI Analysis).

### 2. Environment Variables (.env)
Create a `.env` file in the root directory:

```env
# Database & Auth
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key (optional, for admin tasks)

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
BOT_USERNAME=YourBotName_bot

# AI Analysis
GEMINI_API_KEY=your_google_gemini_key