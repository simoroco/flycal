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
