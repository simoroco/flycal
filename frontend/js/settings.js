/* === FlyCal — Settings Page (Auto-Save) === */

let settingsAirlines = [];
let settingsTimeSlots = [];
let settingsData = {};

/* ── Debounce utility ── */
const _debounceTimers = {};
function debounce(key, fn, delay = 600) {
    clearTimeout(_debounceTimers[key]);
    _debounceTimers[key] = setTimeout(fn, delay);
}

/* ── Init ── */
async function initSettings() {
    await Promise.all([
        loadAllSettings(),
        loadAirlinesList(),
    ]);
    bindAutoSave();
}

/* ── Bind auto-save listeners ── */
function bindAutoSave() {
    // Ideal price
    document.getElementById('idealPrice').addEventListener('change', () => {
        debounce('idealPrice', saveIdealPrice);
    });

    // Email fields — auto-save on blur or change
    const emailFields = ['smtpHost', 'smtpPort', 'smtpUser', 'smtpPassword', 'smtpTo', 'serverHostname'];
    emailFields.forEach(id => {
        const el = document.getElementById(id);
        el.addEventListener('change', () => debounce('email', saveEmailSettings));
        el.addEventListener('blur', () => debounce('email', saveEmailSettings));
    });

    // Time slots — delegate change events on the container
    document.getElementById('timeSlotsContainer').addEventListener('change', () => {
        debounce('timeSlots', saveTimeSlots);
    });
    document.getElementById('timeSlotsContainer').addEventListener('blur', () => {
        debounce('timeSlots', saveTimeSlots);
    }, true); // capture phase for blur

    // Airlines — delegate on container
    const airlinesContainer = document.getElementById('airlinesListSettings');
    airlinesContainer.addEventListener('change', (e) => {
        const row = e.target.closest('.airline-row');
        if (row) debounce('airline-' + row.dataset.id, () => saveAirline(parseInt(row.dataset.id)));
    });
    airlinesContainer.addEventListener('blur', (e) => {
        const row = e.target.closest('.airline-row');
        if (row) debounce('airline-' + row.dataset.id, () => saveAirline(parseInt(row.dataset.id)));
    }, true);
}

/* ── Load settings ── */
async function loadAllSettings() {
    try {
        settingsData = await API.getSettings();

        document.getElementById('idealPrice').value = settingsData.ideal_price || 40;
        document.getElementById('smtpHost').value = settingsData.smtp_host || '';
        document.getElementById('smtpPort').value = settingsData.smtp_port || 587;
        document.getElementById('smtpUser').value = settingsData.smtp_user || '';
        document.getElementById('smtpPassword').value = settingsData.smtp_password || '';
        document.getElementById('smtpTo').value = settingsData.smtp_to || '';
        document.getElementById('serverHostname').value = settingsData.server_hostname || '192.168.1.50';

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

/* ── Ideal price ── */
async function saveIdealPrice() {
    const val = parseInt(document.getElementById('idealPrice').value) || 40;
    try {
        await API.updateSettings({ ideal_price: val });
        Toast.success('Reference price saved.');
    } catch (e) {
        Toast.error('Error: ' + e.message);
    }
}


/* ── Airlines ── */
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
        Toast.error('Error: ' + e.message);
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
        const airline = settingsAirlines.find(a => a.id === id);
        if (airline) Object.assign(airline, { name, fees_fixed, fees_percent, logo_url });
        Toast.success('Airline saved.');
    } catch (e) {
        Toast.error('Error: ' + e.message);
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
        Toast.success('Logo uploaded.');
    } catch (e) {
        Toast.error('Upload error: ' + e.message);
    }
}

async function deleteAirline(id) {
    Toast.confirm('Delete this airline?', async () => {
        try {
            await API.deleteAirline(id);
            await loadAirlinesList();
            Toast.success('Airline deleted.');
        } catch (e) {
            Toast.error('Error: ' + e.message);
        }
    });
}

async function addAirline() {
    const name = prompt('Airline name:');
    if (!name || !name.trim()) return;
    try {
        await API.createAirline({ name: name.trim(), fees_fixed: 0, fees_percent: 0, enabled: true });
        await loadAirlinesList();
        Toast.success('Airline added.');
    } catch (e) {
        Toast.error('Error: ' + e.message);
    }
}

/* ── Time Slots ── */
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
    saveTimeSlots();
}

function removeTimeSlot(index) {
    settingsTimeSlots.splice(index, 1);
    renderTimeSlots();
    saveTimeSlots();
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
        Toast.success('Time slots saved.');
    } catch (e) {
        Toast.error('Error: ' + e.message);
    }
}

/* ── Password toggle ── */
function togglePasswordVisibility() {
    const input = document.getElementById('smtpPassword');
    const iconEye = document.getElementById('pwIconEye');
    const iconEyeOff = document.getElementById('pwIconEyeOff');
    if (input.type === 'password') {
        input.type = 'text';
        iconEye.style.display = 'none';
        iconEyeOff.style.display = 'block';
    } else {
        input.type = 'password';
        iconEye.style.display = 'block';
        iconEyeOff.style.display = 'none';
    }
}

/* ── Email settings ── */
function toggleEmail() {
    const el = document.getElementById('emailToggle');
    el.classList.toggle('active');
    saveEmailSettings();
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
            server_hostname: document.getElementById('serverHostname').value || '192.168.1.50',
            smtp_send_enabled: emailEnabled,
        });
        Toast.success('Email settings saved.');
    } catch (e) {
        Toast.error('Error: ' + e.message);
    }
}

async function testSmtp() {
    const resultEl = document.getElementById('smtpTestResult');
    resultEl.textContent = 'Testing...';
    resultEl.style.color = 'var(--text-muted)';

    await saveEmailSettings();

    try {
        const result = await API.testSmtp();
        resultEl.textContent = result.message || 'Test email sent! Check your inbox.';
        resultEl.style.color = 'var(--green)';
    } catch (e) {
        resultEl.textContent = 'Failed: ' + e.message;
        resultEl.style.color = 'var(--red)';
    }
}

/* ── Data export/import ── */
function exportData() {
    window.location.href = '/api/settings/export';
}

async function importData(input) {
    if (!input.files || !input.files[0]) return;
    const resultEl = document.getElementById('importResult');
    resultEl.textContent = 'Importing...';
    resultEl.style.color = 'var(--text-muted)';

    const formData = new FormData();
    formData.append('file', input.files[0]);

    try {
        const resp = await fetch('/api/settings/import', { method: 'POST', body: formData });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || resp.statusText);
        }
        const data = await resp.json();
        const counts = Object.entries(data.imported || {}).map(([k, v]) => `${k}: ${v}`).join(', ');
        resultEl.textContent = `Import complete (${counts})`;
        resultEl.style.color = 'var(--green)';
        Toast.success('Import successful! Reloading...');
        setTimeout(() => location.reload(), 1500);
    } catch (e) {
        resultEl.textContent = 'Import failed: ' + e.message;
        resultEl.style.color = 'var(--red)';
        Toast.error('Import failed: ' + e.message);
    }
    input.value = '';
}

function resetDatabase() {
    Toast.confirm('WARNING: This will delete ALL data (searches, flights, logs, price history). Settings and airlines will be kept. Continue?', async () => {
        try {
            const result = await API.post('/api/settings/reset');
            Toast.success('Database reset complete. Reloading...');
            setTimeout(() => location.reload(), 1500);
        } catch (e) {
            Toast.error('Reset failed: ' + e.message);
        }
    });
}

document.addEventListener('DOMContentLoaded', initSettings);
