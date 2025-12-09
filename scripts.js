// scripts.js

// --- 1. CORE ALERT CREATION FUNCTION ---
async function createAlertFromDashboard() {
    // 1. --- GET INPUT VALUES ---
    const alertPhrase = document.getElementById('alertInput').value; 
    
    // 2. --- USER IDENTIFICATION (CRITICAL: USE UUID) ---
    // NOTE: In a real app, this MUST come from secure session/auth storage.
    // For testing, use a UUID that is successfully linked to your Telegram chat_id via /link.
    // Example UUID: 5a6d36e0-94d0-459f-9e79-8812543e2e8e
    const userId = 'f3a8d746-5295-4773-b663-3ff337a74372'; // <--- !!! REPLACE WITH A UUID !!!

    if (!alertPhrase) {
        alert('Please type the alert you want before clicking Create Alert.');
        return;
    }

    try {
        // 3. --- SEND POST REQUEST TO FLASK API ---
        const response = await fetch('http://127.0.0.1:5000/api/create-alert', {
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
        alert('⚠️ Failed to connect to the alert creation server. Make sure your web_api.py is running on port 5000.');
    }
}


// --- 2. LIVE PRICE FETCHING (MOCK/EXAMPLE) ---

function fetchAndDisplayLivePrices() {
    // This is a mock function. Replace with real CCXT or WebSocket API calls.
    const ethPrice = (3100 + Math.random() * 5 - 2.5).toFixed(2);
    const btcPrice = (102300 + Math.random() * 50 - 25).toFixed(2);

    const ethPriceEl = document.getElementById('eth-price');
    const btcPriceEl = document.getElementById('btc-price');

    if (ethPriceEl) ethPriceEl.textContent = ethPrice;
    if (btcPriceEl) btcPriceEl.textContent = btcPrice;
}


// --- 3. ALERT MANAGEMENT (NEW IMPLEMENTATION) ---

const userId = 'f3a8d746-5295-4773-b663-3ff337a74372'; // <--- MUST MATCH THE ID IN createAlertFromDashboard()

async function fetchMyAlerts() {
    const alertsTableBody = document.getElementById('alertsTableBody');
    if (!alertsTableBody) return; // Exit if the table body doesn't exist

    // Clear previous results
    alertsTableBody.innerHTML = '<tr><td colspan="7">Fetching active alerts...</td></tr>';
    
    try {
        const response = await fetch(`http://127.0.0.1:5000/api/my-alerts/${userId}`);
        const alerts = await response.json();

        alertsTableBody.innerHTML = ''; // Clear status message

        if (alerts.length === 0) {
            alertsTableBody.innerHTML = '<tr><td colspan="7">You have no active alerts. Create a new one!</td></tr>';
            return;
        }

        alerts.forEach(alert => {
            const row = alertsTableBody.insertRow();
            
            // Extract the simple condition text from params (if available)
            const params = alert.params || {};
            const conditionDisplay = alert.condition_text || params.condition || 'N/A';
            
            row.insertCell(0).textContent = alert.id;
            row.insertCell(1).textContent = alert.asset;
            row.insertCell(2).textContent = alert.timeframe;
            row.insertCell(3).textContent = alert.alert_type.replace('_', ' ');
            row.insertCell(4).textContent = conditionDisplay;
            row.insertCell(5).textContent = alert.status;
            
            // Action Cell (Delete Button)
            const actionCell = row.insertCell(6);
            const deleteButton = document.createElement('button');
            deleteButton.textContent = '❌ Delete';
            deleteButton.className = 'delete-btn';
            deleteButton.onclick = () => deleteAlert(alert.id);
            actionCell.appendChild(deleteButton);
        });

    } catch (error) {
        console.error('Error fetching alerts:', error);
        alertsTableBody.innerHTML = `<tr><td colspan="7" style="color:red;">Error loading alerts: ${error.message}. Is web_api.py running?</td></tr>`;
    }
}

async function deleteAlert(alertId) {
    if (!confirm(`Are you sure you want to delete Alert ID ${alertId}?`)) {
        return;
    }

    try {
        const response = await fetch('http://127.0.0.1:5000/api/delete-alert', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ alert_id: alertId }),
        });

        const result = await response.json();

        if (response.ok) {
            alert(`✅ Alert ID ${alertId} successfully deleted.`);
            // Refresh the list to remove the deleted alert from the view
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
    // IMPORTANT: Make sure the HTML element with id="alertsTableBody" exists!
    fetchMyAlerts(); 
    
    // Add event listener to the "Refresh List" button if it exists
    const refreshButton = document.getElementById('refreshAlertsList');
    if (refreshButton) {
        refreshButton.addEventListener('click', fetchMyAlerts);
    }
});