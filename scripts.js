// scripts.js

// --- GLOBAL CONFIGURATION ---
const API_BASE_URL = 'https://crypto-pulse-mvp-1.onrender.com';
const TOKEN_STORAGE_KEY = 'access_token';

// --- JWT HELPER FUNCTIONS ---

/**
 * Retrieves the JWT token from Local Storage.
 * @returns {string|null} The token or null if not found.
 */
function getToken() {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
}

/**
 * Saves the JWT token to Local Storage.
 * @param {string} token The JWT token to save.
 */
function saveToken(token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

/**
 * Removes the token and logs the user out.
 */
function logout() {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    // Reloads the page, which will trigger the UI update to show 'Login'
    location.reload(); 
}

/**
 * Checks for a token and updates the UI links (Hi Ajit vs. Login/Logout).
 */
function updateAuthStatusUI() {
    const token = getToken();
    const authStatusLink = document.getElementById('authStatusLink');
    const greetingMessage = document.getElementById('greetingMessage');
    const alertCreationSection = document.getElementById('alertCreationSection');
    
    if (authStatusLink) {
        if (token) {
            // User is logged in
            authStatusLink.innerHTML = `<a href="#" onclick="logout()">Logout</a>`;
            if (greetingMessage) greetingMessage.textContent = 'Welcome Back, Ajit!';
            if (alertCreationSection) alertCreationSection.style.display = 'block'; // Show creation section
        } else {
            // User is not logged in
            authStatusLink.innerHTML = `<a href="login.html">Login</a>`; 
            if (greetingMessage) greetingMessage.textContent = 'Please Log In';
            if (alertCreationSection) alertCreationSection.style.display = 'none'; // Hide creation section
        }
    }
}

// --- NEW: LOGIN FUNCTION (Used by login.html) ---
async function handleLogin() {
    const email = document.getElementById('loginEmail')?.value;
    const password = document.getElementById('loginPassword')?.value;
    const messageElement = document.getElementById('loginMessage');
    
    if (!email || !password) {
        if (messageElement) {
             messageElement.textContent = 'Please enter both email and password.';
             messageElement.className = 'text-warning';
        }
        return;
    }
    
    if (messageElement) messageElement.textContent = 'Logging in...';

    try {
        const response = await fetch(`${API_BASE_URL}/api/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        const result = await response.json();

        if (response.ok) {
            // SUCCESS! Save the token and redirect to the dashboard.
            saveToken(result.access_token);
            if (messageElement) {
                messageElement.textContent = 'Login successful! Redirecting...';
                messageElement.className = 'text-success';
            }
            
            // Redirect to your main dashboard page
            window.location.href = 'index.html'; 

        } else {
            // Login failed (e.g., incorrect credentials)
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


// --- 1. CORE ALERT CREATION FUNCTION ---
async function createAlertFromDashboard() {
    const token = getToken();
    if (!token) {
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
            messageElement.className = 'text-warning';
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
                'alert_phrase': alertPhrase
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
                logout(); // Log the user out if the token fails verification
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

// --- 2. CORE ALERT FETCHING FUNCTION ---
async function fetchAndDisplayAlerts() {
    const token = getToken();
    const alertsList = document.getElementById('alertsList'); 
    
    // Check if user is logged in before attempting fetch
    if (!token) {
        if (alertsList) alertsList.innerHTML = '<tr><td colspan="6" class="text-danger">❌ Not Logged In. Log in to manage alerts.</td></tr>';
        return;
    }

    if (alertsList) alertsList.innerHTML = '<tr><td colspan="6">Loading alerts...</td></tr>'; 
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/my-alerts`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}` 
            }
        });
        
        if (response.status === 401 || response.status === 422) {
             if (alertsList) alertsList.innerHTML = '<tr><td colspan="6" class="text-danger">❌ Authentication Failed. Token is expired or invalid. Please re-login.</td></tr>';
             logout(); // Token failed verification, force logout
             return;
        }

        if (!response.ok) {
            const errorResult = await response.json();
             if (alertsList) alertsList.innerHTML = `<tr><td colspan="6" class="text-danger">❌ Failed to fetch alerts: ${errorResult.error || 'Server error'}</td></tr>`;
             return;
        }
        
        const alerts = await response.json();
        
        if (alertsList) alertsList.innerHTML = ''; // Clear 'Loading' message
        
        if (alerts.length === 0) {
            if (alertsList) alertsList.innerHTML = '<tr><td colspan="6">No active alerts found. Create one above!</td></tr>';
            return;
        }
        
        // Loop through alerts and populate the table
        alerts.forEach(alert => {
            const row = alertsList.insertRow();
            
            row.insertCell(0).textContent = alert.id || 'N/A'; // ID
            row.insertCell(1).textContent = alert.asset || 'N/A'; // Asset
            row.insertCell(2).textContent = alert.timeframe || 'N/A'; // Timeframe

            // Condition Logic
            let condition = 'N/A';
            if (alert.alert_type === 'PRICE_TARGET') {
                condition = `${alert.asset} ${alert.operator} ${alert.target_value}`;
            } else if (alert.alert_type === 'GOLDEN_CROSS' || alert.alert_type === 'DEATH_CROSS') {
                condition = `${alert.alert_type} on ${alert.asset} ${alert.timeframe}`;
            } else {
                condition = alert.alert_type;
            }
            row.insertCell(3).textContent = condition; 
            
            // Status Cell
            const statusCell = row.insertCell(4);
            statusCell.textContent = alert.status || 'Active'; 
            statusCell.className = alert.status === 'ACTIVE' ? 'text-success' : 'text-danger';

            const deleteCell = row.insertCell(5); // Action column
            const deleteButton = document.createElement('button');
            deleteButton.textContent = 'Delete';
            deleteButton.className = 'btn btn-sm btn-danger';
            // Note: alert.id is safer than alert.alert_id based on previous issues
            deleteButton.onclick = () => deleteAlert(alert.id); 
            deleteCell.appendChild(deleteButton);
        });

    } catch (error) {
        console.error('Error fetching alerts:', error);
        if (alertsList) alertsList.innerHTML = '<tr><td colspan="6" class="text-danger">⚠️ Connection Error. The API is likely sleeping.</td></tr>';
    }
}

// --- 3. DELETE ALERT FUNCTION ---
async function deleteAlert(alertId) {
    const token = getToken();
    if (!token) {
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
            body: JSON.stringify({ 'alert_id': alertId })
        });

        const result = await response.json();

        if (response.ok) {
            alert(result.message);
            await fetchAndDisplayAlerts(); 
        } else {
            alert(`Error deleting alert: ${result.error || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Error deleting alert:', error);
        alert('Network error while attempting to delete alert.');
    }
}

// --- 4. SUGGESTION FUNCTION ---
function useSuggestion(suggestion) {
    const alertInput = document.getElementById('alertInput');
    if (alertInput) {
        alertInput.value = suggestion;
    }
}

// --- 5. INITIALIZATION ---
// Run when the page loads
document.addEventListener('DOMContentLoaded', () => {
    // 1. Update the UI to show Login or Logout link
    updateAuthStatusUI();
    
    // 2. Attach click listener to the create button
    const createButton = document.getElementById('createAlertButton');
    if (createButton) {
        createButton.addEventListener('click', createAlertFromDashboard);
    }
    
    // 3. Load existing alerts on startup (only if index.html is loaded)
    const alertsList = document.getElementById('alertsList');
    if (alertsList) {
        fetchAndDisplayAlerts();
    }
    
    // 4. If we are on the login page, we might want to attach event listeners 
    //    if the button wasn't using onclick=""
    const loginButton = document.querySelector('.login-btn');
    if (loginButton && !loginButton.onclick) {
        loginButton.addEventListener('click', handleLogin);
    }
});