/**
 * API.JS - Handles Data Fetching only (No UI code)
 */

const API = {
    async getSignals(type = 'ALL') {
        try {
            const endpoint = type === 'ALL' ? '/api/signals' : `/api/signals?type=${type}`;
            const res = await fetch(`${window.API_BASE_URL}${endpoint}`);
            return await res.json();
        } catch (e) {
            console.error("API Error:", e);
            return [];
        }
    },

    async getMyAlerts() {
        const token = getToken(); // Uses helper from auth.js
        if (!token) return [];
        try {
            const res = await fetch(`${window.API_BASE_URL}/api/my-alerts`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            return await res.json();
        } catch (e) { return []; }
    },

    async createAlert(payload) {
        const token = getToken();
        try {
            const res = await fetch(`${window.API_BASE_URL}/api/create-alert`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify(payload)
            });
            return await res.json();
        } catch (e) { return { error: "Network Error" }; }
    },

    async deleteAlert(alertId) {
        const token = getToken();
        try {
            await fetch(`${window.API_BASE_URL}/api/delete-alert`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ 'alert_id': alertId })
            });
            return true;
        } catch (e) { return false; }
    },
    
    // Check if user has linked Telegram
    async getTelegramStatus() {
        const userId = getUserId();
        if (!window.supabaseClient || !userId) return false;
        
        const { data } = await window.supabaseClient
            .from('users')
            .select('telegram_chat_id')
            .eq('user_uuid', userId)
            .maybeSingle();
            
        return data?.telegram_chat_id ? true : false;
    }
};