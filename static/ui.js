/**
 * UI.JS - Handles Dashboard, Charts, Audio, Live Ticker & Bulk Alerts
 */

// --- 1. CONFIGURATION & DEFINITIONS ---
const WATCHLIST = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'BNBUSDT', 'DOGEUSDT'];

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
    'MACD_BULL_CROSS': "Momentum shifting to bullish.",

    // Strategies
    'STRATEGY_UNLOCK_SHORT': "Unlock Strategy: High inflation token + BB Rejection.",
};

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
    'MOMENTUM_BREAKOUT':   ['MACD@tv-basicstudies'],
    'STRATEGY_UNLOCK_SHORT': ['BB@tv-basicstudies'] 
};

const TF_MAP = { '15m': '15', '1h': '60', '4h': '240', '1d': 'D' };

// --- 2. LIVE TICKER FUNCTION ---
async function updateTicker() {
    const container = document.getElementById('tickerBar');
    if (!container) return;

    try {
        const res = await fetch('https://data-api.binance.vision/api/v3/ticker/24hr');
        const data = await res.json();
        const relevantData = data.filter(item => WATCHLIST.includes(item.symbol));

        container.innerHTML = relevantData.map(item => {
            const asset = item.symbol.replace('USDT', '');
            const price = parseFloat(item.lastPrice);
            const change = parseFloat(item.priceChangePercent);
            const isUp = change >= 0;
            
            const displayPrice = price < 1 
                ? price.toFixed(4) 
                : price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});

            return `
                <div class="ticker-item">
                    <div class="ticker-pair">${asset} <span style="opacity:0.5">/ USDT</span></div>
                    <div class="ticker-data">
                        <span class="ticker-price">$${displayPrice}</span>
                        <span class="ticker-change ${isUp ? 'ticker-up' : 'ticker-down'}">
                            ${isUp ? '▲' : '▼'} ${Math.abs(change).toFixed(2)}%
                        </span>
                    </div>
                </div>
            `;
        }).join('');

    } catch (e) {
        console.error("Ticker Error:", e);
    }
}

// --- 3. HELPER FUNCTIONS ---
function timeAgo(dateString) {
    const date = new Date(dateString);
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 60) return Math.floor(seconds) + "s ago";
    if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
    if (seconds < 86400) return Math.floor(seconds / 3600) + "h ago";
    return Math.floor(seconds / 86400) + "d ago";
}

function cleanSignalName(name, price = null) {
    if (name.includes('PRICE_TARGET') && price) {
        const direction = name.includes('ABOVE') ? ' (Above)' : name.includes('BELOW') ? ' (Below)' : '';
        return `💰 Target: $${price}${direction}`;
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
        'MACD_BULL_CROSS': '🟢 MACD Bull Cross',
        'STRATEGY_UNLOCK_SHORT': '🧠 Unlock Short'
    };
    return map[name] || name.replace(/_/g, ' ');
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        console.log("Copied to clipboard");
    });
}

// --- 4. BULK ALERT CREATION LOGIC (NEW) ---

// --- 4. BULK ALERT CREATION LOGIC (NEW) ---

function openCreateAlertModal() {
    const modal = document.getElementById('chartModal'); 
    const content = document.getElementById('tv_chart_container');
    const title = document.getElementById('modalTitle');
    
    if(title) title.innerText = "🔔 Create Bulk Alerts";

    // 1. Define Options
    const coins = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT', 'BNB/USDT', 'DOGE/USDT', 'ENA/USDT', 'STRK/USDT', 'ZK/USDT', 'PIXEL/USDT'];
    const timeframes = ['15m', '1h', '4h'];
    
    // UPDATED SIGNALS LIST (Added Death Cross)
    const signals = [
        {val: 'PRICE_TARGET', label: 'Price Target (Exact)'},
        {val: 'GOLDEN_CROSS', label: 'Golden Cross (Bullish)'},
        {val: 'DEATH_CROSS', label: 'Death Cross (Bearish)'}, // <--- ADDED THIS
        {val: 'RSI_OVERSOLD', label: 'RSI Oversold (<30)'},
        {val: 'RSI_OVERBOUGHT', label: 'RSI Overbought (>70)'},
        {val: 'VOLATILITY_SQUEEZE', label: 'Volatility Squeeze'},
        {val: 'STRATEGY_UNLOCK_SHORT', label: 'Unlock Strategy Short'}
    ];

    // 2. Build HTML
    const coinCheckboxes = coins.map(c => `
        <label style="display:inline-block; width:45%; margin-bottom:8px; cursor:pointer;">
            <input type="checkbox" class="bulk-asset" value="${c}" checked> 
            <span style="margin-left:5px; font-weight:bold;">${c.replace('/USDT','')}</span>
        </label>
    `).join('');

    const tfCheckboxes = timeframes.map(tf => `
        <label style="display:inline-block; width:30%; margin-bottom:8px; cursor:pointer;">
            <input type="checkbox" class="bulk-tf" value="${tf}" checked> 
            <span style="margin-left:5px;">${tf}</span>
        </label>
    `).join('');

    const signalOptions = signals.map(s => `<option value="${s.val}">${s.label}</option>`).join('');

    content.innerHTML = `
        <div style="padding: 20px; color: var(--text-main);">
            <div style="margin-bottom: 20px;">
                <label style="color:var(--text-dim); font-size:12px; text-transform:uppercase; display:block; margin-bottom:10px;">1. Select Assets</label>
                <div style="max-height: 150px; overflow-y: auto; background: rgba(0,0,0,0.2); padding: 10px; border: 1px solid var(--border-color); border-radius: 8px;">
                    ${coinCheckboxes}
                </div>
                <div style="margin-top:5px; font-size:11px;">
                    <a href="#" onclick="document.querySelectorAll('.bulk-asset').forEach(c => c.checked=true); return false;" style="color:var(--accent-blue);">Select All</a> | 
                    <a href="#" onclick="document.querySelectorAll('.bulk-asset').forEach(c => c.checked=false); return false;" style="color:var(--text-dim);">Clear</a>
                </div>
            </div>

            <div style="margin-bottom: 20px;">
                <label style="color:var(--text-dim); font-size:12px; text-transform:uppercase; display:block; margin-bottom:10px;">2. Select Timeframes</label>
                <div>${tfCheckboxes}</div>
            </div>

            <div class="input-group" style="margin-bottom: 20px;">
                <label>3. Trigger Condition</label>
                <select id="newAlertSignal" onchange="toggleBulkPriceInput(this.value)" style="width:100%; padding:10px;">
                    ${signalOptions}
                </select>
            </div>

            <div id="bulkPriceGroup" class="input-group" style="margin-bottom: 20px;">
                <label>Target Price ($)</label>
                <input type="number" id="newAlertPrice" placeholder="e.g. 65000" step="any" style="width:100%; padding:12px; background:var(--bg-dark); border:1px solid var(--border-color); color:white; border-radius:8px;">
            </div>

            <div style="margin-bottom: 25px;">
                <label style="cursor:pointer; display:flex; align-items:center;">
                    <input type="checkbox" id="newAlertRecurring">
                    <span style="margin-left: 10px; color: var(--text-dim);">Recurring Alert</span>
                </label>
            </div>

            <div style="display: flex; gap: 10px;">
                <button onclick="closeModal()" style="flex:1; padding: 12px; background: transparent; border: 1px solid var(--border-color); color: var(--text-dim); border-radius: 8px; cursor: pointer;">Cancel</button>
                <button id="btnSaveAlert" onclick="submitBulkAlerts()" class="btn-create" style="flex:2;">Create Alerts</button>
            </div>
            
            <div id="bulkProgress" style="margin-top:15px; text-align:center; color:var(--accent-green); font-size:13px; display:none;"></div>
        </div>
    `;

    modal.style.display = 'flex';
    toggleBulkPriceInput('PRICE_TARGET'); 
}

function toggleBulkPriceInput(val) {
    const el = document.getElementById('bulkPriceGroup');
    if (val === 'PRICE_TARGET') {
        el.style.display = 'block';
    } else {
        el.style.display = 'none';
    }
}

async function submitBulkAlerts() {
    const btn = document.getElementById('btnSaveAlert');
    const progress = document.getElementById('bulkProgress');
    
    // Gather Data
    const selectedAssets = Array.from(document.querySelectorAll('.bulk-asset:checked')).map(c => c.value);
    const selectedTFs = Array.from(document.querySelectorAll('.bulk-tf:checked')).map(c => c.value);
    const signalType = document.getElementById('newAlertSignal').value;
    const targetPrice = document.getElementById('newAlertPrice').value;
    const isRecurring = document.getElementById('newAlertRecurring').checked;

    // Validate
    if (selectedAssets.length === 0 || selectedTFs.length === 0) {
        alert("Please select at least one Asset and one Timeframe.");
        return;
    }
    if (signalType === 'PRICE_TARGET' && !targetPrice) {
        alert("Please enter a Target Price.");
        return;
    }

    // UI Updates
    btn.disabled = true;
    btn.innerText = "Processing...";
    progress.style.display = 'block';

    let successCount = 0;
    const total = selectedAssets.length * selectedTFs.length;

    // Loop
    for (const asset of selectedAssets) {
        for (const tf of selectedTFs) {
            progress.innerText = `Creating alert for ${asset} (${tf})...`;
            
            const payload = {
                asset: asset,
                timeframe: tf,
                signal_type: signalType,
                target_price: targetPrice || null,
                is_recurring: isRecurring
            };

            const res = await API.createAlert(payload);
            if (res.success) successCount++;
        }
    }

    progress.innerText = `✅ Created ${successCount} of ${total} alerts successfully!`;
    setTimeout(() => {
        closeModal();
        refreshAlerts(); // Update the sidebar list
    }, 1500);
}

// --- 5. CORE RENDER FUNCTIONS ---
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

// --- NEW: STRATEGY RENDERER ---
async function refreshStrategies() {
    const container = document.getElementById('strategiesContainer');
    if (!container) return; 

    container.innerHTML = '<div class="loader"></div> Loading Strategy Data...';
    
    const strategies = await API.getStrategies();
    const liveSignals = await API.getSignals('STRATEGY_UNLOCK_SHORT');

    if (!strategies.length) {
        container.innerHTML = '<p style="text-align:center;">No strategies available yet.</p>';
        return;
    }

    let liveSignalsHtml = '';
    if (liveSignals.length > 0) {
        const rows = liveSignals.map(s => {
            const relativeTime = timeAgo(s.detected_at);
            const cleanName = cleanSignalName(s.signal_type);
            const assetName = s.asset.replace('/USDT', '');
            
            return `
            <tr class="signal-row" onclick="openChart('${assetName}', '${s.timeframe}', '${s.signal_type}')" style="background: rgba(0, 255, 136, 0.05);">
                <td style="font-weight:bold; padding:12px;">${assetName}</td>
                <td><span class="tf-badge">${s.timeframe}</span></td>
                <td class="text-danger">SHORT SIGNAL</td> 
                <td style="color:var(--text-dim); font-size:12px;">${relativeTime}</td>
                <td style="text-align: right;"><button class="btn-view-chart">View Chart</button></td>
            </tr>`;
        }).join('');

        liveSignalsHtml = `
            <div style="margin-bottom: 30px; border: 1px solid var(--accent-green); border-radius: 12px; overflow: hidden;">
                <div style="background: rgba(0, 255, 136, 0.1); padding: 15px; border-bottom: 1px solid var(--accent-green); display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="margin:0; color: var(--accent-green); font-size: 16px;">⚡ Active Strategy Signals</h3>
                    <span class="update-tag" style="background: var(--accent-green); color: black; font-weight: bold;">LIVE</span>
                </div>
                <table style="width: 100%; border-collapse: collapse;">
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
    } else {
        liveSignalsHtml = `
            <div style="margin-bottom: 30px; padding: 20px; text-align: center; border: 1px dashed var(--border-color); border-radius: 12px; color: var(--text-dim);">
                No active signals for this strategy right now.<br>
                <small>Scanning 4H candles for BB Rejections...</small>
            </div>
        `;
    }

    container.innerHTML = strategies.map(strat => {
        const logic = strat.logic_summary || {};
        const perfRows = strat.performance && strat.performance.length > 0 
            ? strat.performance.map(p => `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <td style="padding:10px;"><strong>${p.asset}</strong></td>
                    <td>${p.total_trades}</td>
                    <td class="${p.win_rate_percent >= 50 ? 'text-success' : 'text-danger'}">${p.win_rate_percent}%</td>
                    <td class="${p.total_pnl_percent >= 0 ? 'text-success' : 'text-danger'}">${p.total_pnl_percent > 0 ? '+' : ''}${p.total_pnl_percent}%</td>
                    <td style="color: #ff6b6b;">-${p.max_drawdown_percent}%</td>
                </tr>
            `).join('')
            : '<tr><td colspan="5" style="text-align:center; padding:10px;">No backtest data available yet.</td></tr>';

        return `
        ${liveSignalsHtml}

        <div style="background: var(--card-bg); border-radius: 12px; padding: 24px; margin-bottom: 30px; border: 1px solid var(--border-color);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 15px;">
                <h2 style="color: var(--accent-color); margin:0; font-size: 1.5rem;">${strat.name}</h2>
                <span style="background: #ff4757; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">Risk: ${strat.risk_profile}</span>
            </div>
            
            <p style="color: var(--text-dim); line-height: 1.5;">${strat.description}</p>

            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 25px 0;">
                <div class="logic-box"><strong>🎯 Trigger</strong><br><span style="color:var(--text-dim); font-size:0.9em;">${logic.Trigger || 'N/A'}</span></div>
                <div class="logic-box"><strong>🛑 Filter</strong><br><span style="color:var(--text-dim); font-size:0.9em;">${logic.Filter || 'N/A'}</span></div>
                <div class="logic-box"><strong>⏳ Window</strong><br><span style="color:var(--text-dim); font-size:0.9em;">${logic.Window || 'N/A'}</span></div>
                <div class="logic-box"><strong>🚪 Exit</strong><br><span style="color:var(--text-dim); font-size:0.9em;">${logic.Exit || 'N/A'}</span></div>
            </div>

            <h3 style="margin-top: 30px; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; font-size: 1.2rem;">📊 Backtest Performance (2 Years)</h3>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.95em;">
                    <thead>
                        <tr style="text-align: left; color: var(--text-dim);">
                            <th style="padding: 10px;">Asset</th>
                            <th style="padding: 10px;">Trades</th>
                            <th style="padding: 10px;">Win Rate</th>
                            <th style="padding: 10px;">Total PnL</th>
                            <th style="padding: 10px;">Max DD</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${perfRows}
                    </tbody>
                </table>
            </div>
        </div>
        `;
    }).join('');
}

// --- NEW: VIEW NAVIGATION ---
function showSection(sectionId) {
    const dashboardDiv = document.getElementById('dashboardSection');
    const strategiesDiv = document.getElementById('strategiesSection');

    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));

    if (sectionId === 'strategies') {
        if(dashboardDiv) dashboardDiv.style.display = 'none';
        if(strategiesDiv) strategiesDiv.style.display = 'block';
        refreshStrategies();
        if (event && event.currentTarget) event.currentTarget.classList.add('active');
    } else {
        if(dashboardDiv) dashboardDiv.style.display = 'block';
        if(strategiesDiv) strategiesDiv.style.display = 'none';
        if (event && event.currentTarget) event.currentTarget.classList.add('active');
    }
}

// --- 6. CHART MODAL ---
function openChart(symbol, timeframe = '1h', signalType = 'NONE') {
    const modal = document.getElementById('chartModal');
    const title = document.getElementById('modalTitle');
    const container = document.getElementById('tv_chart_container');
    
    if(modal && title) {
        modal.style.display = 'flex';
        const cleanName = signalType !== 'NONE' ? cleanSignalName(signalType) : 'Analysis';
        title.innerText = `${symbol}/USDT - ${timeframe} - ${cleanName}`;
        
        // Ensure container is empty before creating widget
        container.innerHTML = '';

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
    // Clear container to remove Chart OR Bulk Alert Form
    document.getElementById('tv_chart_container').innerHTML = '';
}

// --- 7. EVENTS & INITIALIZATION ---
async function handleDeleteAlert(id) {
    if (confirm("Stop receiving this alert?")) {
        await API.deleteAlert(id);
        refreshAlerts();
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Initialize Auth
    await initAuth();

    // 2. Initial Data Load
    refreshSignals('ALL');
    refreshAlerts();
    updateTelegramUI();
    
    // 3. Start Live Price Ticker (Runs every 10s)
    updateTicker();
    setInterval(updateTicker, 10000);

    // 4. Alert Creation Logic (Old Sidebar Form - Optional)
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
                target_price: document.getElementById('alertPrice').value || null, 
                is_recurring: document.getElementById('recurringAlert').checked
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

    // 5. Sidebar & Menu Logic
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

    // 6. Navigation Logic (Updates Description Inline)
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', function (e) {
            const categoryType = this.getAttribute('data-type');
            if (categoryType === 'STRATEGY_VIEW') return;
            
            showSection('dashboard'); 

            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            this.classList.add('active');
            
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