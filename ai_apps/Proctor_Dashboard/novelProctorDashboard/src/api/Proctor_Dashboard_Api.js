/**
 * ProctorTool Frontend API SDK (Dashboard Monitoring Version)
 * 
 * Provides a standardized interface for interacting with the 
 * Frappe backend to fetch session lists, details, and live trust scores.
 * 
 * NOTE: This is the dashboard version. Candidate/ML execution logic
 * has been stripped out.
 */

const DEFAULT_API_BASE_URL = import.meta.env.VITE_API_BASE || "https://proctor.novelinfra.com";
const DEFAULT_FRAPPE_API_BASE = import.meta.env.VITE_FRAPPE_BASE || "http://10.80.4.71";

class ProctorAPIClient {
    constructor(baseUrl = DEFAULT_API_BASE_URL, frappeBaseUrl = DEFAULT_FRAPPE_API_BASE) {
        this.baseUrl = baseUrl.replace(/\/$/, "");
        this.frappeBaseUrl = frappeBaseUrl.replace(/\/$/, "");
    }

    /**
     * Set or update the base URL of the Proctor ML service.
     * @param {string} url 
     */
    setBaseUrl(url) {
        this.baseUrl = url.replace(/\/$/, "");
    }

    /**
     * Helper for robust JSON POST requests to Frappe.
     */
    async _frappePost(path, data = {}) {
        const url = `${this.frappeBaseUrl}${path}`;
        const response = await fetch(url, {
            method: "POST",
            credentials: "include",
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            body: JSON.stringify(data),
        });

        if (!response.ok) {
            let errorMsg = `Frappe Error ${response.status}`;
            try {
                const errData = await response.json();
                errorMsg = (errData.exc && JSON.parse(errData.exc)[0]) || errData.message || errorMsg;
            } catch (e) { }
            throw new Error(errorMsg);
        }

        const resData = await response.json();
        return resData.message || resData;
    }

    /**
     * Helper for GET requests.
     */
    async _get(path) {
        const url = `${this.baseUrl}${path}`;
        const response = await fetch(url, {
            method: "GET",
            headers: {
                "Accept": "application/json",
            },
        });

        if (!response.ok) {
            throw new Error(`ProctorAPI [GET ${path}] failed: ${response.status}`);
        }

        return response.json();
    }

    /**
     * Get the live real-time trust score of the session.
     * @param {string} sessionId - Active session ID.
     * @returns {Promise<Object>} { session_id, trust_score }
     */
    async getTrustScore(sessionId) {
        if (!sessionId) {
            throw new Error("No active session ID provided.");
        }
        // Directly fetch trust score from Frappe backend
        const sessionInfo = await this._frappePost("/api/method/ai_apps.api.proctor_api.rule_engine.get_trust_score", { session_name: sessionId });
        return { session_id: sessionId, trust_score: sessionInfo.trust_score };
    }

    /**
     * Get risk band based on trust score.
     * @param {string} sessionId - Session ID.
     * @returns {Promise<string>} risk band (LOW, MEDIUM, HIGH, CRITICAL)
     */
    async getRiskBand(sessionId) {
        const { trust_score } = await this.getTrustScore(sessionId);
        if (trust_score > 85) return "LOW";
        if (trust_score > 65) return "MEDIUM";
        if (trust_score > 40) return "HIGH";
        return "CRITICAL";
    }

    /**
     * Delete candidate data sequentially.
     * @param {string} sessionId - Session ID.
     * @returns {Promise<Object>} { success }
     */
    async deleteCandidateData(sessionId) {
        if (!sessionId) {
            throw new Error("No active session ID provided.");
        }
        return this._frappePost("/api/method/ai_apps.api.proctor_api.proctor_session.delete_candidate_data", { session_name: sessionId });
    }

    /**
     * Check the health of the ML Backend service.
     */
    async checkHealth() {
        return this._get("/health");
    }
}

// Export singleton instance as default
const proctorApi = new ProctorAPIClient();
export default proctorApi;

