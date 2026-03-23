/** Format an ISO date/datetime string as YYYY-MM-DD or YYYY-MM-DD HH:MM */
function fmtDT(iso, timeOnly) {
    if (!iso) return '—';
    const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
    if (isNaN(d)) return iso;
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const date = `${yyyy}-${mm}-${dd}`;
    if (timeOnly === false) return date;
    const hh = String(d.getHours()).padStart(2, '0');
    const mi = String(d.getMinutes()).padStart(2, '0');
    return `${date} ${hh}:${mi}`;
}

const API = {
    BASE: '/api',

    async get(url) {
        const resp = await fetch(url);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || resp.statusText);
        }
        return resp.json();
    },

    async post(url, body = null) {
        const opts = {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        };
        if (body !== null) {
            opts.body = JSON.stringify(body);
        }
        const resp = await fetch(url, opts);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || resp.statusText);
        }
        return resp.json();
    },

    async put(url, body) {
        const resp = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || resp.statusText);
        }
        return resp.json();
    },

    async del(url) {
        const resp = await fetch(url, { method: 'DELETE' });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || resp.statusText);
        }
        return resp.json();
    },

    async getSettings() {
        return this.get('/api/settings');
    },

    async getAirlines() {
        return this.get('/api/airlines');
    },

    async getCrawlerStatus() {
        return this.get('/api/crawler/status');
    },

    async getLastSearch() {
        return this.get('/api/flights/last');
    },

    async launchSearch(params) {
        return this.post('/api/flights/search', params);
    },

    async cancelSearch() {
        return this.post('/api/flights/cancel');
    },

    async getPriceHistory(flightId) {
        return this.get(`/api/flights/price-history/${flightId}`);
    },

    async getSearches() {
        return this.get('/api/searches');
    },

    async rerunSearch(id) {
        return this.post(`/api/searches/${id}/rerun`);
    },

    async toggleCrawler() {
        return this.post('/api/crawler/toggle');
    },

    async runCrawler() {
        return this.post('/api/crawler/run');
    },

    async getLogs() {
        return this.get('/api/logs');
    },

    async getCrawlerLogs() {
        return this.get('/api/crawler/logs');
    },

    async updateSettings(settings) {
        return this.put('/api/settings', { settings });
    },

    async createAirline(data) {
        return this.post('/api/airlines', data);
    },

    async updateAirline(id, data) {
        return this.put(`/api/airlines/${id}`, data);
    },

    async deleteAirline(id) {
        return this.del(`/api/airlines/${id}`);
    },

    async testSmtp() {
        return this.post('/api/settings/smtp-test');
    },
};
