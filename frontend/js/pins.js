/* === FlyCal — Pins Page Controller === */

let allPins = [];
const chartInstances = {};

// ── Init ──
async function init() {
    await loadPins();
}

async function loadPins() {
    try {
        allPins = await API.getPins();
        renderPins();
    } catch (e) {
        document.getElementById('pinsContent').innerHTML =
            `<div class="pins-empty">Failed to load pins: ${e.message}</div>`;
    }
}

function renderPins() {
    const container = document.getElementById('pinsContent');
    if (!allPins.length) {
        container.innerHTML = '<div class="pins-empty">No pinned flights yet.<br>Double-click or right-click a flight on the Scan page to pin it.</div>';
        return;
    }
    container.innerHTML = allPins.map(pin => renderPinCard(pin)).join('');

    // Render charts after DOM is ready
    for (const pin of allPins) {
        renderPriceChart(`chart-pin-${pin.id}`, pin);
    }
}

function renderPinCard(pin) {
    const currentPrice = pin.current_price != null ? `${Math.round(pin.current_price)}€` : '—';
    const oldestPrice = pin.oldest_price != null ? `${Math.round(pin.oldest_price)}€` : '—';
    const oldestDate = pin.oldest_price_date ? pin.oldest_price_date.split('T')[0] : '';
    let changeHtml = '';
    if (pin.current_price != null && pin.oldest_price != null && pin.oldest_price !== pin.current_price) {
        const diff = pin.current_price - pin.oldest_price;
        const pct = ((diff / pin.oldest_price) * 100).toFixed(0);
        const arrow = diff < 0 ? '↓' : '↑';
        const cls = diff < 0 ? 'down' : 'up';
        changeHtml = `<span class="pin-price-change ${cls}">${arrow}${Math.abs(Math.round(diff))}€ (${pct}%)</span>`;
    }

    const dirBadge = `<span class="pin-direction-badge ${pin.direction}">${pin.direction === 'outbound' ? 'OUT' : 'RET'}</span>`;
    const alertsHtml = renderAlertSection(pin);

    return `
    <div class="pin-card" data-pin-id="${pin.id}">
        <div class="pin-top-band">
            ${pin.airline_logo_url ? `<img src="${pin.airline_logo_url}" class="pin-logo" onerror="this.style.display='none'">` : ''}
            <span class="pin-airline">${pin.airline_name}</span>
            ${dirBadge}
            <span class="pin-route">${pin.origin_airport} → ${pin.destination_airport}</span>
            <span class="pin-sep">|</span>
            <span class="pin-info">${pin.flight_date} ${pin.departure_time}</span>
            <span class="pin-sep">|</span>
            <span class="pin-info"><span class="pin-info-label">Start</span><span class="pin-info-value">${oldestPrice}</span> <span style="color:var(--text-muted);font-size:0.65rem">${oldestDate}</span></span>
            <span class="pin-sep">|</span>
            <span class="pin-info"><span class="pin-info-label">Now</span><span class="pin-info-value">${currentPrice}</span> ${changeHtml}</span>
            <span class="pin-sep">|</span>
            <span class="pin-info" style="color:var(--text-muted)">${pin.price_data_points} pts</span>
            <div class="pin-actions">
                <button class="btn-sm btn-danger" onclick="unpinFlight(${pin.id})">Unpin</button>
                <a href="/" class="btn-sm btn-ghost" style="text-decoration:none">Scan</a>
            </div>
        </div>
        <div class="pin-chart-container">
            <canvas id="chart-pin-${pin.id}"></canvas>
        </div>
        ${alertsHtml}
    </div>`;
}

// ── Chart rendering ──
async function renderPriceChart(canvasId, pin) {
    try {
        const data = await API.getPinPriceHistory(pin.id);
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        if (data.length === 0) {
            canvas.parentElement.innerHTML = '<div class="pin-chart-empty">No price data available yet.</div>';
            return;
        }

        const labels = data.map(d => {
            const dt = new Date(d.recorded_at);
            return `${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,'0')}-${String(dt.getDate()).padStart(2,'0')}`;
        });
        const prices = data.map(d => d.price);

        // Projection via linear regression if >= 3 points
        let projLabels = [];
        let projPrices = [];
        if (data.length >= 3) {
            const reg = linearRegression(data.map((d, i) => ({ x: i, y: d.price })));
            const lastDate = new Date(data[data.length - 1].recorded_at);
            const flightDate = new Date(pin.flight_date + 'T00:00:00');
            const daysBetween = Math.max(1, Math.ceil((flightDate - lastDate) / 86400000));
            const steps = Math.min(daysBetween, 30); // max 30 projection points

            projLabels.push(labels[labels.length - 1]);
            projPrices.push(prices[prices.length - 1]);

            for (let s = 1; s <= steps; s++) {
                const projDate = new Date(lastDate.getTime() + s * 86400000);
                projLabels.push(`${projDate.getFullYear()}-${String(projDate.getMonth()+1).padStart(2,'0')}-${String(projDate.getDate()).padStart(2,'0')}`);
                const projPrice = reg.intercept + reg.slope * (data.length - 1 + s);
                projPrices.push(Math.max(0, Math.round(projPrice * 100) / 100));
            }
        }

        const allLabels = [...new Set([...labels, ...projLabels])];

        // Destroy old chart
        if (chartInstances[canvasId]) chartInstances[canvasId].destroy();

        const datasets = [
            {
                label: 'Price (€)',
                data: labels.map((l, i) => ({ x: l, y: prices[i] })),
                borderColor: '#6c63ff',
                backgroundColor: 'rgba(108, 99, 255, 0.1)',
                borderWidth: 2,
                pointRadius: 3,
                pointBackgroundColor: '#6c63ff',
                tension: 0.1,
                fill: true,
            }
        ];

        if (projPrices.length > 1) {
            datasets.push({
                label: 'Projection',
                data: projLabels.map((l, i) => ({ x: l, y: projPrices[i] })),
                borderColor: '#6c63ff',
                borderWidth: 2,
                borderDash: [5, 5],
                pointRadius: 0,
                tension: 0.1,
                fill: false,
            });
        }

        chartInstances[canvasId] = new Chart(canvas, {
            type: 'line',
            data: { datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        type: 'category',
                        labels: allLabels,
                        ticks: { color: 'rgba(255,255,255,0.4)', font: { size: 10 }, maxTicksLimit: 8 },
                        grid: { color: 'rgba(255,255,255,0.05)' },
                    },
                    y: {
                        ticks: {
                            color: 'rgba(255,255,255,0.4)',
                            font: { size: 10 },
                            callback: v => v + '€',
                        },
                        grid: { color: 'rgba(255,255,255,0.05)' },
                    }
                },
                plugins: {
                    legend: { display: true, labels: { color: 'rgba(255,255,255,0.5)', font: { size: 10 } } },
                    tooltip: {
                        callbacks: {
                            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y}€`
                        }
                    }
                }
            }
        });
    } catch (e) {
        console.error('Chart error:', e);
    }
}

function linearRegression(points) {
    const n = points.length;
    let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
    for (const p of points) {
        sumX += p.x;
        sumY += p.y;
        sumXY += p.x * p.y;
        sumX2 += p.x * p.x;
    }
    const denom = n * sumX2 - sumX * sumX;
    if (denom === 0) return { slope: 0, intercept: sumY / n };
    const slope = (n * sumXY - sumX * sumY) / denom;
    const intercept = (sumY - slope * sumX) / n;
    return { slope, intercept };
}

// ── Unpin ──
async function unpinFlight(pinId) {
    try {
        await API.deletePin(pinId);
        allPins = allPins.filter(p => p.id !== pinId);
        renderPins();
        Toast.success('Flight unpinned');
    } catch (e) {
        Toast.error('Unpin failed: ' + e.message);
    }
}

// ── Alert section ──
function renderAlertSection(pin) {
    const alertCount = pin.alerts ? pin.alerts.length : 0;
    const alertsList = (pin.alerts || []).map(a => {
        const text = describeAlert(a);
        const enabledIcon = a.enabled ? '●' : '○';
        const enabledColor = a.enabled ? 'var(--green)' : 'var(--text-muted)';
        return `
        <div class="alert-rule">
            <span style="color:${enabledColor};font-size:0.6rem">${enabledIcon}</span>
            <span class="alert-rule-text">${text}</span>
            <span class="alert-rule-cooldown">${formatCooldown(a.cooldown)}</span>
            <span class="alert-rule-actions">
                <button class="alert-toggle-btn" onclick="toggleAlert(${pin.id}, ${a.id}, ${!a.enabled})" title="${a.enabled ? 'Disable' : 'Enable'}">${a.enabled ? 'Pause' : 'Resume'}</button>
                <button class="alert-delete-btn" onclick="deleteAlert(${pin.id}, ${a.id})">Delete</button>
            </span>
        </div>`;
    }).join('');

    return `
    <div class="pin-alerts-section">
        <div class="pin-alerts-header" onclick="toggleAlertSection(this)">
            <span class="pin-alerts-title">Alerts (${alertCount})</span>
            <span class="pin-alerts-toggle">▼</span>
        </div>
        <div class="pin-alerts-body">
            ${alertsList}
            <button class="btn-sm btn-accent" style="margin-top:8px" onclick="showAlertForm(${pin.id}, this)">+ Add Alert</button>
        </div>
    </div>`;
}

function describeAlert(a) {
    if (a.alert_type === 'threshold') {
        const op = a.operator === 'lt' ? '<' : '>';
        const unit = a.value_is_percent ? '%' : '€';
        return `Price ${op} ${a.value}${unit}`;
    }
    if (a.alert_type === 'variation') {
        return `Price changes by more than ${a.value}%`;
    }
    if (a.alert_type === 'trend_start') {
        return `Price starts ${a.operator === 'decrease' ? 'decreasing' : 'increasing'}`;
    }
    return a.alert_type;
}

function formatCooldown(c) {
    const map = {
        'once_only': 'Once',
        'every_scan': 'Every scan',
        'once_per_day': 'Daily',
        'once_per_week': 'Weekly',
    };
    return map[c] || c;
}

function toggleAlertSection(header) {
    const body = header.nextElementSibling;
    body.classList.toggle('open');
    const toggle = header.querySelector('.pin-alerts-toggle');
    toggle.textContent = body.classList.contains('open') ? '▲' : '▼';
}

function showAlertForm(pinId, btn) {
    const existing = btn.parentElement.querySelector('.alert-form');
    if (existing) { existing.remove(); return; }

    const form = document.createElement('div');
    form.className = 'alert-form';
    form.innerHTML = `
        <select id="alertType_${pinId}" onchange="updateAlertFormFields(${pinId})">
            <option value="threshold">Threshold</option>
            <option value="variation">Variation %</option>
            <option value="trend_start">Trend</option>
        </select>
        <span id="alertFields_${pinId}" style="display:contents">
            <select id="alertOp_${pinId}"><option value="lt">&lt;</option><option value="gt">&gt;</option></select>
            <input type="number" id="alertVal_${pinId}" placeholder="60" step="1">
            <label style="display:flex;align-items:center;gap:2px"><input type="checkbox" id="alertPct_${pinId}">%</label>
        </span>
        <select id="alertCooldown_${pinId}">
            <option value="every_scan">Every scan</option>
            <option value="once_per_day">Daily</option>
            <option value="once_per_week">Weekly</option>
            <option value="once_only">Once</option>
        </select>
        <button class="btn-sm btn-accent" onclick="saveNewAlert(${pinId})">Save</button>
        <button class="btn-sm btn-ghost" onclick="this.closest('.alert-form').remove()">✕</button>
    `;
    btn.parentElement.appendChild(form);
}

function updateAlertFormFields(pinId) {
    const type = document.getElementById(`alertType_${pinId}`).value;
    const container = document.getElementById(`alertFields_${pinId}`);
    if (type === 'threshold') {
        container.innerHTML = `
            <select id="alertOp_${pinId}"><option value="lt">&lt;</option><option value="gt">&gt;</option></select>
            <input type="number" id="alertVal_${pinId}" placeholder="60" step="1">
            <label style="display:flex;align-items:center;gap:2px"><input type="checkbox" id="alertPct_${pinId}">%</label>`;
    } else if (type === 'variation') {
        container.innerHTML = `<input type="number" id="alertVal_${pinId}" placeholder="10" step="1"><label>%</label>`;
    } else if (type === 'trend_start') {
        container.innerHTML = `<select id="alertOp_${pinId}"><option value="decrease">↓ Decreasing</option><option value="increase">↑ Increasing</option></select>`;
    }
}

async function saveNewAlert(pinId) {
    const type = document.getElementById(`alertType_${pinId}`).value;
    const data = {
        alert_type: type,
        logic_group: 0,
        cooldown: document.getElementById(`alertCooldown_${pinId}`).value,
        enabled: true,
    };

    if (type === 'threshold') {
        data.operator = document.getElementById(`alertOp_${pinId}`).value;
        data.value = parseFloat(document.getElementById(`alertVal_${pinId}`).value);
        const pctEl = document.getElementById(`alertPct_${pinId}`);
        data.value_is_percent = pctEl ? pctEl.checked : false;
    } else if (type === 'variation') {
        data.value = parseFloat(document.getElementById(`alertVal_${pinId}`).value);
    } else if (type === 'trend_start') {
        data.operator = document.getElementById(`alertOp_${pinId}`).value;
    }

    try {
        await API.createPinAlert(pinId, data);
        Toast.success('Alert created');
        await loadPins();
    } catch (e) {
        Toast.error('Failed: ' + e.message);
    }
}

async function toggleAlert(pinId, alertId, enabled) {
    try {
        await API.updatePinAlert(pinId, alertId, { enabled });
        await loadPins();
    } catch (e) {
        Toast.error('Failed: ' + e.message);
    }
}

async function deleteAlert(pinId, alertId) {
    try {
        await API.deletePinAlert(pinId, alertId);
        Toast.success('Alert deleted');
        await loadPins();
    } catch (e) {
        Toast.error('Failed: ' + e.message);
    }
}

// ── Boot ──
document.addEventListener('DOMContentLoaded', init);
