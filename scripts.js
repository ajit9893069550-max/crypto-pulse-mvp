// scripts.js

// --- GLOBAL CONFIGURATION (NEW ADDITION) ---
const API_BASE_URL = 'https://crypto-pulse-mvp-1.onrender.com';

// ⚠️ IMPORTANT: This MUST be the freshest token from your last successful POST /api/login in Postman.
const PLACEHOLDER_JWT_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhdCI6MTc2NTQ2MTA1MSwianRpIjoiMjc4YmY1YjktYzRjMy00ODFjLThkZjQtZjkzMTM1Mjg1NTc0IiwidHlwZSI6ImFjY2VzcyIsInN1YiI6ImYzYThkNzQ2LTUyOTUtNDc3My1iNjYzLTNmZjMzN2E3NDM3MiIsIm5iZiI6MTc2NTQ2MTA1MSwiY3NyZiI6ImZkMzdlZGYyLTkxODEtNDY3Ni1iMDFmLWY2MGQ3YjYwMjIzMCIsImV4cCI6MTc2NTU0NzQ1MX0.Gg5EDwOtHnH4PaPIj7iJLZHi_ovWvUE1ubJWeybcwpo'; 

// --- 1. CORE ALERT CREATION FUNCTION ---
async function createAlertFromDashboard() {
    // 1. --- GET INPUT VALUES ---
    const alertPhrase = document.getElementById('alertInput').value; 
    
    // FIX 4: Added the alertMessage element to the HTML, so this is now safe:
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
                'Authorization': `Bearer ${PLACEHOLDER_JWT_TOKEN}` 
            },
            body: JSON.stringify({
                'alert_phrase': alertPhrase
            })
        });

        // 3. --- HANDLE RESPONSE ---
        const result = await response.json();

        if (response.ok) {
            messageElement.textContent = `✅ Alert created successfully! Type: ${result.alert_type}`;
            messageElement.className = 'text-success';
            document.getElementById('alertInput').value = ''; 
            await fetchAndDisplayAlerts(); 
        } else {
            let errorMessage = result.error || 'Unknown API Error.';
            if (response.status === 401) {
                errorMessage = "Authentication failed. Please generate a new token and re-deploy.";
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
    // FIX 3: This ID now correctly matches the tbody ID in the corrected index.html
    const alertsList = document.getElementById('alertsList'); 
    alertsList.innerHTML = '<tr><td colspan="6">Loading alerts...</td></tr>'; // 6 columns now for the table structure
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/my-alerts`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${PLACEHOLDER_JWT_TOKEN}` 
            }
        });
        
        if (response.status === 401) {
             alertsList.innerHTML = '<tr><td colspan="6" class="text-danger">❌ Authentication Failed. Token is expired or invalid.</td></tr>';
             return;
        }

        if (!response.ok) {
            const errorResult = await response.json();
             alertsList.innerHTML = `<tr><td colspan="6" class="text-danger">❌ Failed to fetch alerts: ${errorResult.error || 'Server error'}</td></tr>`;
             return;
        }
        
        const alerts = await response.json();
        
        if (alerts.length === 0) {
            alertsList.innerHTML = '<tr><td colspan="6">No active alerts found. Create one above!</td></tr>';
            return;
        }

        alertsList.innerHTML = ''; // Clear 'Loading' message
        
        alerts.forEach(alert => {
            const row = alertsList.insertRow();
            // Note: Updated cell count to 6 based on index.html table headers
            row.insertCell(0).textContent = alert.alert_id || alert.id || 'N/A'; 
            row.insertCell(1).textContent = alert.asset || 'N/A';
            row.insertCell(2).textContent = alert.alert_type || 'N/A'; // Assuming a type field exists
            row.insertCell(3).textContent = alert.timeframe || 'N/A';
            row.insertCell(4).textContent = `${alert.operator} ${alert.target_value}`;
            
            // Status Cell (Assuming 'active' status for now)
            const statusCell = row.insertCell(5);
            statusCell.textContent = 'Active'; 
            statusCell.className = 'text-success';

            const deleteCell = row.insertCell(6); // This will add the 7th cell for the button
            const deleteButton = document.createElement('button');
            deleteButton.textContent = 'Delete';
            deleteButton.className = 'btn btn-sm btn-danger';
            deleteButton.onclick = () => deleteAlert(alert.alert_id || alert.id);
            deleteCell.appendChild(deleteButton);
        });

    } catch (error) {
        console.error('Error fetching alerts:', error);
        alertsList.innerHTML = '<tr><td colspan="6" class="text-danger">⚠️ Connection Error. The Web API is likely sleeping. Refresh in 30 seconds.</td></tr>';
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
            await fetchAndDisplayAlerts(); 
        } else {
            alert(`Error deleting alert: ${result.error || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Error deleting alert:', error);
        alert('Network error while attempting to delete alert.');
    }
}

// --- 4. SUGGESTION FUNCTION (To prevent ReferenceError from HTML onclick) ---
function useSuggestion(suggestion) {
    const alertInput = document.getElementById('alertInput');
    if (alertInput) {
        alertInput.value = suggestion;
    }
}

// --- 5. INITIALIZATION ---
// Run when the page loads
document.addEventListener('DOMContentLoaded', () => {
    // FIX 1: This now correctly targets the button by the ID we added to index.html
    const createButton = document.getElementById('createAlertButton');
    if (createButton) {
        createButton.addEventListener('click', createAlertFromDashboard);
    }
    
    // Load existing alerts on startup
    fetchAndDisplayAlerts();
});