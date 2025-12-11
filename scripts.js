// scripts.js

// --- GLOBAL CONFIGURATION (NEW ADDITION) ---
const API_BASE_URL = 'https://crypto-pulse-mvp-1.onrender.com';
const userId = 'f3a8d746-5295-4773-b663-3ff337a74372'; // <--- MUST MATCH THE ID BELOW

// --- 1. CORE ALERT CREATION FUNCTION ---
async function createAlertFromDashboard() {
    // 1. --- GET INPUT VALUES ---
    const alertPhrase = document.getElementById('alertInput').value; 
    
    // 2. --- USER IDENTIFICATION (CRITICAL: USE UUID) ---
    // NOTE: In a real app, this MUST come from secure session/auth storage.
    // Ensure this userId is linked to your Telegram chat_id via /link command.
    // const userId is defined globally above

    if (!alertPhrase) {
        alert('Please type the alert you want before clicking Create Alert.');
        return;
    }

    try {
        // 3. --- SEND POST REQUEST TO LIVE RENDER API ---
        const response = await fetch(`${API_BASE_URL}/api/create-alert`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json' 
            },
            body: JSON.stringify({ 
                user_id: userId,
                alert_phrase: alertPhrase 
            }),
        });

        const result = await response.json();

        // 4. --- HANDLE API RESPONSE ---
        if (response.status === 201) {
            alert(`✅ Alert Created! Type: ${result.alert_type}.`);
            document.getElementById('alertInput').value = ''; 
            // Refresh the list immediately after successful creation
            fetchMyAlerts(); 
        } else {
            alert(`❌ ERROR: ${result.error}\nDetails: ${result.details || 'Check the API logs.'}`);
        }
    } catch (error) {
        console.error('Network or server error:', error);
        alert('⚠️ Failed to connect to the live Render API. Check your internet connection.');
    }
}


// --- 2. LIVE PRICE FETCHING (MOCK/EXAMPLE) ---

function fetchAndDisplayLivePrices() {
    // ... (rest of the function remains the same)
    const ethPrice = (3100 + Math.random() * 5 - 2.5).toFixed(2);
    const btcPrice = (102300 + Math.random() * 50 - 25).toFixed(2);

    const ethPriceEl = document.getElementById('eth-price');
    const btcPriceEl = document.getElementById('btc-price');

    if (ethPriceEl) ethPriceEl.textContent = btcPrice; // BTC is usually the larger number
    if (btcPriceEl) btcPriceEl.textContent = ethPrice; // ETH is usually the smaller number
}


// --- 3. ALERT MANAGEMENT (UPDATED API URL) ---

// const userId is defined globally above

async function fetchMyAlerts() {
    const alertsTableBody = document.getElementById('alertsTableBody');
    if (!alertsTableBody) return; 

    // Clear previous results
    alertsTableBody.innerHTML = '<tr><td colspan="7">Fetching active alerts...</td></tr>';
    
    try {
        // UPDATED: Using API_BASE_URL constant
        const response = await fetch(`${API_BASE_URL}/api/my-alerts/${userId}`);
        const alerts = await response.json();

        alertsTableBody.innerHTML = ''; 

        if (alerts.length === 0) {
            alertsTableBody.innerHTML = '<tr><td colspan="7">You have no active alerts. Create a new one!</td></tr>';
            return;
        }

        alerts.forEach(alert => {
            const row = alertsTableBody.insertRow();
            
            const params = alert.params || {};
            const conditionDisplay = alert.condition_text || params.condition || 'N/A';
            
            row.insertCell(0).textContent = alert.id;
            row.insertCell(1).textContent = alert.asset;
            row.insertCell(2).textContent = alert.timeframe;
            row.insertCell(3).textContent = alert.alert_type.replace('_', ' ');
            row.insertCell(4).textContent = conditionDisplay;
            row.insertCell(5).textContent = alert.status;
            
            const actionCell = row.insertCell(6);
            const deleteButton = document.createElement('button');
            deleteButton.textContent = '❌ Delete';
            deleteButton.className = 'delete-btn';
            deleteButton.onclick = () => deleteAlert(alert.id);
            actionCell.appendChild(deleteButton);
        });

    } catch (error) {
        console.error('Error fetching alerts:', error);
        alertsTableBody.innerHTML = `<tr><td colspan="7" style="color:red;">Error loading alerts: ${error.message}. Is the Render API running?</td></tr>`;
    }
}

async function deleteAlert(alertId) {
    if (!confirm(`Are you sure you want to delete Alert ID ${alertId}?`)) {
        return;
    }

    try {
        // UPDATED: Using API_BASE_URL constant
        const response = await fetch(`${API_BASE_URL}/api/delete-alert`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ alert_id: alertId }),
        });

        const result = await response.json();

        if (response.ok) {
            alert(`✅ Alert ID ${alertId} successfully deleted.`);
            fetchMyAlerts(); 
        } else {
            alert(`❌ ERROR deleting alert: ${result.error || 'Check API logs.'}`);
        }
    } catch (error) {
        console.error('Network or server error during deletion:', error);
        alert('⚠️ Failed to connect to the deletion server.');
    }
}


// --- 4. SUGGESTION INPUT LOGIC ---

function useSuggestion(suggestionText) {
    const alertInput = document.getElementById('alertInput');
    alertInput.value = suggestionText;
    alertInput.focus();
}


// --- 5. INITIALIZATION ---

document.addEventListener('DOMContentLoaded', () => {
    // 1. Price fetching initialization
    fetchAndDisplayLivePrices();
    setInterval(fetchAndDisplayLivePrices, 5000);
    
    // 2. Alert fetching initialization
    fetchMyAlerts(); 
    
    // Add event listener to the "Refresh List" button if it exists
    const refreshButton = document.getElementById('refreshAlertsList');
    if (refreshButton) {
        refreshButton.addEventListener('click', fetchMyAlerts);
    }
});