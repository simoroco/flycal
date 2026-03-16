/* === FlyCal — Settings Page === */

let settingsAirlines = [];
let settingsTimeSlots = [];
let settingsData = {};

async function initSettings() {
    await Promise.all([
        loadAllSettings(),
        loadAirlinesList(),
        loadCrawlerInfo(),
        loadLogs(),
    ]);
}

async function loadAllSettings() {
    try {
        settingsData = await API.getSettings();

        document.getElementById('idealPrice').value = settingsData.ideal_price || 100;
        document.getElementById('smtpHost').value = settingsData.smtp_host || '';
        document.getElementById('smtpPort').value = settingsData.smtp_port || 587;
        document.getElementById('smtpUser').value = settingsData.smtp_user || '';
        document.getElementById('smtpPassword').value = settingsData.smtp_password || '';
        document.getElementById('smtpTo').value = settingsData.smtp_to || '';

        const emailToggle = document.getElementById('emailToggle');
        if (settingsData.smtp_send_enabled === true || settingsData.smtp_send_enabled === 'true') {
            emailToggle.classList.add('active');
        } else {
            emailToggle.classList.remove('active');
        }

        settingsTimeSlots = settingsData.time_slots || [];
        renderTimeSlots();
    } catch (e) {
        console.error('Failed to load settings:', e);
    }
}

async function loadAirlinesList() {
    try {
        settingsAirlines = await API.getAirlines();
        renderAirlines();
    } catch (e) {
        console.error('Failed to load airlines:', e);
    }
}

function renderAirlines() {
    const container = document.getElementById('airlinesListSettings');
    if (!settingsAirlines.length) {
        container.innerHTML = '<p class="text-muted">No airlines configured</p>';
        return;
    }

    container.innerHTML = settingsAirlines.map(a => {
        const logoSrc = a.logo_url || '';
        const logoPreview = logoSrc
            ? `<img src="${logoSrc}" alt="${a.name}" class="airline-logo-preview" onerror="this.style.display='none'">`
            : `<div class="airline-logo-placeholder">${(a.name || '??').substring(0,2).toUpperCase()}</div>`;
        return `
        <div class="airline-row" data-id="${a.id}">
            <div class="airline-logo-cell">
                ${logoPreview}
            </div>
            <input type="text" class="input-field" value="${a.name}" data-field="name" placeholder="Name">
            <label style="font-size:0.75rem;color:var(--text-muted)">Fixed fees (€)</label>
            <input type="number" class="input-field input-sm" value="${a.fees_fixed}" data-field="fees_fixed" step="0.01" min="0">
            <label style="font-size:0.75rem;color:var(--text-muted)">Fees (%)</label>
            <input type="number" class="input-field input-sm" value="${a.fees_percent}" data-field="fees_percent" step="0.01" min="0">
            <div class="toggle-switch ${a.enabled ? 'active' : ''}" onclick="toggleAirlineEnabled(${a.id}, this)">
                <div class="toggle-slider"></div>
            </div>
            <div class="airline-logo-actions">
                <input type="text" class="input-field input-sm" value="${logoSrc}" data-field="logo_url" placeholder="Logo URL">
                <label class="btn-sm btn-secondary logo-upload-btn">
                    📁
                    <input type="file" accept="image/*" style="display:none" onchange="uploadLogo(${a.id}, this)">
                </label>
            </div>
            <button class="btn-sm btn-accent" onclick="saveAirline(${a.id})">Save</button>
            <button class="btn-sm btn-danger" onclick="deleteAirline(${a.id})">Delete</button>
        </div>`;
    }).join('');
}

async function toggleAirlineEnabled(id, el) {
    el.classList.toggle('active');
    const enabled = el.classList.contains('active');
    try {
        await API.updateAirline(id, { enabled });
        const airline = settingsAirlines.find(a => a.id === id);
        if (airline) airline.enabled = enabled;
    } catch (e) {
        alert('Error: ' + e.message);
        el.classList.toggle('active');
    }
}

async function saveAirline(id) {
    const row = document.querySelector(`.airline-row[data-id="${id}"]`);
    if (!row) return;

    const name = row.querySelector('[data-field="name"]').value.trim();
    const fees_fixed = parseFloat(row.querySelector('[data-field="fees_fixed"]').value) || 0;
    const fees_percent = parseFloat(row.querySelector('[data-field="fees_percent"]').value) || 0;
    const logo_url = row.querySelector('[data-field="logo_url"]')?.value.trim() || null;

    try {
        await API.updateAirline(id, { name, fees_fixed, fees_percent, logo_url });
        await loadAirlinesList();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function uploadLogo(airlineId, input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];
    const formData = new FormData();
    formData.append('file', file);
    try {
        const resp = await fetch(`/api/airlines/${airlineId}/logo`, {
            method: 'POST',
            body: formData,
        });
        if (!resp.ok) throw new Error('Upload failed');
        await loadAirlinesList();
    } catch (e) {
        alert('Upload error: ' + e.message);
    }
}

async function deleteAirline(id) {
    if (!confirm('Delete this airline?')) return;
    try {
        await API.deleteAirline(id);
        await loadAirlinesList();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function addAirline() {
    const name = prompt('Airline name:');
    if (!name || !name.trim()) return;
    try {
        await API.createAirline({ name: name.trim(), fees_fixed: 0, fees_percent: 0, enabled: true });
        await loadAirlinesList();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function saveIdealPrice() {
    const val = document.getElementById('idealPrice').value;
    try {
        await API.updateSettings({ ideal_price: val });
        alert('Reference price saved.');
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

function renderTimeSlots() {
    const container = document.getElementById('timeSlotsContainer');
    if (!settingsTimeSlots.length) {
        container.innerHTML = '<p class="text-muted">No time slots configured</p>';
        return;
    }

    container.innerHTML = settingsTimeSlots.map((slot, i) => `
        <div class="timeslot-row" data-index="${i}">
            <input type="text" class="input-field input-sm" value="${slot.label || ''}" placeholder="Label" data-field="label">
            <input type="time" value="${slot.start || '00:00'}" data-field="start" onclick="if(this.showPicker)this.showPicker()">
            <span style="color:var(--text-muted)">→</span>
            <input type="time" value="${slot.end || '00:00'}" data-field="end" onclick="if(this.showPicker)this.showPicker()">
            <select data-field="color">
                <option value="green" ${slot.color === 'green' ? 'selected' : ''}>Green</option>
                <option value="orange" ${slot.color === 'orange' ? 'selected' : ''}>Orange</option>
                <option value="red" ${slot.color === 'red' ? 'selected' : ''}>Red</option>
            </select>
            <button class="btn-sm btn-danger" onclick="removeTimeSlot(${i})">Delete</button>
        </div>
    `).join('');
}

function addTimeSlot() {
    settingsTimeSlots.push({ label: 'New slot', start: '00:00', end: '06:00', color: 'orange' });
    renderTimeSlots();
}

function removeTimeSlot(index) {
    settingsTimeSlots.splice(index, 1);
    renderTimeSlots();
}

async function saveTimeSlots() {
    const rows = document.querySelectorAll('.timeslot-row');
    const slots = [];
    rows.forEach(row => {
        slots.push({
            label: row.querySelector('[data-field="label"]').value,
            start: row.querySelector('[data-field="start"]').value,
            end: row.querySelector('[data-field="end"]').value,
            color: row.querySelector('[data-field="color"]').value,
        });
    });

    try {
        await API.updateSettings({ time_slots: slots });
        settingsTimeSlots = slots;
        alert('Time slots saved.');
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function loadCrawlerInfo() {
    try {
        const status = await API.getCrawlerStatus();

        const dot = document.getElementById('crawlerDot');
        const label = document.getElementById('crawlerLabel');
        const toggle = document.getElementById('crawlerToggle');
        const statusText = document.getElementById('crawlerStatus');
        const lastRun = document.getElementById('lastRun');
        const nextRun = document.getElementById('nextRun');

        dot.className = 'crawler-dot ' + (status.enabled ? 'active' : 'inactive');
        label.textContent = status.enabled ? 'Crawler ON' : 'Crawler OFF';

        if (status.enabled) {
            toggle.classList.add('active');
            statusText.textContent = 'Active';
        } else {
            toggle.classList.remove('active');
            statusText.textContent = 'Inactive';
        }

        if (status.last_run && status.last_run.started_at) {
            const d = new Date(status.last_run.started_at);
            lastRun.textContent = d.toLocaleString('en-US') + ' — ' + (status.last_run.status || '');
        } else {
            lastRun.textContent = '—';
        }

        nextRun.textContent = status.next_run
            ? new Date(status.next_run).toLocaleString('en-US')
            : '—';
    } catch (e) {
        console.error('Failed to load crawler info:', e);
    }
}

async function toggleCrawler() {
    try {
        await API.toggleCrawler();
        await loadCrawlerInfo();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function runCrawlerNow() {
    try {
        await API.runCrawler();
        alert('Crawler started!');
        setTimeout(loadCrawlerInfo, 2000);
        setTimeout(loadLogs, 5000);
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function loadLogs() {
    try {
        const logs = await API.getLogs();
        const container = document.getElementById('logsContainer');

        if (!logs.length) {
            container.innerHTML = '<p class="text-muted">No logs</p>';
            return;
        }

        container.innerHTML = logs.map(log => {
            const time = log.started_at ? new Date(log.started_at).toLocaleString('en-US') : '—';
            const statusColor = log.status === 'success' ? 'var(--green)' :
                                log.status === 'error' ? 'var(--red)' :
                                log.status === 'running' ? 'var(--orange)' : 'var(--text-muted)';
            const errorPart = log.error_msg ? ` — ${log.error_msg}` : '';
            return `<div class="log-entry">
                <span class="log-time">${time}</span>
                <span class="log-status" style="color:${statusColor}">${log.status}</span>
                <span class="log-msg">${log.triggered_by}${errorPart}</span>
            </div>`;
        }).join('');
    } catch (e) {
        console.error('Failed to load logs:', e);
    }
}

function toggleEmail() {
    const el = document.getElementById('emailToggle');
    el.classList.toggle('active');
}

async function saveEmailSettings() {
    const emailEnabled = document.getElementById('emailToggle').classList.contains('active');
    try {
        await API.updateSettings({
            smtp_host: document.getElementById('smtpHost').value,
            smtp_port: document.getElementById('smtpPort').value,
            smtp_user: document.getElementById('smtpUser').value,
            smtp_password: document.getElementById('smtpPassword').value,
            smtp_to: document.getElementById('smtpTo').value,
            smtp_send_enabled: emailEnabled,
        });
        alert('Email settings saved.');
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function testSmtp() {
    const resultEl = document.getElementById('smtpTestResult');
    resultEl.textContent = 'Testing...';
    resultEl.style.color = 'var(--text-muted)';

    await saveEmailSettings();

    try {
        const result = await API.testSmtp();
        resultEl.textContent = result.message || 'Connection successful!';
        resultEl.style.color = 'var(--green)';
    } catch (e) {
        resultEl.textContent = 'Failed: ' + e.message;
        resultEl.style.color = 'var(--red)';
    }
}

document.addEventListener('DOMContentLoaded', initSettings);
