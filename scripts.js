// scripts.js

// --- GLOBAL CONFIGURATION (NEW ADDITION) ---
// NOTE: Ensure this URL points to your Render Web Service (web_api.py).
// The URL should be: https://YOUR-WEB-SERVICE-NAME.onrender.com
const API_BASE_URL = 'https://crypto-pulse-mvp-1.onrender.com';

// ⚠️ WARNING: These are placeholders until proper Login is implemented.
const userId = 'f3a8d746-5295-4773-b663-3ff337a74372'; 
const PLACEHOLDER_JWT_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhdCI6MTc2NTQ0MjA4NywianRpIjoiN2Y1YWNhM2YtMjk3Mi00N2IwLTllMzUtZGZmOWFlYWYyMzhhIiwidHlwZSI6ImFjY2VzcyIsInN1YiI6ImYzYThkNzQ2LTUyOTUtNDc3My1iNjYzLTNmZjMzN2E3NDM3MiIsIm5iZiI6MTc2NTQ0MjA4NywiY3NyZiI6IjJjYTI5NzlmLTY4YWQtNDZlMS1hZGIwLWE3MmI5YjI0MDhjNiIsImV4cCI6MTc2NTUyODQ4N30.5SnXXufA50GfTxBYCDqHPH3tPcUnMuYisQImoORbgU8'; // This is a mock/temporary JWT.

// --- 1. CORE ALERT CREATION FUNCTION ---
async function createAlertFromDashboard() {
    // 1. --- GET INPUT VALUES ---
    const alertPhrase = document.getElementById('alertInput').value; 
    const messageElement = document.getElementById('alertMessage');
    
    // Clear previous message
    messageElement.textContent = 'Sending request...';
    messageElement.className = 'text-info';

    if (!alertPhrase) {
        messageElement.textContent = 'Please enter an alert phrase.';
        messageElement.className = 'text-warning';
        return;
    }

    try {
        // 2. --- MAKE API CALL ---
        const response = await fetch(`${API_BASE_URL}/api/create-alert`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                // IMPORTANT: Pass the JWT for the protected route
                'Authorization': `Bearer ${PLACEHOLDER_JWT_TOKEN}` 
            },
            body: JSON.stringify({
                // Note: user_id is NOT needed here anymore, it's pulled from the JWT on the server
                'alert_phrase': alertPhrase
            })
        });

        // 3. --- HANDLE RESPONSE ---
        const result = await response.json();

        if (response.ok) {
            // Success (201 Created)
            messageElement.textContent = `✅ Alert created successfully! Type: ${result.alert_type}`;
            messageElement.className = 'text-success';
            // Clear the input and reload alerts list
            document.getElementById('alertInput').value = ''; 
            await fetchAndDisplayAlerts(); 
        } else {
            // API returned an error (400, 500, etc.)
            let errorMessage = result.error || 'Unknown API Error.';
            if (response.status === 401) {
                errorMessage = "Authentication failed. Please log in again.";
            } else if (result.details) {
                errorMessage += ` (Details: ${result.details})`;
            }
            messageElement.textContent = `❌ Error: ${errorMessage}`;
            messageElement.className = 'text-danger';
        }

    } catch (error) {
        // Network or connection error (e.g., API is offline/asleep)
        console.error('Network or Fetch Error:', error);
        
        // This is the specific error when the Render service is sleeping
        messageElement.textContent = `⚠️ Failed to connect to the alert creation server. Is the Web API service running at ${API_BASE_URL}? (Error: ${error.message})`;
        messageElement.className = 'text-danger';
    }
}

// --- 2. CORE ALERT FETCHING FUNCTION ---
async function fetchAndDisplayAlerts() {
    const alertsList = document.getElementById('alertsList');
    alertsList.innerHTML = '<tr><td colspan="4">Loading alerts...</td></tr>';
    
    try {
        // Fetch alerts for the hardcoded user ID
        const response = await fetch(`${API_BASE_URL}/api/my-alerts`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                // Pass the JWT for the protected route
                'Authorization': `Bearer ${PLACEHOLDER_JWT_TOKEN}` 
            }
        });
        
        // Handle token expiration/bad token first
        if (response.status === 401) {
             alertsList.innerHTML = '<tr><td colspan="4" class="text-danger">❌ Authentication Failed. Please Log In.</td></tr>';
             return;
        }

        if (!response.ok) {
            const errorResult = await response.json();
             alertsList.innerHTML = `<tr><td colspan="4" class="text-danger">❌ Failed to fetch alerts: ${errorResult.error || 'Server error'}</td></tr>`;
             return;
        }
        
        const alerts = await response.json();
        
        if (alerts.length === 0) {
            alertsList.innerHTML = '<tr><td colspan="4">No active alerts found. Create one above!</td></tr>';
            return;
        }

        alertsList.innerHTML = ''; // Clear 'Loading' message
        
        alerts.forEach(alert => {
            const row = alertsList.insertRow();
            // Use .id if your database returns a field named 'id'
            row.insertCell(0).textContent = alert.alert_id || alert.id || 'N/A'; 
            row.insertCell(1).textContent = `${alert.asset} ${alert.operator} ${alert.target_value}`;
            row.insertCell(2).textContent = alert.created_at ? new Date(alert.created_at).toLocaleString() : 'N/A';
            
            const deleteCell = row.insertCell(3);
            const deleteButton = document.createElement('button');
            deleteButton.textContent = 'Delete';
            deleteButton.className = 'btn btn-sm btn-danger';
            deleteButton.onclick = () => deleteAlert(alert.alert_id || alert.id);
            deleteCell.appendChild(deleteButton);
        });

    } catch (error) {
        console.error('Error fetching alerts:', error);
        alertsList.innerHTML = '<tr><td colspan="4" class="text-danger">⚠️ Connection Error. The Web API is likely sleeping. Refresh in 30 seconds.</td></tr>';
    }
}

// --- 3. DELETE ALERT FUNCTION ---
async function deleteAlert(alertId) {
    if (!confirm(`Are you sure you want to delete Alert ID ${alertId}?`)) return;

    try {
        const response = await fetch(`${API_BASE_URL}/api/delete-alert`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${PLACEHOLDER_JWT_TOKEN}` 
            },
            body: JSON.stringify({ 'alert_id': alertId })
        });

        const result = await response.json();

        if (response.ok) {
            alert(result.message);
            await fetchAndDisplayAlerts(); // Refresh the list
        } else {
            alert(`Error deleting alert: ${result.error || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Error deleting alert:', error);
        alert('Network error while attempting to delete alert.');
    }
}

// --- 4. INITIALIZATION ---
// Run when the page loads
document.addEventListener('DOMContentLoaded', () => {
    // Add event listener to the create button
    const createButton = document.getElementById('createAlertButton');
    if (createButton) {
        createButton.addEventListener('click', createAlertFromDashboard);
    }
    
    // Load existing alerts on startup
    fetchAndDisplayAlerts();
});