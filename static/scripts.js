// --- GLOBAL CONFIGURATION ---
// Automatically switches between local and production URLs
const API_BASE_URL = window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1') 
    ? 'http://127.0.0.1:5001' 
    : window.location.origin;

const TOKEN_STORAGE_KEY = 'access_token';
const USER_ID_STORAGE_KEY = 'user_id'; 

let supabaseClient = null;

// ==========================================================
// 1. CONFIGURATION & INITIALIZATION
// ==========================================================

async function fetchConfig() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/config`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error("Failed to fetch configuration:", error);
        return { SUPABASE_URL: null, SUPABASE_KEY: null };
    }
}

async function initializeSupabase() {
    const config = await fetchConfig();
    if (config.SUPABASE_URL && config.SUPABASE_KEY && typeof supabase !== 'undefined') {
        try {
            supabaseClient = supabase.createClient(config.SUPABASE_URL, config.SUPABASE_KEY);
            console.log("Supabase client initialized.");
        } catch (e) {
            console.error("Failed to create Supabase client:", e);
        }
    }
}

// ==========================================================
// 2. AUTHENTICATION HELPERS
// ==========================================================

function getToken() { return localStorage.getItem(TOKEN_STORAGE_KEY); }
function getUserId() { return localStorage.getItem(USER_ID_STORAGE_KEY); }

function logout() {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    localStorage.removeItem(USER_ID_STORAGE_KEY); 
    window.location.href = 'login.html';
}

function updateAuthStatusUI() {
    const token = getToken();
    const authStatusLink = document.getElementById('authStatusLink');
    if (authStatusLink) {
        authStatusLink.innerHTML = token 
            ? `<a href="#" onclick="logout()" class="nav-link">Logout</a>` 
            : `<a href="login.html" class="nav-link">Login</a>`;
    }
}

async function checkSupabaseSession() {
    if (!supabaseClient) await initializeSupabase();
    if (!supabaseClient) return null;

    const { data: { session } } = await supabaseClient.auth.getSession();
    if (session) {
        localStorage.setItem(TOKEN_STORAGE_KEY, session.access_token);
        localStorage.setItem(USER_ID_STORAGE_KEY, session.user.id);
        updateAuthStatusUI();
        return session;
    }
    return null;
}

// ==========================================================
// 3. MARKET SIGNALS (Date Parsing & Display)
// ==========================================================

async function fetchMarketSignals(type = 'ALL') {
    const scanList = document.getElementById('marketScansList');
    if (!scanList) return;

    try {
        const endpoint = type === 'ALL' ? '/api/signals' : `/api/signals?type=${type}`;
        const response = await fetch(`${API_BASE_URL}${endpoint}`);
        const scans = await response.json();

        if (!scans || scans.length === 0) {
            scanList.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:20px; color:var(--text-dim);">No ${type} signals available.</td></tr>`;
            return;
        }

        scanList.innerHTML = scans.map(s => {
            const bullTerms = ['BULL', 'OVERSOLD', 'GOLDEN', 'PULLBACK', 'UPPER_BREAKOUT', 'NEW_HIGH'];
            const isBullish = bullTerms.some(term => s.signal_type.includes(term));
            const signalClass = isBullish ? 'text-success' : 'text-danger';
            
            let dateStr = s.detected_at || s.created_at;
            if (dateStr && typeof dateStr === 'string') {
                dateStr = dateStr.replace(' ', 'T');
            }
            
            const signalTime = new Date(dateStr);
            const isValid = !isNaN(signalTime.getTime());
            
            const now = new Date();
            const diffInMinutes = Math.abs(now - signalTime) / (1000 * 60);
            const isNew = isValid && diffInMinutes <= 20; 
            const newBadge = isNew ? '<span class="new-tag">NEW</span>' : '';

            const displayDateTime = isValid ? signalTime.toLocaleString('en-IN', { 
                day: '2-digit', month: '2-digit', year: '2-digit',
                hour: '2-digit', minute: '2-digit', hour12: true 
            }) : "Pending...";

            return `
                <tr>
                    <td class="asset-cell">${s.asset.replace('/USDT', '')} ${newBadge}</td>
                    <td><span class="tf-badge tf-${s.timeframe}">${s.timeframe}</span></td>
                    <td class="${signalClass}">${s.signal_type.replace(/_/g, ' ')}</td>
                    <td style="color:var(--text-dim); font-size: 0.85em; white-space: nowrap;">${displayDateTime}</td>
                </tr>
            `;
        }).join('');
    } catch (err) { console.error("Signal Fetch Error:", err); }
}

// ==========================================================
// 4. ALERT MANAGEMENT & TELEGRAM STATUS
// ==========================================================

async function fetchAndDisplayAlerts() {
    const listContainer = document.getElementById('myAlertsList');
    const telegramSection = document.getElementById('telegramLinkSection');
    const token = getToken();
    const userId = getUserId();
    
    if (!listContainer || !token) return;

    try {
        if (supabaseClient && userId) {
            const { data: profile } = await supabaseClient.from('users').select('telegram_chat_id').eq('user_uuid', userId).single();
            if (profile && profile.telegram_chat_id) {
                telegramSection.innerHTML = `
                    <div style="background: rgba(0, 255, 136, 0.1); padding: 12px; border-radius: 8px; border: 1px solid var(--accent-green);">
                        <h4 style="color: var(--accent-green); margin: 0; font-size: 13px;">✅ Telegram Linked</h4>
                        <p style="font-size: 11px; color: var(--text-dim); margin-top: 4px;">You are receiving instant signals.</p>
                    </div>`;
            }
        }

        const response = await fetch(`${API_BASE_URL}/api/my-alerts`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const alerts = await response.json();

        if (!alerts || alerts.length === 0) {
            listContainer.innerHTML = `
                <div style="text-align: center; padding: 20px; color: var(--text-dim); border: 1px dashed var(--border-color); border-radius: 8px;">
                    <p style="font-size: 13px;">No active alerts found.</p>
                </div>`;
            return;
        }

        listContainer.innerHTML = alerts.map(a => `
            <div class="card" style="margin-bottom: 10px; padding: 12px; border: 1px solid var(--border-color);">
                <div style="display: flex; justify-content: space-between; align-items: start;">
                    <div>
                        <strong style="font-size: 14px;">${a.asset}</strong> 
                        <span class="tf-badge" style="font-size: 10px;">${a.timeframe}</span><br>
                        <small style="color: var(--text-dim);">${a.alert_type.replace(/_/g, ' ')}</small>
                    </div>
                    <button onclick="deleteAlert(${a.id})" style="background:none; border:none; color:var(--danger); cursor:pointer; font-size: 12px;">Delete</button>
                </div>
            </div>
        `).join('');
    } catch (err) { console.error("Fetch Alerts Error:", err); }
}

async function deleteAlert(alertId) {
    if (!confirm("Delete this alert?")) return;
    const token = getToken();
    try {
        const response = await fetch(`${API_BASE_URL}/api/delete-alert`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ 'alert_id': alertId })
        });
        if (response.ok) fetchAndDisplayAlerts();
    } catch (err) { console.error("Delete Error:", err); }
}

// ==========================================================
// 5. INITIALIZATION & EVENTS
// ==========================================================

document.addEventListener('DOMContentLoaded', async () => {
    // A. Theme Logic
    const themeToggle = document.getElementById('themeToggle');
    const htmlTag = document.documentElement;
    const savedTheme = localStorage.getItem('theme') || 'dark';
    htmlTag.setAttribute('data-theme', savedTheme);
    if(themeToggle) themeToggle.innerText = savedTheme === 'dark' ? '🌓' : '☀️';

    if(themeToggle) {
        themeToggle.addEventListener('click', () => {
            const currentTheme = htmlTag.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            htmlTag.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            themeToggle.innerText = newTheme === 'dark' ? '🌓' : '☀️';
        });
    }

    // B. Mobile Menu & Overlay Initialization
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay';
    document.body.appendChild(overlay);

    if (menuToggle) {
        menuToggle.addEventListener('click', () => {
            sidebar.classList.toggle('active');
            overlay.classList.toggle('active');
        });
    }

    overlay.addEventListener('click', () => {
        sidebar.classList.remove('active');
        overlay.classList.remove('active');
    });

    // C. Auth & Data Fetching
    await checkSupabaseSession(); 
    updateAuthStatusUI();
    fetchMarketSignals('ALL');
    fetchAndDisplayAlerts();

    // D. Telegram Deep Link
    const telegramBtn = document.getElementById('connectTelegramBtn');
    const userId = getUserId();
    if (telegramBtn && userId) {
        const botUsername = 'Crypto1804_bot'; 
        telegramBtn.href = `https://t.me/${botUsername}?start=${userId}`;
    }

    // E. Create Alert Form Handling
    const createForm = document.getElementById('createAlertForm');
    if (createForm) {
        createForm.onsubmit = async (e) => {
            e.preventDefault();
            const token = getToken();
            if (!token) return alert("Please login first");

            const data = {
                asset: document.getElementById('alertAsset').value,
                timeframe: document.getElementById('alertTimeframe').value,
                alert_type: document.getElementById('alertType').value
            };

            const response = await fetch(`${API_BASE_URL}/api/create-alert`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify(data)
            });

            if (response.ok) {
                alert("✅ Alert Activated!");
                createForm.reset();
                fetchAndDisplayAlerts();
            }
        };
    }

    // F. Sidebar Filter Selection
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', function() {
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            this.classList.add('active');
            
            // Close mobile menu if open
            if (window.innerWidth <= 1024) {
                sidebar.classList.remove('active');
                overlay.classList.remove('active');
            }
            
            fetchMarketSignals(this.getAttribute('data-type'));
        });
    });

    // G. Live Refresh Loop (Matches selected category)
    setInterval(() => {
        const activeItem = document.querySelector('.nav-item.active');
        const type = activeItem ? activeItem.getAttribute('data-type') : 'ALL';
        fetchMarketSignals(type);
    }, 60000);
});