// scripts.js

// --- GLOBAL CONFIGURATION ---
const API_BASE_URL = 'https://crypto-pulse-dashboard1.onrender.com'; 
const TOKEN_STORAGE_KEY = 'access_token';
const USER_ID_STORAGE_KEY = 'user_id'; 

// Supabase client instance will be initialized dynamically
let supabaseClient = null;


// ==========================================================
// CONFIGURATION & INITIALIZATION
// ==========================================================

/**
 * Step 1: Fetches configuration from the Flask backend.
 * @returns {Promise<Object>} Object containing Supabase URL and Key.
 */
async function fetchConfig() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/config`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const config = await response.json();
        
        if (!config.SUPABASE_URL || !config.SUPABASE_KEY) {
            console.error("Configuration missing required Supabase credentials.");
            throw new Error("Missing Supabase credentials in server configuration.");
        }
        return config;
    } catch (error) {
        console.error("Failed to fetch configuration from backend:", error);
        return { SUPABASE_URL: null, SUPABASE_KEY: null };
    }
}

/**
 * Step 2: Initializes the Supabase client once the config is available.
 */
async function initializeSupabase() {
    const config = await fetchConfig();
    
    if (config.SUPABASE_URL && config.SUPABASE_KEY && typeof supabase !== 'undefined') {
        try {
            // Initialize Supabase Client using the fetched environment variables
            supabaseClient = supabase.createClient(config.SUPABASE_URL, config.SUPABASE_KEY);
            console.log("Supabase client initialized successfully.");
        } catch (e) {
            console.error("Failed to create Supabase client:", e);
        }
    } else {
        console.error("Supabase SDK or configuration not available. OAuth will fail.");
    }
}


// ==========================================================
// AUTHENTICATION HELPER FUNCTIONS
// ==========================================================

function getToken() {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
}

function getUserId() {
    return localStorage.getItem(USER_ID_STORAGE_KEY);
}

/**
 * Saves both the access token and the user's Supabase UUID.
 */
function saveToken(token, userId = null) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
    if (userId) {
        localStorage.setItem(USER_ID_STORAGE_KEY, userId); 
    }
}

/**
 * Clears tokens and redirects, ensuring the authentication loop is broken.
 */
function logout() {
    // 1. Aggressively sign out from Supabase (to clear their cookies/session state)
    if (supabaseClient) {
        // Use an asynchronous call but don't wait for it to avoid blocking the redirect
        supabaseClient.auth.signOut({ scope: 'global' }); 
    }
    
    // 2. Clear local storage
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    localStorage.removeItem(USER_ID_STORAGE_KEY); 
    
    // 3. CRITICAL FIX: Ensure a clean redirect to login.html if on dashboard
    if (window.location.pathname.endsWith('index.html') || window.location.pathname === '/') {
        window.location.href = 'login.html';
    } else {
        location.reload(); 
    }
}

function updateAuthStatusUI() {
    const token = getToken();
    const authStatusLink = document.getElementById('authStatusLink');
    const greetingMessage = document.getElementById('greetingMessage');
    const alertCreationSection = document.getElementById('alertCreationSection');
    const noAlertsMessage = document.getElementById('noAlertsMessage');
    
    if (authStatusLink) {
        if (token) {
            authStatusLink.innerHTML = `<a href="#" onclick="logout()">Logout</a>`;
            if (greetingMessage) greetingMessage.textContent = 'Welcome Back!'; 
            if (alertCreationSection) alertCreationSection.style.display = 'block';
            if (noAlertsMessage) noAlertsMessage.style.display = 'none';
        } else {
            authStatusLink.innerHTML = `<a href="login.html">Login</a>`; 
            if (greetingMessage) greetingMessage.textContent = 'Please Log In';
            if (alertCreationSection) alertCreationSection.style.display = 'none';
            if (noAlertsMessage && (window.location.pathname.endsWith('index.html') || window.location.pathname === '/')) {
                noAlertsMessage.style.display = 'block';
            }
        }
    }
}


// ==========================================================
// A. AUTHENTICATION HANDLERS
// ==========================================================

/**
 * Handles Google OAuth login and registration.
 */
async function handleGoogleLogin() {
    const messageElement = document.getElementById('loginMessage');
    
    if (!supabaseClient) {
        if (messageElement) {
            messageElement.textContent = '❌ Supabase client not ready. Please try refreshing.';
            messageElement.className = 'text-danger';
        }
        return;
    }

    if (messageElement) {
        messageElement.textContent = 'Redirecting to Google...';
        messageElement.className = 'text-info';
    }

    try {
        const { data, error } = await supabaseClient.auth.signInWithOAuth({
            provider: 'google',
            options: {
                redirectTo: `${window.location.origin}/index.html` 
            }
        });

        if (error) {
            console.error('Google Sign-In Error:', error);
            if (messageElement) {
                messageElement.textContent = `❌ Google Sign-In Failed: ${error.message}`;
                messageElement.className = 'text-danger';
            }
        } else if (data && data.url) {
            window.location.href = data.url;
        }

    } catch (error) {
        console.error('Supabase Client Error:', error);
        if (messageElement) {
            messageElement.textContent = '⚠️ Failed to start Google login process.';
            messageElement.className = 'text-danger';
        }
    }
}


/**
 * 1. Handles traditional Email/Password Login.
 */
async function handleLogin() {
    const email = document.getElementById('loginEmail')?.value;
    const password = document.getElementById('loginPassword')?.value;
    const messageElement = document.getElementById('loginMessage');
    
    if (!email || !password) {
        if (messageElement) {
             messageElement.textContent = 'Please enter both email and password.';
             messageElement.className = 'text-danger';
        }
        return;
    }
    
    if (messageElement) {
        messageElement.textContent = 'Logging in...';
        messageElement.className = 'text-info';
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        const result = await response.json();

        if (response.ok) {
            // IMPORTANT: Assume the Flask backend returns both access_token and user_id here
            saveToken(result.access_token, result.user_id);
            if (messageElement) {
                messageElement.textContent = 'Login successful! Redirecting...';
                messageElement.className = 'text-success';
            }
            window.location.href = 'index.html'; 

        } else {
            let errorMessage = result.error || 'Invalid credentials';
            if (messageElement) {
                messageElement.textContent = `❌ Login Failed: ${errorMessage}`;
                messageElement.className = 'text-danger';
            }
        }

    } catch (error) {
        console.error('Network or Fetch Error:', error);
        if (messageElement) {
            messageElement.textContent = '⚠️ Failed to connect to the API.';
            messageElement.className = 'text-danger';
        }
    }
}


/**
 * 2. Handles Registration.
 */
async function handleRegistration() {
    const email = document.getElementById('registerEmail')?.value;
    const password = document.getElementById('registerPassword')?.value;
    const confirmPassword = document.getElementById('confirmPassword')?.value;
    const messageElement = document.getElementById('registerMessage');

    if (!email || !password || !confirmPassword) {
        if (messageElement) {
            messageElement.textContent = 'Please fill in all fields.';
            messageElement.className = 'text-danger';
        }
        return;
    }

    if (password !== confirmPassword) {
        if (messageElement) {
            messageElement.textContent = 'Passwords do not match.';
            messageElement.className = 'text-danger';
        }
        return;
    }
    
    if (messageElement) {
        messageElement.textContent = 'Registering...';
        messageElement.className = 'text-info';
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        const result = await response.json();

        if (response.ok) {
            if (messageElement) {
                messageElement.textContent = `✅ Registration Successful! Check email for confirmation. Redirecting to login...`;
                messageElement.className = 'text-success';
            }
            setTimeout(() => {
                window.location.href = 'login.html'; 
            }, 3000);

        } else {
            let errorMessage = result.error || 'Registration failed.';
            if (messageElement) {
                messageElement.textContent = `❌ Registration Failed: ${errorMessage}`;
                messageElement.className = 'text-danger';
            }
        }

    } catch (error) {
        console.error('Network or Fetch Error:', error);
        if (messageElement) {
            messageElement.textContent = '⚠️ Failed to connect to the API.';
            messageElement.className = 'text-danger';
        }
    }
}


// ==========================================================
// B. MARKET AND ALERT HANDLERS 
// ==========================================================

// --- 3. FETCH & DISPLAY SUPPORTED PAIRS (FOR SIDEBAR) ---
async function fetchAndDisplaySupportedPairs() {
    const headerElement = document.getElementById('sidebarHeader');
    const assetListElement = document.getElementById('live-asset-list');

    if (!headerElement || !assetListElement) return;

    try {
        const pairsResponse = await fetch(`${API_BASE_URL}/api/supported-pairs`);
        if (!pairsResponse.ok) throw new Error(`HTTP error! status: ${pairsResponse.status}`);
        const pairsData = await pairsResponse.json();
        const supportedPairs = pairsData.supported_pairs;
        
        // Fetch market summary (price and change)
        const summaryResponse = await fetch(`${API_BASE_URL}/api/market-summary`);
        const marketSummary = await summaryResponse.json();
        const marketDataMap = new Map();
        
        if (Array.isArray(marketSummary)) {
             marketSummary.forEach(item => {
                 marketDataMap.set(item.symbol, item);
             });
        }
        
        headerElement.textContent = `Supported Pairs (${supportedPairs.length})`;
        assetListElement.innerHTML = ''; 

        supportedPairs.forEach(symbol => {
            const data = marketDataMap.get(symbol);
            
            const price = data 
                ? data.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 }) 
                : '---';
                
            const changePercent = data 
                ? (data.change_percent / 100).toLocaleString(undefined, { style: 'percent', minimumFractionDigits: 2, maximumFractionDigits: 2 }) 
                : 'N/A';
                
            const changeClass = data ? (data.change_percent >= 0 ? 'positive' : 'negative') : '';

            const item = document.createElement('div');
            item.className = 'asset-item';
            
            item.innerHTML = `
                <span class="ticker">${symbol}</span>
                <span class="change ${changeClass}">${changePercent}</span> 
                <span class="price">${price}</span>
            `;
            assetListElement.appendChild(item);
        });

    } catch (error) {
        console.error("Failed to fetch market data:", error);
        headerElement.textContent = `Supported Pairs (Error)`;
        assetListElement.innerHTML = `<div style="padding: 10px; color: red; font-size: 12px;">Failed to load data. API Down?</div>`;
    }
}


// --- 4. CORE ALERT CREATION FUNCTION ---
async function createAlertFromDashboard() {
    const token = getToken();
    const userId = getUserId(); 
    if (!token || !userId) {
        alert("Authentication required. Please log in first.");
        return;
    }

    const alertPhrase = document.getElementById('alertInput').value; 
    const messageElement = document.getElementById('alertMessage'); 
    
    if (messageElement) {
        messageElement.textContent = 'Sending request...';
        messageElement.className = 'text-info';
    }

    if (!alertPhrase) {
        if (messageElement) {
            messageElement.textContent = 'Please enter an alert phrase.';
            messageElement.className = 'text-danger';
        }
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/create-alert`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}` 
            },
            body: JSON.stringify({
                'alert_phrase': alertPhrase,
                'user_id': userId 
            })
        });

        const result = await response.json();

        if (response.ok) {
            if (messageElement) {
                messageElement.textContent = `✅ Alert created successfully! Type: ${result.alert_type}`;
                messageElement.className = 'text-success';
            }
            document.getElementById('alertInput').value = ''; 
            await fetchAndDisplayAlerts(); 
        } else {
            let errorMessage = result.error || 'Unknown API Error.';
            if (response.status === 401 || response.status === 422) {
                errorMessage = "Authentication failed. Token is expired or invalid. Please re-login.";
                logout(); // Will redirect user to login.html
            } else if (result.details) {
                errorMessage += ` (Details: ${result.details})`;
            }
            if (messageElement) {
                messageElement.textContent = `❌ Error: ${errorMessage}`;
                messageElement.className = 'text-danger';
            }
        }

    } catch (error) {
        console.error('Network or Fetch Error:', error);
        if (messageElement) {
            messageElement.textContent = `⚠️ Failed to connect to the server. Is the Web API service running at ${API_BASE_URL}? (Error: ${error.message})`;
            messageElement.className = 'text-danger';
        }
    }
}

// --- 5. CORE ALERT FETCHING FUNCTION ---
async function fetchAndDisplayAlerts() {
    const token = getToken();
    const userId = getUserId(); 
    const alertsList = document.getElementById('alertsList'); 
    
    if (!alertsList) return;

    if (!token || !userId) {
        alertsList.innerHTML = '<tr><td colspan="5" class="text-danger">❌ Not Logged In. Log in to manage alerts.</td></tr>';
        return;
    }

    alertsList.innerHTML = '<tr><td colspan="5">Loading alerts...</td></tr>'; 
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/my-alerts`, { 
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}` 
            }
        });
        
        // CRITICAL FIX: Ensure clean logout and redirect on auth failure (401/422)
        if (response.status === 401 || response.status === 422) {
             alertsList.innerHTML = '<tr><td colspan="5" class="text-danger">❌ Authentication Failed. Token is expired or invalid. Please re-login.</td></tr>';
             localStorage.removeItem(TOKEN_STORAGE_KEY); // Explicitly remove bad token
             localStorage.removeItem(USER_ID_STORAGE_KEY);
             window.location.href = 'login.html'; // Force redirect to login page
             return; // Stop execution
        }

        if (!response.ok) {
            const errorResult = await response.json();
             alertsList.innerHTML = `<tr><td colspan="5" class="text-danger">❌ Failed to fetch alerts: ${errorResult.error || 'Server error'}</td></tr>`;
             return;
        }
        
        const alerts = await response.json();
        
        alertsList.innerHTML = '';
        
        if (alerts.length === 0) {
            alertsList.innerHTML = '<tr><td colspan="5">No active alerts found. Create one above!</td></tr>';
            return;
        }
        
        alerts.forEach(alert => {
            const row = alertsList.insertRow();
            let cellIndex = 0;

            row.insertCell(cellIndex++).textContent = alert.asset || 'N/A'; 
            row.insertCell(cellIndex++).textContent = alert.timeframe || 'N/A'; 

            let condition = 'N/A';
            if (alert.alert_type === 'PRICE_TARGET') {
                condition = `${alert.asset} ${alert.operator} ${alert.target_value}`;
            } else if (alert.alert_type === 'MA_CROSS') {
                const crossType = alert.params.condition === 'ABOVE' ? 'Golden Cross' : 'Death Cross';
                condition = `${crossType} on ${alert.asset} ${alert.timeframe}`;
            } else {
                condition = alert.alert_type;
            }
            row.insertCell(cellIndex++).textContent = condition; 
            
            const statusCell = row.insertCell(cellIndex++);
            statusCell.textContent = alert.status || 'Active'; 
            statusCell.className = alert.status === 'ACTIVE' ? 'text-success' : 'text-danger';

            const deleteCell = row.insertCell(cellIndex++); 
            const deleteButton = document.createElement('button');
            deleteButton.textContent = 'Delete';
            deleteButton.className = 'btn btn-sm btn-danger';
            deleteButton.onclick = () => deleteAlert(alert.id); 
            deleteCell.appendChild(deleteButton);
        });

    } catch (error) {
        console.error('Error fetching alerts:', error);
        alertsList.innerHTML = '<tr><td colspan="5" class="text-danger">⚠️ Connection Error. The API is likely sleeping.</td></tr>';
    }
}

// --- 6. DELETE ALERT FUNCTION ---
async function deleteAlert(alertId) {
    const token = getToken();
    const userId = getUserId(); 
    if (!token || !userId) {
        alert("Authentication required. Please log in first.");
        return;
    }

    if (!confirm(`Are you sure you want to delete Alert ID ${alertId}?`)) return;

    try {
        const response = await fetch(`${API_BASE_URL}/api/delete-alert`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}` 
            },
            body: JSON.stringify({ 
                'alert_id': alertId,
                'user_id': userId 
            })
        });

        const result = await response.json();

        if (response.ok) {
            alert(result.message);
            await fetchAndDisplayAlerts(); 
        } else {
            alert(`Error deleting alert: ${result.error || 'Unknown error'}`);
            console.error('Delete API Error:', result.error);
        }
    } catch (error) {
        console.error('Error deleting alert:', error);
        alert('Network error while attempting to delete alert.');
    }
}

// --- 7. SUGGESTION FUNCTION ---
function useSuggestion(suggestion) {
    const alertInput = document.getElementById('alertInput');
    if (alertInput) {
        alertInput.value = suggestion;
    }
}


// ==========================================================
// C. DOM CONTENT LOADED & EVENT LISTENERS
// ==========================================================

// Function to check for and process a Supabase session after redirect
// scripts.js (The checkSupabaseSession function)

async function checkSupabaseSession() {
    // ... (supabaseClient check and getSession call remains the same) ...
    
    try {
        console.log("--- DEBUG START: checkSupabaseSession ---");
        const { data: { session }, error } = await supabaseClient.auth.getSession();
        
        // ... (error handling remains the same) ...

        if (session) {
            saveToken(session.access_token, session.user.id); 
            console.log("✅ Supabase Session Found! Token and User ID saved.");
            
            // CRITICAL FIX: IF the URL has a hash (meaning it just came from OAuth), 
            // clear the hash AND force a clean redirect.
            if (window.location.hash) {
                console.log("Clearing URL hash and forcing clean index.html redirect.");
                
                // 1. Clear the history state
                window.history.replaceState(null, null, window.location.pathname);
                
                // 2. Force a clean page load without the hash to prevent the loop
                window.location.replace('index.html');
                return; // Stop execution here, the page is reloading
            }
            
            // If no hash, just update the UI (i.e., this is a regular page load)
            updateAuthStatusUI();
            fetchAndDisplayAlerts();
            
        } else {
             console.log("No Supabase session found in URL hash or storage.");
        }
        console.log("--- DEBUG END: checkSupabaseSession ---");
    } catch (e) {
        console.error("Error getting Supabase session:", e);
    }
}

// NOTE: You can remove this block from the original code now as the logic is inside the 'if (session)' block
//            if (window.location.pathname.endsWith('login.html') || window.location.pathname.endsWith('register.html') || window.location.pathname === '/') {
//                window.location.href = 'index.html';
//            } else {
//                updateAuthStatusUI();
//                fetchAndDisplayAlerts();
//            }
//            
//            // Clear the URL fragment (if the index.html is loaded directly with the hash)
//            if (window.location.hash) {
//                console.log("Clearing URL hash.");
//                window.history.replaceState(null, null, window.location.pathname);
//            }


document.addEventListener('DOMContentLoaded', async () => {
    // 1. First, initialize the Supabase client by fetching config from the backend
    await initializeSupabase(); 

    // 2. Process potential Supabase session (Crucial for OAuth redirect)
    await checkSupabaseSession(); 

    // 3. Update the UI to show Login or Logout link
    updateAuthStatusUI();
    
    // 4. Attach click listeners for login buttons (on login.html)
    const loginButton = document.getElementById('loginButton'); 
    if (loginButton) {
        loginButton.addEventListener('click', handleLogin);
    }
    
    const googleLoginButton = document.getElementById('googleLoginButton');
    if (googleLoginButton) {
        googleLoginButton.addEventListener('click', handleGoogleLogin);
    }
    
    // 5. Attach click listener to the create button (on index.html)
    const createButton = document.getElementById('createAlertButton');
    if (createButton) {
        createButton.addEventListener('click', createAlertFromDashboard);
    }
    
    // 6. Load existing alerts and supported pairs on startup (only if index.html is loaded)
    const alertsList = document.getElementById('alertsList');
    if (alertsList) {
        fetchAndDisplayAlerts();
        fetchAndDisplaySupportedPairs();
    }
    
    // 7. Attach listener for register button (on register.html - assumed to exist)
    const registerButton = document.querySelector('.register-btn');
    if (registerButton) { 
        registerButton.addEventListener('click', handleRegistration);
    }
});