/* === FlyCal — Automate Page === */

let allCrawlers = [];
let globalEnabled = false;

async function init() {
    await loadStatus();
    await Promise.all([loadCrawlers(), loadLogs()]);
}

async function loadStatus() {
    try {
        const status = await API.getAutomateStatus();
        globalEnabled = status.enabled;
        document.getElementById('globalToggle').checked = globalEnabled;
        const label = globalEnabled ? 'ON' : 'OFF';
        const count = `${status.enabled_count}/${status.crawler_count} active`;
        document.getElementById('globalStatus').textContent = `${label} — ${count}`;
        updateBadge(globalEnabled);
    } catch (e) { console.error('Status error:', e); }
}

async function loadCrawlers() {
    try {
        allCrawlers = await API.getCrawlers();
        renderCrawlers();
    } catch (e) {
        document.getElementById('crawlerList').innerHTML = `<div class="crawler-empty">Error: ${e.message}</div>`;
    }
}

function renderCrawlers() {
    const c = document.getElementById('crawlerList');
    if (!allCrawlers.length) {
        c.innerHTML = '<div class="crawler-empty">No scheduled crawlers.<br>Click "Schedule last search" or use the History page to add one.</div>';
        return;
    }
    c.innerHTML = allCrawlers.map(renderCrawlerRow).join('');
}

function renderCrawlerRow(crawler) {
    const s = crawler.search;
    if (!s) return '';
    const airlines = (s.airlines || []).join(', ');
    const times = ['04:00','07:00','14:00','18:00','23:00'];
    const options = times.map(t => `<option value="${t}" ${t === crawler.schedule_time ? 'selected' : ''}>${t}</option>`).join('');
    const disabledAttr = globalEnabled ? '' : 'disabled';
    const rowClass = globalEnabled ? 'crawler-row' : 'crawler-row disabled';

    return `<div class="${rowClass}">
        <span class="crawler-route">${s.origin_city} → ${s.destination_city}</span>
        <span class="crawler-sep">|</span>
        <span class="crawler-dates">${s.date_from} → ${s.date_to}</span>
        <span class="crawler-sep">|</span>
        <span class="crawler-airlines" title="${airlines}">${airlines}</span>
        <span class="crawler-sep">|</span>
        <span class="crawler-schedule">
            <select onchange="updateSchedule(${crawler.id}, this.value)">${options}</select>
        </span>
        <span class="crawler-sep">|</span>
        <label class="auto-switch">
            <input type="checkbox" ${crawler.enabled ? 'checked' : ''} ${disabledAttr} onchange="toggleCrawler(${crawler.id}, this.checked)">
            <span class="auto-slider"></span>
        </label>
        <div class="crawler-actions">
            <button class="btn-sm btn-ghost" onclick="runNow(${crawler.id})">Run now</button>
            <button class="btn-sm btn-danger" onclick="removeCrawler(${crawler.id})">Delete</button>
        </div>
    </div>`;
}

async function toggleGlobal() {
    try {
        const res = await API.toggleGlobalCrawler();
        await loadStatus();
        await loadCrawlers();
        Toast.success(res.enabled ? 'Crawler enabled' : 'Crawler disabled');
    } catch (e) { Toast.error(e.message); }
}

function updateBadge(enabled) {
    const dot = document.getElementById('crawlerDot');
    const badgeLabel = document.getElementById('crawlerLabel');
    if (dot) dot.style.background = enabled ? 'var(--green)' : 'var(--red)';
    if (badgeLabel) badgeLabel.textContent = enabled ? 'Crawler ON' : 'Crawler OFF';
}

async function scheduleLastSearch() {
    try {
        const data = await API.getLastSearch();
        if (!data || !data.id) { Toast.error('No search to schedule'); return; }
        await API.createCrawler({ search_id: data.id, schedule_time: '04:00' });
        Toast.success('Crawler scheduled at 04:00');
        await loadCrawlers();
        await loadStatus();
    } catch (e) { Toast.error(e.message); }
}

async function updateSchedule(id, time) {
    try { await API.updateCrawler(id, { schedule_time: time }); }
    catch (e) { Toast.error(e.message); await loadCrawlers(); }
}

async function toggleCrawler(id, enabled) {
    try { await API.updateCrawler(id, { enabled }); await loadStatus(); }
    catch (e) { Toast.error(e.message); await loadCrawlers(); }
}

async function runNow(id) {
    try {
        await API.runCrawler(id);
        Toast.success('Crawler started');
        setTimeout(loadLogs, 3000);
    } catch (e) { Toast.error(e.message); }
}

async function removeCrawler(id) {
    try {
        await API.deleteCrawler(id);
        Toast.success('Crawler removed');
        await loadCrawlers();
        await loadStatus();
    } catch (e) { Toast.error(e.message); }
}

async function loadLogs() {
    try {
        const logs = await API.getAutomateLogs();
        const container = document.getElementById('logsContainer');
        if (!logs.length) { container.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">No logs yet</div>'; return; }

        container.innerHTML = logs.map(log => {
            const dt = log.started_at ? fmtDT(log.started_at) : '';
            const statusClass = `status-${log.status}`;
            const errMsg = log.error_msg ? ` — ${log.error_msg}` : '';
            return `<div class="log-line">${dt} <span class="${statusClass}">${log.status}</span> ${log.triggered_by}${errMsg}</div>`;
        }).join('');
    } catch (e) { console.error('Logs error:', e); }
}

document.addEventListener('DOMContentLoaded', init);
