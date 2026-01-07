/**
 * AUTH.JS - Handles User Identity, Configuration & Theme-Adaptive UI
 */

// 1. Global Keys
window.TOKEN_KEY = 'supabase_token';
window.USER_ID_KEY = 'user_id';
window.supabaseClient = null;

// 2. Helper Functions
function getToken() { return localStorage.getItem(window.TOKEN_KEY); }
function getUserId() { return localStorage.getItem(window.USER_ID_KEY); }

// 3. Initialize Connection (Run this on page load)
async function initAuth() {
    try {
        // Fetch config from backend
        const res = await fetch('/api/config');
        const cfg = await res.json();
        
        // 1. Setup Bot Username
        if (!window.BOT_USERNAME && cfg.BOT_USERNAME) {
            window.BOT_USERNAME = cfg.BOT_USERNAME;
        }

        // 2. Initialize Supabase
        if (cfg.SUPABASE_URL && typeof supabase !== 'undefined') {
            window.supabaseClient = supabase.createClient(cfg.SUPABASE_URL, cfg.SUPABASE_KEY);
        }

        // 3. LISTEN FOR AUTH CHANGES (Fixes Google Sign-In)
        if (window.supabaseClient) {
            // This listener automatically catches the Google Redirect Hash
            window.supabaseClient.auth.onAuthStateChange((event, session) => {
                if (event === 'SIGNED_IN' && session) {
                    console.log("✅ User Signed In via Google/Email");
                    localStorage.setItem(window.TOKEN_KEY, session.access_token);
                    localStorage.setItem(window.USER_ID_KEY, session.user.id);
                    updateAuthButton();
                    // Refresh alerts if the UI is ready
                    if (window.refreshAlerts) window.refreshAlerts();
                } else if (event === 'SIGNED_OUT') {
                    console.log("👋 User Signed Out");
                    localStorage.removeItem(window.TOKEN_KEY);
                    localStorage.removeItem(window.USER_ID_KEY);
                    updateAuthButton();
                }
            });

            // Also check current session immediately (for page refreshes)
            const { data: { session } } = await window.supabaseClient.auth.getSession();
            if (session) {
                localStorage.setItem(window.TOKEN_KEY, session.access_token);
                localStorage.setItem(window.USER_ID_KEY, session.user.id);
            }
        }
        
        // 4. Update UI
        updateAuthButton();
        return true;

    } catch (e) {
        console.error("Auth Init Failed:", e);
        return false;
    }
}

// 4. Update Header Button (Login vs Logout)
function updateAuthButton() {
    const token = getToken();
    const authLink = document.getElementById('authStatusLink');
    
    if (authLink) {
        // STYLE: Uses var(--text-main) so it changes color automatically with the theme
        const linkStyle = 'color: var(--text-main); text-decoration: none; font-weight: 600; font-size: 14px; margin-left: 15px; cursor: pointer;';
        
        if (token) {
            // LOGGED IN: Show Logout
            authLink.innerHTML = `<a onclick="logout()" style="${linkStyle}">Logout</a>`;
        } else {
            // LOGGED OUT: Show Login
            authLink.innerHTML = `<a href="login.html" style="${linkStyle}">Login</a>`;
        }
    }
}

// 5. Logout Handler
async function logout() {
    if (window.supabaseClient) {
        await window.supabaseClient.auth.signOut();
    }
    
    // Clear Local Storage
    localStorage.clear();
    
    // REDIRECT TO DASHBOARD
    window.location.href = '/';
}

// Initialize immediately
initAuth();