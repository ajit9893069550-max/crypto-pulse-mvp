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
    // After logging out, redirect the user to a login page
    // For now, we'll just reload the current page.
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
    
    if (token) {
        // User is logged in
        authStatusLink.innerHTML = `<a href="#" onclick="logout()">Logout</a>`;
        greetingMessage.textContent = 'Welcome Back!';
        alertCreationSection.style.display = 'block'; // Show creation section
    } else {
        // User is not logged in
        authStatusLink.innerHTML = `<a href="login.html">Login</a>`; 
        greetingMessage.textContent = 'Please Log In';
        alertCreationSection.style.display = 'none'; // Hide creation section
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
    
    messageElement.textContent = 'Sending request...';
    messageElement.className = 'text-info';

    if (!alertPhrase) {
        messageElement.textContent = 'Please enter an alert phrase.';
        messageElement.className = 'text-warning';
        return;
    }

    try {
        // Use the dynamic token from getToken()
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
            messageElement.textContent = `✅ Alert created successfully! Type: ${result.alert_type}`;
            messageElement.className = 'text-success';
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
            messageElement.textContent = `❌ Error: ${errorMessage}`;
            messageElement.className = 'text-danger';
        }

    } catch (error) {
        console.error('Network or Fetch Error:', error);
        messageElement.textContent = `⚠️ Failed to connect to the server. Is the Web API service running at ${API_BASE_URL}? (Error: ${error.message})`;
        messageElement.className = 'text-danger';
    }
}

// --- 2. CORE ALERT FETCHING FUNCTION ---
async function fetchAndDisplayAlerts() {
    const token = getToken();
    const alertsList = document.getElementById('alertsList'); 
    
    // Check if user is logged in before attempting fetch
    if (!token) {
        alertsList.innerHTML = '<tr><td colspan="6" class="text-danger">❌ Not Logged In. Log in to manage alerts.</td></tr>';
        return;
    }

    alertsList.innerHTML = '<tr><td colspan="6">Loading alerts...</td></tr>'; 
    
    try {
        // Use the dynamic token from getToken()
        const response = await fetch(`${API_BASE_URL}/api/my-alerts`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}` 
            }
        });
        
        if (response.status === 401 || response.status === 422) {
             alertsList.innerHTML = '<tr><td colspan="6" class="text-danger">❌ Authentication Failed. Token is expired or invalid. Please re-login.</td></tr>';
             logout(); // Token failed verification, force logout
             return;
        }

        if (!response.ok) {
            const errorResult = await response.json();
             alertsList.innerHTML = `<tr><td colspan="6" class="text-danger">❌ Failed to fetch alerts: ${errorResult.error || 'Server error'}</td></tr>`;
             return;
        }
        
        const alerts = await response.json();
        
        // ... (Alert display logic remains the same for brevity) ...

        alertsList.innerHTML = ''; // Clear 'Loading' message
        
        if (alerts.length === 0) {
            alertsList.innerHTML = '<tr><td colspan="6">No active alerts found. Create one above!</td></tr>';
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
            deleteButton.onclick = () => deleteAlert(alert.id);
            deleteCell.appendChild(deleteButton);
        });

    } catch (error) {
        console.error('Error fetching alerts:', error);
        alertsList.innerHTML = '<tr><td colspan="6" class="text-danger">⚠️ Connection Error. Check your browser console.</td></tr>';
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
    
    // 3. Load existing alerts on startup
    fetchAndDisplayAlerts();
});