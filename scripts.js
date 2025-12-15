// scripts.js

// --- GLOBAL CONFIGURATION ---
const API_BASE_URL = 'https://crypto-pulse-mvp-1.onrender.com';
const TOKEN_STORAGE_KEY = 'access_token';
const USER_ID_STORAGE_KEY = 'user_id'; // IMPORTANT: Store User ID separately
let supabaseClient = null;


// ==========================================================
// CONFIGURATION & INITIALIZATION
// ==========================================================

/**
 * Step 1: Fetches configuration from the Flask backend.
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

// **CRITICAL FIX 1: Save both the JWT token AND the User ID**
function saveSession(token, userId) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
    localStorage.setItem(USER_ID_STORAGE_KEY, userId);
}

// **CRITICAL FIX 2: Clear all session data**
function logout() {
    if (supabaseClient) {
        // Sign out of Supabase session (important for OAuth users)
        supabaseClient.auth.signOut(); 
    }
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    localStorage.removeItem(USER_ID_STORAGE_KEY); // Clear User ID
    window.location.href = 'login.html'; // Redirect to clear dashboard state
}

// **CRITICAL FIX 3: Dynamic UI update using User ID**
function updateAuthStatusUI() {
    const token = getToken();
    const userId = getUserId();
    const authStatusLink = document.getElementById('authStatusLink');
    const greetingMessage = document.getElementById('greetingMessage');
    const alertCreationSection = document.getElementById('alertCreationSection');
    const noAlertsMessage = document.getElementById('noAlertsMessage');
    
    if (authStatusLink) {
        if (token && userId) {
            authStatusLink.innerHTML = `<a href="#" onclick="logout()">Logout</a>`;
            
            // Personalize greeting with part of the UUID
            const shortId = userId.substring(0, 8); 
            if (greetingMessage) greetingMessage.textContent = `Welcome Back, User ${shortId}!`; 
            
            if (alertCreationSection) alertCreationSection.style.display = 'block';
            if (noAlertsMessage) noAlertsMessage.style.display = 'none';
        } else {
            authStatusLink.innerHTML = `<a href="login.html">Login</a>`; 
            if (greetingMessage) greetingMessage.textContent = 'Please Log In';
            if (alertCreationSection) alertCreationSection.style.display = 'none';
            if (noAlertsMessage) noAlertsMessage.style.display = 'block';
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

    // ... (rest of your handleGoogleLogin remains the same) ...
    if (messageElement) {
        messageElement.textContent = 'Redirecting to Google...';
        messageElement.className = 'text-info';
    }

    try {
        const { data, error } = await supabaseClient.auth.signInWithOAuth({
            provider: 'google',
            options: {
                // Ensure this is the correct public facing URL
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
            // Success: Redirect the user to the Google login screen
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
    
    // ... (Input validation logic remains the same) ...
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
            // **FIXED: Use saveSession to store both token and user_id**
            saveSession(result.access_token, result.user_id); 
            if (messageElement) {
                messageElement.textContent = 'Login successful! Redirecting...';
                messageElement.className = 'text-success';
            }
            window.location.href = 'index.html'; 

        } else {
            // ... (Error handling remains the same) ...
            let errorMessage = result.error || 'Invalid credentials';
            if (messageElement) {
                messageElement.textContent = `❌ Login Failed: ${errorMessage}`;
                messageElement.className = 'text-danger';
            }
        }

    } catch (error) {
        // ... (Network error handling remains the same) ...
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
    // ... (The entire handleRegistration function remains the same as it is correct) ...
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

// --- 3. FETCH & DISPLAY SUPPORTED PAIRS (Unchanged, relies only on API) ---
// --- 4. CORE ALERT CREATION FUNCTION (Unchanged, uses getToken()) ---
// --- 5. CORE ALERT FETCHING FUNCTION (Unchanged, uses getToken()) ---
// --- 6. DELETE ALERT FUNCTION (Unchanged, uses getToken()) ---
// --- 7. SUGGESTION FUNCTION (Unchanged) ---


// **NOTE: Keep the functions 3, 4, 5, 6, 7 from your original script here. They are correct.**


// ==========================================================
// C. DOM CONTENT LOADED & EVENT LISTENERS
// ==========================================================

/**
 * **CRITICAL FIX 4: Process Supabase session on redirect from OAuth.**
 * This is the heart of the fix for Google login.
 */
async function checkSupabaseSession() {
    // Only proceed if the client is ready
    if (!supabaseClient) {
        // This brief wait helps handle the race condition where DOMContentLoaded runs before initializeSupabase finishes
        await new Promise(resolve => setTimeout(resolve, 50)); 
        if (!supabaseClient) return; 
    }

    try {
        const { data: { session }, error } = await supabaseClient.auth.getSession();
        
        if (error) throw error;

        if (session) {
            console.log("Supabase Session detected. Processing token...");
            
            // 1. Save the new JWT token and User ID from Supabase session
            saveSession(session.access_token, session.user.id);
            
            // 2. Clear the URL fragment to hide the sensitive session data
            history.replaceState(null, '', window.location.pathname); 

            // 3. Redirect to the main dashboard if currently on the login page
            if (window.location.pathname.endsWith('login.html')) {
                window.location.href = 'index.html';
                return true; // Indicate session was processed and redirect occurred
            }
            
            // 4. Update UI and fetch data for index.html load
            updateAuthStatusUI();
            fetchAndDisplayAlerts();
            return true;
        }
    } catch (e) {
        console.error("Error getting Supabase session:", e);
    }
    return false;
}


document.addEventListener('DOMContentLoaded', async () => {
    // 1. First, initialize the Supabase client
    await initializeSupabase(); 

    // 2. Process potential Supabase session (This is the most critical step for OAuth)
    const sessionProcessed = await checkSupabaseSession(); 

    // **CRITICAL FIX 5: Only update UI and fetch data if we didn't just process a new session**
    // (This prevents redundant calls or flickering if the session was just set)
    if (!sessionProcessed) {
        updateAuthStatusUI();
    }
    
    // 3. Attach click listener to the Google login button (on login.html)
    const googleLoginButton = document.getElementById('googleLoginButton');
    if (googleLoginButton) {
        googleLoginButton.addEventListener('click', handleGoogleLogin);
    }
    
    // 4. Attach click listener to the create button (on index.html)
    const createButton = document.getElementById('createAlertButton');
    if (createButton) {
        createButton.addEventListener('click', createAlertFromDashboard);
    }
    
    // 5. Load existing alerts and supported pairs on startup (only if index.html is loaded)
    const alertsList = document.getElementById('alertsList');
    if (alertsList) {
        if (!sessionProcessed) {
             // If a session wasn't just processed and saved, we still need to fetch alerts
             // The call is already inside checkSupabaseSession if successful, but we call it here too
             // in case the user reloads or navigates directly with a stored token.
             fetchAndDisplayAlerts(); 
        }
        fetchAndDisplaySupportedPairs();
    }
    
    // 6. Attach listener for register button (on register.html)
    const registerButton = document.querySelector('.register-btn');
    if (registerButton && !registerButton.onclick) {
        registerButton.addEventListener('click', handleRegistration);
    }
});