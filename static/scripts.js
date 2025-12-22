/**
 * CryptoPulse Scanner - Dashboard Logic
 * Optimized for: JWT Auth, Google OAuth, Mobile Responsiveness, and Real-time Updates
 */

// --- GLOBAL CONFIGURATION ---
const API_BASE_URL = window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1') 
    ? 'http://127.0.0.1:5001' 
    : window.location.origin;

const TOKEN_STORAGE_KEY = 'supabase_token'; 
const USER_ID_STORAGE_KEY = 'user_id'; 
let supabaseClient = null;

// ==========================================================
// 1. INITIALIZATION & AUTHENTICATION
// ==========================================================

async function fetchConfig() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/config`);
        return await response.json();
    } catch (error) {
        console.error("Config fetch failed:", error);
        return { SUPABASE_URL: null, SUPABASE_KEY: null };
    }
}

async function initializeSupabase() {
    const config = await fetchConfig();
    if (config.SUPABASE_URL && config.SUPABASE_KEY && typeof supabase !== 'undefined') {
        try {
            supabaseClient = supabase.createClient(config.SUPABASE_URL, config.SUPABASE_KEY);
            return true;
        } catch (e) { console.error("Supabase init failed:", e); }
    }
    return false;
}

function getToken() { return localStorage.getItem(TOKEN_STORAGE_KEY); }
function getUserId() { return localStorage.getItem(USER_ID_STORAGE_KEY); }

function logout() {
    localStorage.clear();
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
    const initialized = await initializeSupabase();
    if (!initialized) return null;

    // 1. Check for standard active session
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (session) {
        localStorage.setItem(TOKEN_STORAGE_KEY, session.access_token);
        localStorage.setItem(USER_ID_STORAGE_KEY, session.user.id);
        return session;
    } 

    // 2. Handle token from Google OAuth fragment
    const token = getToken();
    if (token) {
        const { data } = await supabaseClient.auth.setSession({
            access_token: token,
            refresh_token: localStorage.getItem('supabase_refresh_token') || ''
        });
        if (data.user) {
            localStorage.setItem(USER_ID_STORAGE_KEY, data.user.id);
            return { access_token: token, user: data.user };
        }
    }
    return null;
}

// ==========================================================
// 2. DATA DISPLAY (SIGNALS & ALERTS)
// ==========================================================

async function fetchMarketSignals(type = 'ALL') {
    const scanList = document.getElementById('marketScansList');
    if (!scanList) return;

    try {
        const endpoint = type === 'ALL' ? '/api/signals' : `/api/signals?type=${type}`;
        const response = await fetch(`${API_BASE_URL}${endpoint}`);
        const scans = await response.json();

        if (!scans || scans.length === 0) {
            scanList.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:20px;">No signals available.</td></tr>`;
            return;
        }

        scanList.innerHTML = scans.map(s => {
            const signalTime = new Date(s.created_at || s.detected_at);
            const now = new Date();
            const diffInMinutes = Math.abs(now - signalTime) / (1000 * 60);
            
            // Logic: NEW badge based on timeframe
            let isNew = false;
            if (s.timeframe === '15m' && diffInMinutes < 15) isNew = true;
            else if (s.timeframe === '1h' && diffInMinutes < 60) isNew = true;
            else if (s.timeframe === '4h' && diffInMinutes < 240) isNew = true;
            
            const newBadge = isNew ? '<span class="new-tag">NEW</span>' : '';
            return `
                <tr>
                    <td class="asset-cell">${s.asset.replace('/USDT', '')} ${newBadge}</td>
                    <td><span class="tf-badge tf-${s.timeframe}">${s.timeframe}</span></td>
                    <td class="${s.signal_type.includes('BULL') || s.signal_type.includes('OVERSOLD') ? 'text-success' : 'text-danger'}">
                        ${s.signal_type.replace(/_/g, ' ')}
                    </td>
                    <td style="color:var(--text-dim); font-size: 0.85em;">${signalTime.toLocaleString('en-IN')}</td>
                </tr>`;
        }).join('');
    } catch (err) { console.error("Signals Error:", err); }
}

async function fetchAndDisplayAlerts() {
    const listContainer = document.getElementById('myAlertsList');
    const telegramSection = document.getElementById('telegramLinkSection');
    const token = getToken();
    const userId = getUserId();
    if (!listContainer || !token) return;

    try {
        // Sync Telegram status using Service Role permissions from Backend
        if (supabaseClient && userId) {
            const { data: profile } = await supabaseClient.from('users').select('telegram_chat_id').eq('user_uuid', userId).maybeSingle();
            if (profile?.telegram_chat_id) {
                telegramSection.innerHTML = `<div class="linked-badge" style="background: rgba(0, 255, 136, 0.1); padding: 12px; border-radius: 8px; border: 1px solid var(--accent-green); color: var(--accent-green); font-size: 13px; font-weight: bold;">✅ Telegram Linked</div>`;
            }
        }

        const response = await fetch(`${API_BASE_URL}/api/my-alerts`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const alerts = await response.json();

        if (!alerts || alerts.length === 0 || alerts.error) {
            listContainer.innerHTML = `<p style="text-align:center; color:var(--text-dim);">No active alerts found.</p>`;
            return;
        }

        listContainer.innerHTML = alerts.map(a => `
            <div class="card alert-item" style="margin-bottom: 10px; padding: 12px;">
                <div style="display: flex; justify-content: space-between; align-items:center;">
                    <div>
                        <strong>${a.asset}</strong> <span class="tf-badge tf-${a.timeframe}">${a.timeframe}</span><br>
                        <small style="color: var(--text-dim);">${a.alert_type.replace(/_/g, ' ')}</small>
                    </div>
                    <button onclick="deleteAlert(${a.id})" class="text-danger" style="background:none; border:none; cursor:pointer;">Delete</button>
                </div>
            </div>`).join('');
    } catch (err) { console.error("Alerts Fetch Error:", err); }
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
// 3. EVENT HANDLERS & UI LOGIC
// ==========================================================

document.addEventListener('DOMContentLoaded', async () => {
    // Initialization
    await checkSupabaseSession(); 
    updateAuthStatusUI();
    fetchMarketSignals('ALL');
    fetchAndDisplayAlerts();

    // Fix for the mobile hamburger menu (3 dots)
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.querySelector('.sidebar');

    if (menuToggle && sidebar) {
        menuToggle.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevents click from bubbling to background layers
            sidebar.classList.toggle('active');
        });

        // Close sidebar when clicking outside of it
        document.addEventListener('click', (e) => {
            if (sidebar.classList.contains('active') && !sidebar.contains(e.target) && e.target !== menuToggle) {
                sidebar.classList.remove('active');
            }
        });
    }

    // Set Telegram deep link
    const telegramBtn = document.getElementById('connectTelegramBtn');
    if (telegramBtn && getUserId()) {
        telegramBtn.href = `https://t.me/Crypto1804_bot?start=${getUserId()}`;
    }

    // Create Alert Form Logic
    const createForm = document.getElementById('createAlertForm');
    if (createForm) {
        createForm.onsubmit = async (e) => {
            e.preventDefault();
            const statusDiv = document.getElementById('createAlertStatus');
            statusDiv.innerText = "⏳ Activating...";
            
            const payload = {
                asset: document.getElementById('alertAsset').value,
                timeframe: document.getElementById('alertTimeframe').value,
                signal_type: document.getElementById('alertType').value
            };

            const response = await fetch(`${API_BASE_URL}/api/create-alert`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${getToken()}` },
                body: JSON.stringify(payload)
            });

            const result = await response.json();
            if (response.status === 429) {
                statusDiv.innerHTML = `<span class="text-danger">${result.message}</span>`;
            } else if (response.ok) {
                statusDiv.innerHTML = `<span class="text-success">✅ Alert Active!</span>`;
                fetchAndDisplayAlerts();
                createForm.reset();
                setTimeout(() => { statusDiv.innerText = ""; }, 3000);
            }
        };
    }

    // Sidebar Category Filter Logic
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', function() {
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            this.classList.add('active');
            const title = document.getElementById('currentCategoryTitle');
            if (title) title.innerText = this.innerText;
            
            fetchMarketSignals(this.getAttribute('data-type'));
            
            // Auto-close sidebar on mobile after selecting a category
            if (window.innerWidth <= 1024 && sidebar.classList.contains('active')) {
                sidebar.classList.remove('active');
            }
        });
    });

    // Theme Toggle Support
    const themeBtn = document.getElementById('themeToggle');
    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            const html = document.documentElement;
            const current = html.getAttribute('data-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
            themeBtn.innerText = next === 'dark' ? '🌓' : '☀️';
        });
    }

    // Auto-refresh signals every 60 seconds
    setInterval(() => {
        const active = document.querySelector('.nav-item.active');
        fetchMarketSignals(active ? active.getAttribute('data-type') : 'ALL');
    }, 60000);
});