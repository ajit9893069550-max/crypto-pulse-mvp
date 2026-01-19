/**
 * API.JS - Handles Data Fetching
 */

const API = {
    async getSignals(type = 'ALL') {
        try {
            // FIX: Use relative path directly. No variable needed.
            const endpoint = type === 'ALL' 
                ? '/api/signals' 
                : `/api/signals?type=${type}`;
            
            const res = await fetch(endpoint);
            if (!res.ok) throw new Error("Failed to fetch signals");
            return await res.json();
        } catch (e) {
            console.error("API Error:", e);
            return [];
        }
    },

    async getMyAlerts() {
        const userId = localStorage.getItem('user_id');
        if (!userId) return [];
        try {
            const res = await fetch(`/api/my-alerts?user_id=${userId}`);
            return await res.json();
        } catch (e) { return []; }
    },

    async createAlert(payload) {
        const userId = localStorage.getItem('user_id');
        if (!userId) return { success: false, error: "Not logged in" };

        try {
            // Add user_id to payload
            payload.user_id = userId;
            
            const res = await fetch('/api/create-alert', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            return await res.json();
        } catch (e) { return { success: false, error: "Network Error" }; }
    },

    async deleteAlert(alertId) {
        try {
            await fetch(`/api/delete-alert/${alertId}`, { method: 'DELETE' });
            return true;
        } catch (e) { return false; }
    },

    async getTelegramStatus() {
        const userId = localStorage.getItem('user_id');
        if (!userId) return false;
        try {
            const res = await fetch(`/api/telegram-status?user_id=${userId}`);
            const data = await res.json();
            return data.linked;
        } catch (e) { return false; }
    },

    // --- ADDED THIS FUNCTION TO FIX THE ERROR ---
    async getStrategies() {
        try {
            const res = await fetch('/api/strategies');
            return await res.json();
        } catch (e) { return []; }
    }
};