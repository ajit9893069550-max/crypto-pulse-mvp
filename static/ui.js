/**
 * UI.JS - Handles Dashboard, Charts, and Audio
 * (Final Version: Includes Inline Descriptions, Smart Charts & Price Alerts)
 */

// --- 1. SIGNAL DEFINITIONS (Header Description Text) ---
const SIGNAL_DEFINITIONS = {
    'ALL': "Monitoring high-probability setups.",
    
    // Sniper Setups
    'SNIPER_BUY_REVERSAL': "Price < Support AND RSI < 30 AND Vol > 200%. (Reversal)",
    'SNIPER_SELL_REJECTION': "Price > Resistance AND RSI > 70 AND Vol > 200%. (Rejection)",
    'MOMENTUM_BREAKOUT': "Price breaks range AND Vol > 200% AND MACD Cross.",
    
    // Major Trend
    'GOLDEN_CROSS': "50 SMA crosses above 200 SMA (Bull Market Start).",
    'DEATH_CROSS': "50 SMA crosses below 200 SMA (Bear Market Start).",
    'VOLUME_SURGE': "Unusual whale activity detected (>3x Avg Vol).",
    
    // Oscillators
    'RSI_OVERSOLD': "RSI is below 30. Asset is undervalued.",
    'RSI_OVERBOUGHT': "RSI is above 70. Asset is overvalued.",
    'MACD_BULL_CROSS': "Momentum shifting to bullish."
};

// --- CONFIG: Chart Indicators Map ---
const STUDY_MAP = {
    'RSI_OVERSOLD':        ['RSI@tv-basicstudies'],
    'RSI_OVERBOUGHT':      ['RSI@tv-basicstudies'],
    'MACD_BULL_CROSS':     ['MACD@tv-basicstudies'],
    'MACD_BEAR_CROSS':     ['MACD@tv-basicstudies'],
    'BB_SQUEEZE':          ['BB@tv-basicstudies'],
    'GOLDEN_CROSS':        ['MASimple@tv-basicstudies', 'MASimple@tv-basicstudies'], 
    'DEATH_CROSS':         ['MASimple@tv-basicstudies', 'MASimple@tv-basicstudies'],
    'SNIPER_BUY_REVERSAL': ['RSI@tv-basicstudies', 'BB@tv-basicstudies'],
    'SNIPER_SELL_REJECTION':['RSI@tv-basicstudies', 'BB@tv-basicstudies'],
    'MOMENTUM_BREAKOUT':   ['MACD@tv-basicstudies']
};

const TF_MAP = { '15m': '15', '1h': '60', '4h': '240', '1d': 'D' };

// --- HELPERS ---
function timeAgo(dateString) {
    const date = new Date(dateString);
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 60) return Math.floor(seconds) + "s ago";
    if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
    if (seconds < 86400) return Math.floor(seconds / 3600) + "h ago";
    return Math.floor(seconds / 86400) + "d ago";
}

function cleanSignalName(name, price = null) {
    // If it's a price alert, format it nicely
    if (name === 'PRICE_TARGET' && price) {
        return `💰 Target: $${price}`;
    }

    const map = {
        'PRICE_TARGET': '💰 Price Alert',
        'SNIPER_BUY_REVERSAL': '🎯 Sniper Buy',
        'SNIPER_SELL_REJECTION': '🛑 Sniper Sell',
        'MOMENTUM_BREAKOUT': '🚀 Breakout',
        'GOLDEN_CROSS': '🟡 Golden Cross',
        'DEATH_CROSS': '💀 Death Cross',
        'RSI_OVERSOLD': '📉 RSI Oversold',
        'RSI_OVERBOUGHT': '📈 RSI Overbought',
        'BB_SQUEEZE': '🤐 Volatility Squeeze',
        'VOLUME_SURGE': '📊 Volume Surge',
        'MACD_BULL_CROSS': '🟢 MACD Bull Cross'
    };
    return map[name] || name.replace(/_/g, ' ');
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        console.log("Copied to clipboard");
    });
}

// --- TOGGLE FUNCTION (For Price Alert Input) ---
function togglePriceInput() {
    const type = document.getElementById('alertType').value;
    const inputGroup = document.getElementById('priceInputGroup');
    const priceInput = document.getElementById('alertPrice');
    
    if (type === 'PRICE_TARGET') {
        inputGroup.style.display = 'block';
        priceInput.required = true;
        priceInput.focus();
    } else {
        inputGroup.style.display = 'none';
        priceInput.required = false;
        priceInput.value = '';
    }
}

// --- CORE RENDER FUNCTIONS ---
async function refreshSignals(type) {
    const list = document.getElementById('marketScansList');
    if (!list) return;

    list.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 20px;"><div class="loader"></div> Scanning Market...</td></tr>';

    const data = await API.getSignals(type);

    if (!data.length) {
        list.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 20px;">No active signals found for this category.</td></tr>';
        return;
    }

    const latestTime = new Date(data[0].detected_at);
    if ((new Date() - latestTime) < 60000) {
        const audio = document.getElementById('alertSound');
        if (audio) audio.play().catch(e => console.log("Audio autoplay blocked by browser"));
    }

    list.innerHTML = data.map(s => {
        const relativeTime = timeAgo(s.detected_at);
        const cleanName = cleanSignalName(s.signal_type);
        const isBull = s.signal_type.includes('BUY') || s.signal_type.includes('BULL') || s.signal_type.includes('BREAKOUT') || s.signal_type.includes('GOLDEN');
        const assetName = s.asset.replace('/USDT', '');

        return `
            <tr class="signal-row" onclick="openChart('${assetName}', '${s.timeframe}', '${s.signal_type}')">
                <td style="font-weight:bold; width: 25%;">
                    ${assetName} 
                    <button class="btn-copy" onclick="event.stopPropagation(); copyToClipboard('${cleanName} on ${assetName}')" title="Copy Signal">📋</button>
                </td>
                <td style="width: 10%;"><span class="tf-badge">${s.timeframe}</span></td>
                <td class="${isBull ? 'text-success' : 'text-danger'}" style="width: 35%;">${cleanName}</td>
                <td style="color:var(--text-dim); font-size:12px; width: 15%;">${relativeTime}</td>
                <td style="width: 15%; text-align: center;">
                    <button class="btn-view-chart">📊 View</button>
                </td>
            </tr>`;
    }).join('');
}

async function refreshAlerts() {
    const alerts = await API.getMyAlerts();
    const container = document.getElementById('myAlertsList');
    if (!container) return;

    if (!alerts.length || alerts.error) {
        container.innerHTML = '<p style="text-align:center; color:var(--text-dim); font-size:13px;">No active alerts.</p>';
        return;
    }

    container.innerHTML = alerts.map(a => {
        const displayName = cleanSignalName(a.alert_type, a.target_price);
        return `
        <div class="card alert-item" style="margin-bottom: 10px; padding: 12px; display: flex; justify-content: space-between; align-items: center;">
            <div>
                <strong>${a.asset}</strong> <span class="tf-badge tf-${a.timeframe}">${a.timeframe}</span><br>
                <small style="color: var(--text-dim);">${displayName}</small>
            </div>
            <button onclick="handleDeleteAlert(${a.id})" class="text-danger" style="background:none; border:none; cursor:pointer; font-size: 16px;">&times;</button>
        </div>`;
    }).join('');
}

async function updateTelegramUI() {
    const isLinked = await API.getTelegramStatus();
    const btn = document.getElementById('connectTelegramBtn');
    const statusDiv = document.getElementById('telegramLinkSection');

    if (isLinked && statusDiv) {
        statusDiv.innerHTML = `<div style="background: rgba(0, 255, 136, 0.1); padding: 12px; border-radius: 8px; border: 1px solid var(--accent-green); color: var(--accent-green); font-weight: bold; text-align: center;">✅ Telegram Connected</div>`;
        if (btn) btn.style.display = 'none';
    } else if (btn) {
        const botName = window.BOT_USERNAME || 'CryptoPulse_Bot';
        btn.href = `https://t.me/${botName}?start=${getUserId()}`;
        btn.style.display = 'block';
    }
}

// --- CHART MODAL ---
function openChart(symbol, timeframe = '1h', signalType = 'NONE') {
    const modal = document.getElementById('chartModal');
    const title = document.getElementById('modalTitle');
    
    if(modal && title) {
        modal.style.display = 'flex';
        const cleanName = signalType !== 'NONE' ? cleanSignalName(signalType) : 'Analysis';
        title.innerText = `${symbol}/USDT - ${timeframe} - ${cleanName}`;
        
        const tvInterval = TF_MAP[timeframe] || '60';
        const indicators = STUDY_MAP[signalType] || [];

        if (window.TradingView) {
            new TradingView.widget({
                "width": "100%", "height": 500,
                "symbol": "BINANCE:" + symbol + "USDT",
                "interval": tvInterval,
                "timezone": "Etc/UTC",
                "theme": localStorage.getItem('theme') === 'light' ? 'light' : 'dark',
                "style": "1", "locale": "en",
                "toolbar_bg": "#f1f3f6", "enable_publishing": false,
                "hide_side_toolbar": false, "allow_symbol_change": true,
                "studies": indicators,
                "container_id": "tv_chart_container"
            });
        }
    }
}
function closeModal() {
    document.getElementById('chartModal').style.display = 'none';
    document.getElementById('tv_chart_container').innerHTML = '';
}

// --- EVENTS ---
async function handleDeleteAlert(id) {
    if (confirm("Stop receiving this alert?")) {
        await API.deleteAlert(id);
        refreshAlerts();
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    await initAuth();
    refreshSignals('ALL');
    refreshAlerts();
    updateTelegramUI();

    // UPDATED: Alert Creation Logic
    const form = document.getElementById('createAlertForm');
    if (form) {
        form.onsubmit = async (e) => {
            e.preventDefault();
            const status = document.getElementById('createAlertStatus');
            status.innerText = "⏳ Activating...";

            const payload = {
                asset: document.getElementById('alertAsset').value,
                timeframe: document.getElementById('alertTimeframe').value,
                signal_type: document.getElementById('alertType').value,
                target_price: document.getElementById('alertPrice').value || null 
            };

            const res = await API.createAlert(payload);
            if (res.success) {
                status.innerHTML = `<span class="text-success">✅ Alert Active!</span>`;
                refreshAlerts();
                form.reset();
                togglePriceInput(); // Reset visibility
                setTimeout(() => status.innerText = "", 3000);
            } else {
                status.innerHTML = `<span class="text-danger">❌ Error</span>`;
            }
        };
    }

    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.querySelector('.sidebar');
    if (menuToggle && sidebar) {
        menuToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            sidebar.classList.toggle('active');
        });
        document.addEventListener('click', (e) => {
            if (sidebar.classList.contains('active') && !sidebar.contains(e.target) && e.target !== menuToggle) {
                sidebar.classList.remove('active');
            }
        });
    }

    // Sidebar Logic (Updates Description Inline)
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', function () {
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            this.classList.add('active');
            
            const categoryType = this.getAttribute('data-type');
            
            const title = document.getElementById('currentCategoryTitle');
            if (title) title.innerText = this.innerText;

            const desc = document.getElementById('categoryDescription');
            if (desc) {
                const text = SIGNAL_DEFINITIONS[categoryType] || "";
                desc.innerText = text ? `- ${text}` : "";
            }

            refreshSignals(categoryType);
            
            if (window.innerWidth <= 1024 && sidebar.classList.contains('active')) {
                sidebar.classList.remove('active');
            }
        });
    });

    window.onclick = function(event) {
        if (event.target == document.getElementById('chartModal')) closeModal();
    }
});