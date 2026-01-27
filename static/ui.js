/**
 * UI.JS - AlertDCX Pro Terminal
 * Fixes: Recurring Alert Visibility, Dropdown Colors
 */

// =========================================================
// 1. CONFIGURATION
// =========================================================

const WATCHLIST_KEY = 'alertdcx_watchlist';
const DEFAULT_WATCHLIST = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'BNBUSDT', 'DOGEUSDT', 'AVAXUSDT', 'LINKUSDT'];
let currentSymbol = 'BTCUSDT'; 

// Signal Definitions
const SIGNAL_DEFINITIONS = {
    'ALL': "Monitoring high-probability setups.",
    'SNIPER_BUY_REVERSAL': "Price < Support AND RSI < 30 AND Vol > 200%. (Reversal)",
    'SNIPER_SELL_REJECTION': "Price > Resistance AND RSI > 70 AND Vol > 200%. (Rejection)",
    'MOMENTUM_BREAKOUT': "Price breaks range AND Vol > 200% AND MACD Cross.",
    'GOLDEN_CROSS': "50 SMA crosses above 200 SMA (Bull Market Start).",
    'DEATH_CROSS': "50 SMA crosses below 200 SMA (Bear Market Start).",
    'VOLUME_SURGE': "Unusual whale activity detected (>3x Avg Vol).",
    'RSI_OVERSOLD': "RSI is below 30. Asset is undervalued.",
    'RSI_OVERBOUGHT': "RSI is above 70. Asset is overvalued.",
    'MACD_BULL_CROSS': "Momentum shifting to bullish.",
    'STRATEGY_UNLOCK_SHORT': "Unlock Strategy: High inflation token + BB Rejection.",
    'STRATEGY_BULLISH_200MA_RSI': "Trend Pullback: Price > 200MA + RSI Dip + Green Candle.", 
};

// Strategy Map
const STRATEGY_SIGNAL_MAP = {
    'vesting-short-v2': 'STRATEGY_UNLOCK_SHORT',
    'bullish-200ma-rsi': 'STRATEGY_BULLISH_200MA_RSI'
};

// TradingView Templates
const STUDY_MAP = {
    'RSI_OVERSOLD':        ['RSI@tv-basicstudies'],
    'GOLDEN_CROSS':        ['MASimple@tv-basicstudies', 'MASimple@tv-basicstudies'], 
    'STRATEGY_UNLOCK_SHORT': ['BB@tv-basicstudies'],
    'STRATEGY_BULLISH_200MA_RSI': ['MASimple@tv-basicstudies', 'RSI@tv-basicstudies']
};


// =========================================================
// 2. VIEW NAVIGATION
// =========================================================

function loadChartView(symbol, interval = null, signalType = 'NONE') {
    if (symbol && !symbol.toUpperCase().includes('USDT')) {
        symbol = symbol.toUpperCase() + 'USDT';
    }
    currentSymbol = symbol;
    
    // Get interval from dropdown if not provided
    if (!interval) {
        const tfSelect = document.getElementById('ai-timeframe-select');
        interval = tfSelect ? tfSelect.value : '240';
    }

    // Map to TV format
    const map = { '15m': '15', '1h': '60', '4h': '240', '1d': 'D', '1w': 'W' };
    const tvInterval = map[interval] || '240';

    // Toggle Views
    document.getElementById('chart-view').style.display = 'flex';
    document.getElementById('signal-view').style.display = 'none';
    document.getElementById('panel-ai').style.display = 'block';
    document.getElementById('panel-alerts').style.display = 'none';

    resetAIPanel();

    // Load Chart
    const indicators = STUDY_MAP[signalType] || [];
    if (window.TradingView) {
        document.getElementById('tradingview_chart_area').innerHTML = ""; 
        new TradingView.widget({
            "autosize": true,
            "symbol": "BINANCE:" + symbol,
            "interval": tvInterval,
            "timezone": "Etc/UTC",
            "theme": localStorage.getItem('theme') === 'light' ? 'light' : 'dark',
            "style": "1",
            "locale": "en",
            "toolbar_bg": "#f1f3f6",
            "enable_publishing": false,
            "hide_side_toolbar": false,
            "allow_symbol_change": true,
            "studies": indicators,
            "container_id": "tradingview_chart_area"
        });
    }
}

function onTimeframeChange() {
    const tf = document.getElementById('ai-timeframe-select').value;
    loadChartView(currentSymbol, tf);
}

function loadSignalView(type = 'ALL') {
    document.getElementById('chart-view').style.display = 'none';
    document.getElementById('signal-view').style.display = 'flex';
    document.getElementById('panel-ai').style.display = 'none';
    document.getElementById('panel-alerts').style.display = 'block';

    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    const activeItem = document.querySelector(`.nav-item[data-type="${type}"]`);
    if(activeItem) activeItem.classList.add('active');

    const title = document.getElementById('currentCategoryTitle');
    const desc = document.getElementById('categoryDescription');
    const mainTableDiv = document.getElementById('mainTableContainer');
    const strategyDiv = document.getElementById('strategiesContainer');

    if (type.startsWith('STRATEGY:')) {
        const slug = type.split(':')[1];
        if(title) title.innerText = "Algorithmic Strategy";
        if(desc) desc.innerText = "Backtested logic & performance metrics.";
        mainTableDiv.style.display = 'none';
        strategyDiv.style.display = 'block';
        refreshStrategies(slug);
    } else {
        if(title) title.innerText = type === 'ALL' ? "All Live Market Signals" : cleanSignalName(type);
        if(desc) desc.innerText = SIGNAL_DEFINITIONS[type] || "Live market data.";
        mainTableDiv.style.display = 'block';
        strategyDiv.style.display = 'none';
        refreshSignals(type);
    }
    refreshAlerts();
}

function switchSidebarTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.tab-btn[onclick="switchSidebarTab('${tabName}')"]`).classList.add('active');
    
    document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
    document.getElementById(`tab-${tabName}`).style.display = 'block';

    if (tabName === 'watchlist') loadChartView(currentSymbol);
    else loadSignalView('ALL');
}

// =========================================================
// 2. BULK ALERTS (FIXED: Recurring Alert Visible)
// =========================================================

function openCreateAlertModal() {
    const modal = document.getElementById('chartModal'); 
    const content = document.getElementById('tv_chart_container');
    const title = document.getElementById('modalTitle');
    
    if(title) title.innerText = "🔔 Create Bulk Alerts";

    const coins = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'BNB', 'DOGE', 'ENA', 'STRK', 'ZK'];
    const timeframes = ['15m', '1h', '4h'];
    
    const signals = [
        {val: 'PRICE_TARGET', label: 'Price Target (Exact)'},
        {val: 'GOLDEN_CROSS', label: 'Golden Cross (Bullish)'},
        {val: 'DEATH_CROSS', label: 'Death Cross (Bearish)'},
        {val: 'RSI_OVERSOLD', label: 'RSI Oversold (<30)'},
        {val: 'RSI_OVERBOUGHT', label: 'RSI Overbought (>70)'},
        {val: 'STRATEGY_UNLOCK_SHORT', label: 'Unlock Strategy Short'},
        {val: 'STRATEGY_BULLISH_200MA_RSI', label: 'Bullish 200MA Pullback'} 
    ];

    const coinHtml = coins.map(c => `
        <label style="display:flex; align-items:center; gap:8px; cursor:pointer; background:rgba(255,255,255,0.05); padding:8px; border-radius:4px;">
            <input type="checkbox" class="bulk-asset" value="${c}/USDT" checked style="accent-color:#00ff88;"> 
            <span style="font-weight:bold; font-size:13px; color:white;">${c}</span>
        </label>
    `).join('');

    const tfHtml = timeframes.map(tf => `
        <label style="display:flex; align-items:center; gap:8px; cursor:pointer; background:rgba(255,255,255,0.05); padding:8px; border-radius:4px;">
            <input type="checkbox" class="bulk-tf" value="${tf}" checked style="accent-color:#00ff88;"> 
            <span style="font-size:13px; color:white;">${tf}</span>
        </label>
    `).join('');

    const signalOptions = signals.map(s => 
        `<option value="${s.val}" style="background-color:#1e222d; color:white;">${s.label}</option>`
    ).join('');

    content.innerHTML = `
        <div style="padding: 20px; color: white;">
            
            <div style="margin-bottom: 20px;">
                <label style="color:#888; font-size:12px; display:block; margin-bottom:8px; font-weight:bold;">1. SELECT ASSETS</label>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; max-height: 150px; overflow-y: auto;">
                    ${coinHtml}
                </div>
            </div>

            <div style="margin-bottom: 20px;">
                <label style="color:#888; font-size:12px; display:block; margin-bottom:8px; font-weight:bold;">2. TIMEFRAMES</label>
                <div style="display: flex; gap: 10px;">
                    ${tfHtml}
                </div>
            </div>

            <div class="input-group" style="margin-bottom: 20px;">
                <label style="color:#888; font-size:12px; display:block; margin-bottom:8px; font-weight:bold;">3. CONDITION</label>
                <select id="newAlertSignal" onchange="toggleBulkPriceInput(this.value)" 
                    style="width:100%; padding:12px; background-color:#1e222d; color:white; border:1px solid #444; border-radius:6px; outline:none;">
                    ${signalOptions}
                </select>
            </div>

            <div id="bulkPriceGroup" class="input-group" style="margin-bottom: 20px;">
                <label style="color:#888; font-size:12px; display:block; margin-bottom:8px;">Target Price ($)</label>
                <input type="number" id="newAlertPrice" placeholder="e.g. 65000" step="any" 
                    style="width:100%; padding:12px; background-color:#1e222d; color:white; border:1px solid #444; border-radius:6px; outline:none;">
            </div>

            <div style="margin-bottom: 25px; display: flex; align-items: center;">
                <input type="checkbox" id="newAlertRecurring" style="width:16px; height:16px; accent-color:#00ff88; cursor:pointer;">
                <label for="newAlertRecurring" style="margin-left: 10px; color: white; font-size: 14px; cursor:pointer;">Recurring Alert</label>
            </div>

            <div style="display: flex; gap: 10px; margin-top:30px;">
                <button onclick="closeModal()" style="flex:1; padding: 12px; background: transparent; border: 1px solid #444; color: #888; border-radius: 6px; cursor: pointer;">Cancel</button>
                <button id="btnSaveAlert" onclick="submitBulkAlerts()" class="btn-create" style="flex:2; border-radius:6px; background:#00ff88; color:black; font-weight:bold; border:none;">Create Alerts</button>
            </div>
            
            <div id="bulkProgress" style="margin-top:15px; text-align:center; color:#00ff88; font-size:13px; display:none;"></div>
        </div>
    `;

    modal.style.display = 'flex';
    toggleBulkPriceInput('PRICE_TARGET'); 
}

function toggleBulkPriceInput(val) {
    const el = document.getElementById('bulkPriceGroup');
    if (val === 'PRICE_TARGET') el.style.display = 'block';
    else el.style.display = 'none';
}

async function submitBulkAlerts() {
    const btn = document.getElementById('btnSaveAlert');
    const progress = document.getElementById('bulkProgress');
    
    const selectedAssets = Array.from(document.querySelectorAll('.bulk-asset:checked')).map(c => c.value);
    const selectedTFs = Array.from(document.querySelectorAll('.bulk-tf:checked')).map(c => c.value);
    const signalType = document.getElementById('newAlertSignal').value;
    const targetPrice = document.getElementById('newAlertPrice').value;
    const isRecurring = document.getElementById('newAlertRecurring').checked;
    
    if (selectedAssets.length === 0 || selectedTFs.length === 0) {
        alert("Please select at least one Asset and one Timeframe.");
        return;
    }
    if (signalType === 'PRICE_TARGET' && !targetPrice) {
        alert("Please enter a Target Price.");
        return;
    }

    btn.disabled = true;
    btn.innerText = "Processing...";
    progress.style.display = 'block';

    let successCount = 0;
    
    for (const asset of selectedAssets) {
        for (const tf of selectedTFs) {
            progress.innerText = `Creating alert for ${asset} (${tf})...`;
            const payload = {
                asset: asset,
                timeframe: tf,
                signal_type: signalType,
                target_price: targetPrice || null,
                is_recurring: isRecurring,
                user_id: getUserId()
            };
            const res = await API.createAlert(payload);
            if (res.success) successCount++;
        }
    }

    progress.innerText = `✅ Created ${successCount} alerts!`;
    setTimeout(() => {
        closeModal();
        refreshAlerts();
        btn.disabled = false;
        btn.innerText = "Create Alerts";
    }, 1500);
}

// =========================================================
// 3. REST OF LOGIC (DATA, AI, WATCHLIST)
// =========================================================

async function refreshSignals(type) {
    const list = document.getElementById('marketScansList');
    if(!list) return;
    list.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:30px;"><div class="loader"></div> Scanning...</td></tr>';
    
    const data = await API.getSignals(type);
    
    if(!data.length) { list.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:30px; color:#888;">No active signals found.</td></tr>'; return; }

    list.innerHTML = data.map(s => {
        const isBull = s.signal_type.includes('BUY') || s.signal_type.includes('BULL') || s.signal_type.includes('GOLDEN');
        return `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); cursor:pointer;" onclick="loadChartView('${s.asset.replace('/','')}', '60', '${s.signal_type}')">
            <td style="padding:15px; font-weight:bold;">${s.asset.replace('/USDT','')}</td>
            <td><span class="tf-badge">${s.timeframe}</span></td>
            <td style="color:${isBull ? '#00ff88' : '#ff4757'}">${cleanSignalName(s.signal_type)}</td>
            <td style="color:#888; font-size:12px;">${timeAgo(s.detected_at)}</td>
        </tr>`;
    }).join('');
}

async function refreshStrategies(filterSlug) {
    const container = document.getElementById('strategiesContainer');
    container.innerHTML = '<div class="loader"></div> Loading...';
    let strategies = await API.getStrategies();
    if (filterSlug) strategies = strategies.filter(s => s.slug === filterSlug);

    const htmlPromises = strategies.map(async (strat) => {
        const signalType = STRATEGY_SIGNAL_MAP[strat.slug];
        let liveSignalsHtml = '';
        if (signalType) {
            const liveSignals = await API.getSignals(signalType);
            if (liveSignals.length > 0) {
                const rows = liveSignals.map(s => `
                    <tr onclick="loadChartView('${s.asset.replace('/','')}', '240', '${s.signal_type}')" style="cursor:pointer; border-bottom:1px solid rgba(255,255,255,0.05);">
                        <td style="padding:10px;"><b>${s.asset.replace('/USDT','')}</b></td>
                        <td>${s.timeframe}</td>
                        <td class="text-success">ACTIVE</td>
                    </tr>`).join('');
                liveSignalsHtml = `<div style="margin-bottom:20px; border:1px solid var(--accent-green); border-radius:8px; overflow:hidden;"><table style="width:100%; font-size:13px;">${rows}</table></div>`;
            } else {
                liveSignalsHtml = `<div style="margin-bottom:20px; padding:15px; border:1px dashed #444; border-radius:8px; text-align:center; color:#666;">No live signals currently.</div>`;
            }
        }
        return `${liveSignalsHtml}<div class="card" style="padding:20px; margin-bottom:20px;"><h2 style="color:var(--accent-blue); margin-top:0;">${strat.name}</h2><p style="color:#888; font-size:14px;">${strat.description}</p></div>`;
    });
    const rendered = await Promise.all(htmlPromises);
    container.innerHTML = rendered.join('');
}

async function refreshAlerts() {
    const alerts = await API.getMyAlerts();
    const container = document.getElementById('myAlertsList');
    if (!container) return;
    if (!alerts.length || alerts.error) {
        container.innerHTML = '<p style="text-align:center; color:#888; font-size:13px;">No active alerts.</p>';
        return;
    }
    container.innerHTML = alerts.map(a => `
        <div class="card alert-item" style="margin-bottom: 10px; padding: 12px; display: flex; justify-content: space-between; align-items: center;">
            <div><strong>${a.asset}</strong> <span class="tf-badge tf-${a.timeframe}">${a.timeframe}</span><br><small style="color:#888;">${cleanSignalName(a.alert_type)}</small></div>
            <button onclick="handleDeleteAlert(${a.id})" class="text-danger" style="background:none; border:none; cursor:pointer; font-size:16px;">&times;</button>
        </div>`).join('');
}

// --- WATCHLIST, TICKER & HELPERS ---
function getWatchlist() { return JSON.parse(localStorage.getItem(WATCHLIST_KEY) || '[]'); }
function renderWatchlist() {
    const list = getWatchlist().length ? getWatchlist() : DEFAULT_WATCHLIST;
    document.getElementById('userWatchlist').innerHTML = list.map(sym => `
        <div class="watchlist-item" onclick="loadChartView('${sym}')">
            <div style="font-weight:600; color:white;">${sym.replace('USDT','')}</div>
            <span class="watchlist-remove" onclick="event.stopPropagation(); removeFromWatchlist('${sym}')">✕</span>
        </div>`).join('');
}
function addToWatchlist(symbol) {
    if (!symbol.toUpperCase().includes('USDT')) symbol += 'USDT';
    const list = getWatchlist();
    if (!list.includes(symbol)) { list.push(symbol); localStorage.setItem(WATCHLIST_KEY, JSON.stringify(list)); renderWatchlist(); }
}
function removeFromWatchlist(symbol) {
    const list = getWatchlist().filter(s => s !== symbol);
    localStorage.setItem(WATCHLIST_KEY, JSON.stringify(list));
    renderWatchlist();
}

async function updateTicker() {
    const container = document.getElementById('tickerBar');
    if (!container) return;
    try {
        const res = await fetch('https://data-api.binance.vision/api/v3/ticker/24hr');
        const data = await res.json();
        const relevantData = data.filter(item => getWatchlist().includes(item.symbol) || DEFAULT_WATCHLIST.includes(item.symbol));
        container.innerHTML = relevantData.slice(0, 10).map(item => {
            const isUp = parseFloat(item.priceChangePercent) >= 0;
            return `<div class="ticker-item" style="display:inline-block; margin-right:20px; font-size:12px;"><span style="font-weight:bold; color:white;">${item.symbol.replace('USDT','')}</span> <span style="color:${isUp?'#00ff88':'#ff4757'}">${parseFloat(item.lastPrice).toFixed(2)} (${isUp?'+':''}${parseFloat(item.priceChangePercent).toFixed(2)}%)</span></div>`;
        }).join('');
    } catch (e) { console.error("Ticker Error:", e); }
}

async function updateTelegramUI() {
    const isLinked = await API.getTelegramStatus();
    const btn = document.getElementById('connectTelegramBtn');
    if (btn) {
        if (isLinked) {
            btn.innerHTML = "✅ Connected"; btn.style.border = "1px solid var(--accent-green)"; btn.style.color = "var(--accent-green)"; btn.href = "#";
        } else {
            const userId = getUserId(); btn.href = `https://t.me/${window.BOT_USERNAME}?start=${userId}`; btn.innerHTML = "Link Telegram Bot";
        }
    }
}

function resetAIPanel() {
    if(document.getElementById('ai-trend')) {
        document.getElementById('ai-trend').innerText = "--";
        document.getElementById('ai-support').innerText = "--";
        document.getElementById('ai-signal-box').innerText = "READY";
        document.getElementById('ai-signal-box').style.background = "#333";
    }
}

async function runAIAnalysis() {
    const btn = document.getElementById('analyze-btn');
    const tf = document.getElementById('ai-timeframe-select').value;
    btn.innerText = "⏳ Analyzing..."; btn.disabled = true;
    try {
        const res = await fetch('/api/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol: "BINANCE:" + currentSymbol, interval: tf }) });
        const data = await res.json();
        if(data.error) throw new Error(data.error);
        document.getElementById('ai-trend').innerText = data.trend;
        document.getElementById('ai-support').innerText = data.support;
        document.getElementById('ai-reasoning').innerText = data.reasoning;
        const sigBox = document.getElementById('ai-signal-box');
        sigBox.innerText = data.signal;
        sigBox.style.background = data.signal.includes('BUY') ? "#00c853" : (data.signal.includes('SELL') ? "#d50000" : "#ffd600");
    } catch (e) { alert("Analysis Error: " + e.message); } 
    finally { btn.innerText = "✨ Analyze Chart"; btn.disabled = false; }
}

function timeAgo(dateString) { return Math.floor((new Date() - new Date(dateString)) / 60000) + "m ago"; }
function cleanSignalName(name) { return name ? name.replace(/_/g, ' ').replace('STRATEGY', '').trim() : ''; }
function closeModal() { document.getElementById('chartModal').style.display = 'none'; }
async function handleDeleteAlert(id) { if (confirm("Stop receiving this alert?")) { await API.deleteAlert(id); refreshAlerts(); } }

document.addEventListener('DOMContentLoaded', async () => {
    await initAuth();
    renderWatchlist();
    updateTicker();
    setInterval(updateTicker, 10000);
    loadChartView('BTCUSDT'); 
    updateTelegramUI();
    document.getElementById('watchlistInput').addEventListener('keypress', function (e) { if (e.key === 'Enter' && this.value.trim()) { addToWatchlist(this.value.toUpperCase().trim()); this.value = ''; } });
});