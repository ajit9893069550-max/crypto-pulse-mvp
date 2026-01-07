/**
 * AUTH.JS - Handles User Identity & Configuration
 */

// 1. Global Config (Available to all files)
// Detects if running locally or on Render
window.API_BASE_URL = window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1') 
    ? 'http://127.0.0.1:5001' 
    : window.location.origin;

window.TOKEN_KEY = 'supabase_token';
window.USER_ID_KEY = 'user_id';
window.supabaseClient = null;

// 2. Helper Functions
function getToken() { return localStorage.getItem(window.TOKEN_KEY); }
function getUserId() { return localStorage.getItem(window.USER_ID_KEY); }

// 3. Initialize Connection (Run this on page load)
async function initAuth() {
    try {
        const res = await fetch(`${window.API_BASE_URL}/api/config`);
        const cfg = await res.json();
        
        // Save the Bot Username for UI.js to use later
        if (cfg.BOT_USERNAME) {
            window.BOT_USERNAME = cfg.BOT_USERNAME;
        }

        if (cfg.SUPABASE_URL && typeof supabase !== 'undefined') {
            window.supabaseClient = supabase.createClient(cfg.SUPABASE_URL, cfg.SUPABASE_KEY);
        }

        // Check for active session
        if (window.supabaseClient) {
            const { data: { session } } = await window.supabaseClient.auth.getSession();
            if (session) {
                localStorage.setItem(window.TOKEN_KEY, session.access_token);
                localStorage.setItem(window.USER_ID_KEY, session.user.id);
            }
        }
        updateAuthButton();
        return true;
    } catch (e) {
        console.error("Auth Init Failed:", e);
        return false;
    }
}

function updateAuthButton() {
    const token = getToken();
    const authLink = document.getElementById('authStatusLink');
    if (authLink) {
        authLink.innerHTML = token 
            ? `<a href="#" onclick="logout()" class="nav-link">Logout</a>` 
            : `<a href="login.html" class="nav-link">Login</a>`;
    }
}

function logout() {
    localStorage.clear();
    window.location.href = 'login.html';
}