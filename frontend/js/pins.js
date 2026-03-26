/* === FlyCal — Pins Page Controller === */

let allPins = [];
const chartInstances = {};

async function init() { await loadPins(); }

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
    const c = document.getElementById('pinsContent');
    if (!allPins.length) {
        c.innerHTML = '<div class="pins-empty">No pinned flights yet.<br>Double-click or right-click a flight on the Scan page to pin it.</div>';
        return;
    }
    c.innerHTML = `<div class="pins-grid">${allPins.map(renderPinCard).join('')}</div>`;
    for (const pin of allPins) renderPriceChart(`chart-${pin.id}`, pin);
}

// ── Card ──
function renderPinCard(pin) {
    const cur = pin.current_price != null ? Math.round(pin.current_price) + '€' : '—';
    const old = pin.oldest_price != null ? Math.round(pin.oldest_price) + '€' : '—';
    const oldDate = pin.oldest_price_date ? pin.oldest_price_date.split('T')[0] : '';
    let chg = '';
    if (pin.current_price != null && pin.oldest_price != null && pin.oldest_price !== pin.current_price) {
        const d = pin.current_price - pin.oldest_price;
        const p = ((d / pin.oldest_price) * 100).toFixed(0);
        chg = `<span class="pin-change ${d < 0 ? 'down' : 'up'}">${d < 0 ? '↓' : '↑'}${Math.abs(Math.round(d))}€ (${p}%)</span>`;
    }
    const dir = pin.direction === 'outbound' ? 'OUT' : 'RET';

    return `
    <div class="pin-card" data-pin-id="${pin.id}">
        <div class="pin-top-band">
            ${pin.airline_logo_url ? `<img src="${pin.airline_logo_url}" class="pin-logo" onerror="this.style.display='none'">` : ''}
            <span class="pin-airline">${pin.airline_name}</span>
            <span class="pin-dir ${pin.direction}">${dir}</span>
            <span class="pin-route">${pin.origin_airport}→${pin.destination_airport}</span>
            <span class="pin-sep">|</span>
            <span class="pin-val">${pin.flight_date} ${pin.departure_time}</span>
            <span class="pin-sep">|</span>
            <span class="pin-val"><span class="pin-lbl">Start</span><span class="pin-num">${old}</span> <span style="color:var(--text-muted);font-size:0.6rem">${oldDate}</span></span>
            <span class="pin-sep">|</span>
            <span class="pin-val"><span class="pin-lbl">Now</span><span class="pin-num">${cur}</span>${chg}</span>
            <div class="pin-actions">
                <button class="btn-sm btn-danger" onclick="unpinFlight(${pin.id})">Unpin</button>
                <a href="/" class="btn-sm btn-ghost">Scan</a>
            </div>
        </div>
        <div class="pin-chart"><canvas id="chart-${pin.id}"></canvas></div>
        <div class="pin-alerts" id="alerts-${pin.id}">
            ${renderAlerts(pin)}
        </div>
    </div>`;
}

// ── Alerts ──
function renderAlerts(pin) {
    const existing = (pin.alerts || []).map(a => {
        const dot = a.enabled ? '<span style="color:var(--green)">●</span>' : '<span style="color:var(--text-muted)">○</span>';
        return `<div class="alert-row">
            ${dot}
            <span class="alert-row-text">${describeAlert(a)}</span>
            <span class="alert-row-cd">${fmtCd(a.cooldown)}</span>
            <button class="abtn" onclick="toggleAlert(${pin.id},${a.id},${!a.enabled})">${a.enabled ? 'Pause' : 'Resume'}</button>
            <button class="abtn del" onclick="deleteAlert(${pin.id},${a.id})">✕</button>
        </div>`;
    }).join('');

    // Always show the inline add form
    return `${existing}
    <div class="alert-add" id="alertForm-${pin.id}">
        <select id="aType-${pin.id}" onchange="updateFields(${pin.id})">
            <option value="threshold">Threshold</option>
            <option value="variation">Variation %</option>
            <option value="trend_start">Trend</option>
        </select>
        <span id="aFields-${pin.id}" style="display:contents">
            <select id="aOp-${pin.id}"><option value="lt">&lt;</option><option value="gt">&gt;</option></select>
            <input type="number" id="aVal-${pin.id}" placeholder="60" step="1">
            <label><input type="checkbox" id="aPct-${pin.id}">%</label>
        </span>
        <select id="aCd-${pin.id}">
            <option value="every_scan">Every scan</option>
            <option value="once_per_day">Daily</option>
            <option value="once_per_week">Weekly</option>
            <option value="once_only">Once</option>
        </select>
        <button class="abtn add" onclick="saveAlert(${pin.id})">+</button>
    </div>`;
}

function describeAlert(a) {
    if (a.alert_type === 'threshold') return `Price ${a.operator === 'lt' ? '<' : '>'} ${a.value}${a.value_is_percent ? '%' : '€'}`;
    if (a.alert_type === 'variation') return `Variation > ${a.value}%`;
    if (a.alert_type === 'trend_start') return `Trend ${a.operator === 'decrease' ? '↓' : '↑'}`;
    return a.alert_type;
}
function fmtCd(c) { return {once_only:'Once',every_scan:'Every scan',once_per_day:'Daily',once_per_week:'Weekly'}[c]||c; }

function updateFields(pinId) {
    const type = document.getElementById(`aType-${pinId}`).value;
    const c = document.getElementById(`aFields-${pinId}`);
    if (type === 'threshold') {
        c.innerHTML = `<select id="aOp-${pinId}"><option value="lt">&lt;</option><option value="gt">&gt;</option></select>
            <input type="number" id="aVal-${pinId}" placeholder="60" step="1">
            <label><input type="checkbox" id="aPct-${pinId}">%</label>`;
    } else if (type === 'variation') {
        c.innerHTML = `<input type="number" id="aVal-${pinId}" placeholder="10" step="1"><label>%</label>`;
    } else {
        c.innerHTML = `<select id="aOp-${pinId}"><option value="decrease">↓ Down</option><option value="increase">↑ Up</option></select>`;
    }
}

async function saveAlert(pinId) {
    const type = document.getElementById(`aType-${pinId}`).value;
    const data = { alert_type: type, logic_group: 0, cooldown: document.getElementById(`aCd-${pinId}`).value, enabled: true };
    if (type === 'threshold') {
        data.operator = document.getElementById(`aOp-${pinId}`).value;
        data.value = parseFloat(document.getElementById(`aVal-${pinId}`).value);
        const p = document.getElementById(`aPct-${pinId}`);
        data.value_is_percent = p ? p.checked : false;
    } else if (type === 'variation') {
        data.value = parseFloat(document.getElementById(`aVal-${pinId}`).value);
    } else {
        data.operator = document.getElementById(`aOp-${pinId}`).value;
    }
    try { await API.createPinAlert(pinId, data); Toast.success('Alert added'); await loadPins(); }
    catch (e) { Toast.error(e.message); }
}

async function toggleAlert(pinId, alertId, enabled) {
    try { await API.updatePinAlert(pinId, alertId, { enabled }); await loadPins(); }
    catch (e) { Toast.error(e.message); }
}

async function deleteAlert(pinId, alertId) {
    try { await API.deletePinAlert(pinId, alertId); Toast.success('Alert removed'); await loadPins(); }
    catch (e) { Toast.error(e.message); }
}

// ── Unpin ──
async function unpinFlight(pinId) {
    try { await API.deletePin(pinId); allPins = allPins.filter(p => p.id !== pinId); renderPins(); Toast.success('Unpinned'); }
    catch (e) { Toast.error(e.message); }
}

// ── Chart ──
async function renderPriceChart(canvasId, pin) {
    try {
        const data = await API.getPinPriceHistory(pin.id);
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        if (!data.length) { canvas.parentElement.innerHTML = '<div class="pin-chart-empty">No price data yet</div>'; return; }

        const fmtDate = iso => { const d = new Date(iso); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
        const labels = data.map(d => fmtDate(d.recorded_at));
        const prices = data.map(d => d.price);

        // Projection (>= 2 points)
        let projLabels = [], projPrices = [];
        if (data.length >= 2) {
            const reg = linReg(data.map((d, i) => ({ x: i, y: d.price })));
            const last = new Date(data[data.length - 1].recorded_at);
            const flight = new Date(pin.flight_date + 'T00:00:00');
            const days = Math.max(1, Math.min(Math.ceil((flight - last) / 86400000), 30));
            projLabels.push(labels[labels.length - 1]);
            projPrices.push(prices[prices.length - 1]);
            for (let s = 1; s <= days; s++) {
                const d = new Date(last.getTime() + s * 86400000);
                projLabels.push(fmtDate(d.toISOString()));
                projPrices.push(Math.max(0, Math.round((reg.b + reg.m * (data.length - 1 + s)) * 100) / 100));
            }
        }

        const allLabels = [...new Set([...labels, ...projLabels])];
        if (chartInstances[canvasId]) chartInstances[canvasId].destroy();

        const datasets = [{
            label: 'Price (€)', data: labels.map((l, i) => ({ x: l, y: prices[i] })),
            borderColor: '#6c63ff', backgroundColor: 'rgba(108,99,255,0.08)',
            borderWidth: 2, pointRadius: 3, pointBackgroundColor: '#6c63ff', tension: 0.3, fill: true,
        }];
        if (projPrices.length > 1) datasets.push({
            label: 'Projection', data: projLabels.map((l, i) => ({ x: l, y: projPrices[i] })),
            borderColor: 'rgba(108,99,255,0.5)', borderWidth: 2, borderDash: [6, 4],
            pointRadius: 0, tension: 0.3, fill: false,
        });

        chartInstances[canvasId] = new Chart(canvas, {
            type: 'line', data: { datasets },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { type: 'category', labels: allLabels,
                        ticks: { color: 'rgba(255,255,255,0.3)', font: { size: 9 }, maxTicksLimit: 6 },
                        grid: { color: 'rgba(255,255,255,0.04)' } },
                    y: { ticks: { color: 'rgba(255,255,255,0.3)', font: { size: 9 }, callback: v => v + '€' },
                        grid: { color: 'rgba(255,255,255,0.04)' } }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: ctx => ctx.dataset.label + ': ' + ctx.parsed.y + '€' } }
                }
            }
        });
    } catch (e) { console.error('Chart error:', e); }
}

function linReg(pts) {
    const n = pts.length;
    let sx = 0, sy = 0, sxy = 0, sx2 = 0;
    for (const p of pts) { sx += p.x; sy += p.y; sxy += p.x * p.y; sx2 += p.x * p.x; }
    const d = n * sx2 - sx * sx;
    if (d === 0) return { m: 0, b: sy / n };
    return { m: (n * sxy - sx * sy) / d, b: (sy * sx2 - sx * sxy) / d };
}

document.addEventListener('DOMContentLoaded', init);
