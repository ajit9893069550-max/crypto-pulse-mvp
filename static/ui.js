/**
 * UI.JS - Handles Dashboard, Charts, and Audio
 * (Cleaned Version: Descriptions removed for better layout stability)
 */

// --- HELPERS ---
function timeAgo(dateString) {
    const date = new Date(dateString);
    const seconds = Math.floor((new Date() - date) / 1000);
    let interval = seconds / 31536000;
    if (interval > 1) return Math.floor(interval) + "y ago";
    interval = seconds / 2592000;
    if (interval > 1) return Math.floor(interval) + "mo ago";
    interval = seconds / 86400;
    if (interval > 1) return Math.floor(interval) + "d ago";
    interval = seconds / 3600;
    if (interval > 1) return Math.floor(interval) + "h ago";
    interval = seconds / 60;
    if (interval > 1) return Math.floor(interval) + "m ago";
    return Math.floor(seconds) + "s ago";
}

function cleanSignalName(name) {
    const map = {
        'SNIPER_BUY_REVERSAL': '🎯 Sniper Buy',
        'SNIPER_SELL_REJECTION': '🛑 Sniper Sell',
        'MOMENTUM_BREAKOUT': '🚀 Breakout',
        'GOLDEN_CROSS': '🟡 Golden Cross',
        'DEATH_CROSS': '💀 Death Cross',
        'RSI_OVERSOLD': '📉 RSI Oversold',
        'RSI_OVERBOUGHT': '📈 RSI Overbought',
        'BB_SQUEEZE': '🤐 Volatility Squeeze',
        'VOLUME_SURGE': '📊 Volume Surge',
        'MACD_BULL_CROSS': '🟢 MACD Bull Cross',
        'MACD_BEAR_CROSS': '🔴 MACD Bear Cross'
    };
    return map[name] || name.replace(/_/g, ' ');
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        console.log("Copied to clipboard");
    });
}

// --- CORE RENDER FUNCTIONS ---
async function refreshSignals(type) {
    const list = document.getElementById('marketScansList');
    if (!list) return;

    // 1. Loading State
    list.innerHTML = '<tr><td colspan="4" style="text-align:center; padding: 20px;"><div class="loader"></div> Scanning Market...</td></tr>';

    const data = await API.getSignals(type);

    if (!data.length) {
        list.innerHTML = '<tr><td colspan="4" style="text-align:center; padding: 20px;">No active signals found for this category.</td></tr>';
        return;
    }

    // 2. Audio Alert Logic (Play if latest signal is < 1 minute old)
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
            <tr class="signal-row" onclick="openChart('${assetName}')" title="Click to open Chart">
                <td style="font-weight:bold; width: 35%;">
                    ${assetName} 
                    <button class="btn-copy" onclick="event.stopPropagation(); copyToClipboard('${cleanName} on ${assetName} detected via CryptoPulse')" title="Copy Signal">📋</button>
                </td>
                <td style="width: 15%;"><span class="tf-badge">${s.timeframe}</span></td>
                <td class="${isBull ? 'text-success' : 'text-danger'}" style="width: 35%;">${cleanName}</td>
                <td style="color:var(--text-dim); font-size:12px; width: 15%;">${relativeTime}</td>
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

    container.innerHTML = alerts.map(a => `
        <div class="card alert-item" style="margin-bottom: 10px; padding: 12px; display: flex; justify-content: space-between; align-items: center;">
            <div>
                <strong>${a.asset}</strong> <span class="tf-badge tf-${a.timeframe}">${a.timeframe}</span><br>
                <small style="color: var(--text-dim);">${cleanSignalName(a.alert_type)}</small>
            </div>
            <button onclick="handleDeleteAlert(${a.id})" class="text-danger" style="background:none; border:none; cursor:pointer; font-size: 16px;">&times;</button>
        </div>`).join('');
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

// --- CHART MODAL FUNCTIONS ---
function openChart(symbol) {
    const modal = document.getElementById('chartModal');
    const title = document.getElementById('modalTitle');
    
    if(modal && title) {
        modal.style.display = 'flex';
        title.innerText = `${symbol}/USDT Analysis`;
        
        if (window.TradingView) {
            new TradingView.widget({
                "width": "100%",
                "height": 500,
                "symbol": "BINANCE:" + symbol + "USDT",
                "interval": "60",
                "timezone": "Etc/UTC",
                "theme": localStorage.getItem('theme') === 'light' ? 'light' : 'dark',
                "style": "1",
                "locale": "en",
                "toolbar_bg": "#f1f3f6",
                "enable_publishing": false,
                "hide_side_toolbar": false,
                "allow_symbol_change": true,
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

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', async () => {
    await initAuth();
    refreshSignals('ALL');
    refreshAlerts();
    updateTelegramUI();

    const form = document.getElementById('createAlertForm');
    if (form) {
        form.onsubmit = async (e) => {
            e.preventDefault();
            const status = document.getElementById('createAlertStatus');
            status.innerText = "⏳ Activating...";

            const payload = {
                asset: document.getElementById('alertAsset').value,
                timeframe: document.getElementById('alertTimeframe').value,
                signal_type: document.getElementById('alertType').value
            };

            const res = await API.createAlert(payload);
            if (res.success) {
                status.innerHTML = `<span class="text-success">✅ Alert Active!</span>`;
                refreshAlerts();
                form.reset();
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

    // --- SIDEBAR FILTERING (Cleaned Up) ---
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', function () {
            // 1. Highlight Active Tab
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            this.classList.add('active');
            
            // 2. Update Title
            const categoryType = this.getAttribute('data-type');
            const title = document.getElementById('currentCategoryTitle');
            if (title) title.innerText = this.innerText;

            // 3. Fetch Data (Removed Description Logic)
            refreshSignals(categoryType);
            
            if (window.innerWidth <= 1024 && sidebar.classList.contains('active')) {
                sidebar.classList.remove('active');
            }
        });
    });

    // Close Modal on Background Click
    window.onclick = function(event) {
        const modal = document.getElementById('chartModal');
        if (event.target == modal) {
            closeModal();
        }
    }
});