/* === FlyCal — Tracks Page Controller === */

let allTracks = [];
const chartInstances = {};

async function init() { await loadTracks(); }

async function loadTracks() {
    try {
        allTracks = await API.getTracks();
        renderTracks();
    } catch (e) {
        document.getElementById('tracksContent').innerHTML =
            `<div class="tracks-empty">Failed to load tracks: ${e.message}</div>`;
    }
}

function renderTracks() {
    const c = document.getElementById('tracksContent');
    if (!allTracks.length) {
        c.innerHTML = '<div class="tracks-empty">No tracked flights yet.<br>Double-click or right-click a flight on the Scan page to track it.</div>';
        return;
    }
    c.innerHTML = `<div class="tracks-grid">${allTracks.map(renderTrackCard).join('')}</div>`;
    for (const track of allTracks) renderPriceChart(`chart-${track.id}`, track);
}

// ── Card ──
function renderTrackCard(track) {
    const cur = track.current_price != null ? Math.round(track.current_price) + '\u20ac' : '\u2014';
    const old = track.oldest_price != null ? Math.round(track.oldest_price) + '\u20ac' : '\u2014';
    const oldDate = track.oldest_price_date ? track.oldest_price_date.split('T')[0] : '';
    let chg = '';
    if (track.current_price != null && track.oldest_price != null && track.oldest_price !== track.current_price) {
        const d = track.current_price - track.oldest_price;
        const p = ((d / track.oldest_price) * 100).toFixed(0);
        chg = `<span class="track-change ${d < 0 ? 'down' : 'up'}">${d < 0 ? '\u2193' : '\u2191'}${Math.abs(Math.round(d))}\u20ac (${p}%)</span>`;
    }
    const dir = track.direction === 'outbound' ? 'OUT' : 'RET';

    const safeLogo = safeImgUrl(track.airline_logo_url);
    const safeName = escapeHtml(track.airline_name);
    const safeDir = escapeHtml(track.direction);
    return `
    <div class="track-card" data-track-id="${parseInt(track.id)}">
        <div class="track-top-band">
            ${safeLogo ? `<img src="${safeLogo}" class="track-logo" onerror="this.style.display='none'">` : ''}
            <span class="track-airline">${safeName}</span>
            <span class="track-dir ${safeDir}">${escapeHtml(dir)}</span>
            <span class="track-route">${escapeHtml(track.origin_airport)}\u2192${escapeHtml(track.destination_airport)}</span>
            <span class="track-sep">|</span>
            <span class="track-val">${track.flight_date} ${track.departure_time}</span>
            <span class="track-sep">|</span>
            <span class="track-val"><span class="track-lbl">Start</span><span class="track-num">${old}</span> <span style="color:var(--text-muted);font-size:0.6rem">${oldDate}</span></span>
            <span class="track-sep">|</span>
            <span class="track-val"><span class="track-lbl">Now</span><span class="track-num">${cur}</span>${chg}</span>
            <div class="track-actions">
                <button class="btn-sm btn-danger" onclick="untrackFlight(${track.id})">Untrack</button>
                <a href="/" class="btn-sm btn-ghost">Scan</a>
            </div>
        </div>
        <div class="track-chart"><canvas id="chart-${track.id}"></canvas></div>
        <div class="track-alerts" id="alerts-${track.id}">
            ${renderAlerts(track)}
        </div>
    </div>`;
}

// ── Alerts ──
function renderAlerts(track) {
    const existing = (track.alerts || []).map(a => {
        const dot = a.enabled ? '<span style="color:var(--green)">\u25cf</span>' : '<span style="color:var(--text-muted)">\u25cb</span>';
        return `<div class="alert-row">
            ${dot}
            <span class="alert-row-text">${describeAlert(a)}</span>
            <span class="alert-row-cd">${fmtCd(a.cooldown)}</span>
            <button class="abtn" onclick="toggleAlert(${track.id},${a.id},${!a.enabled})">${a.enabled ? 'Pause' : 'Resume'}</button>
            <button class="abtn del" onclick="deleteAlert(${track.id},${a.id})">&#x2715;</button>
        </div>`;
    }).join('');

    // Always show the inline add form
    return `${existing}
    <div class="alert-add" id="alertForm-${track.id}">
        <select id="aType-${track.id}" onchange="updateFields(${track.id})">
            <option value="threshold">Threshold</option>
            <option value="variation">Variation %</option>
            <option value="trend_start">Trend</option>
        </select>
        <span id="aFields-${track.id}" style="display:contents">
            <select id="aOp-${track.id}"><option value="lt">&lt;</option><option value="gt">&gt;</option></select>
            <input type="number" id="aVal-${track.id}" placeholder="60" step="1">
            <label><input type="checkbox" id="aPct-${track.id}">%</label>
        </span>
        <select id="aCd-${track.id}">
            <option value="every_scan">Every scan</option>
            <option value="once_per_day">Daily</option>
            <option value="once_per_week">Weekly</option>
            <option value="once_only">Once</option>
        </select>
        <button class="abtn add" onclick="saveAlert(${track.id})">+</button>
    </div>`;
}

function describeAlert(a) {
    if (a.alert_type === 'threshold') return `Price ${a.operator === 'lt' ? '<' : '>'} ${a.value}${a.value_is_percent ? '%' : '\u20ac'}`;
    if (a.alert_type === 'variation') return `Variation > ${a.value}%`;
    if (a.alert_type === 'trend_start') return `Trend ${a.operator === 'decrease' ? '\u2193' : '\u2191'}`;
    return a.alert_type;
}
function fmtCd(c) { return {once_only:'Once',every_scan:'Every scan',once_per_day:'Daily',once_per_week:'Weekly'}[c]||c; }

function updateFields(trackId) {
    const type = document.getElementById(`aType-${trackId}`).value;
    const c = document.getElementById(`aFields-${trackId}`);
    if (type === 'threshold') {
        c.innerHTML = `<select id="aOp-${trackId}"><option value="lt">&lt;</option><option value="gt">&gt;</option></select>
            <input type="number" id="aVal-${trackId}" placeholder="60" step="1">
            <label><input type="checkbox" id="aPct-${trackId}">%</label>`;
    } else if (type === 'variation') {
        c.innerHTML = `<input type="number" id="aVal-${trackId}" placeholder="10" step="1"><label>%</label>`;
    } else {
        c.innerHTML = `<select id="aOp-${trackId}"><option value="decrease">\u2193 Down</option><option value="increase">\u2191 Up</option></select>`;
    }
}

async function saveAlert(trackId) {
    const type = document.getElementById(`aType-${trackId}`).value;
    const data = { alert_type: type, logic_group: 0, cooldown: document.getElementById(`aCd-${trackId}`).value, enabled: true };
    if (type === 'threshold') {
        data.operator = document.getElementById(`aOp-${trackId}`).value;
        data.value = parseFloat(document.getElementById(`aVal-${trackId}`).value);
        const p = document.getElementById(`aPct-${trackId}`);
        data.value_is_percent = p ? p.checked : false;
    } else if (type === 'variation') {
        data.value = parseFloat(document.getElementById(`aVal-${trackId}`).value);
    } else {
        data.operator = document.getElementById(`aOp-${trackId}`).value;
    }
    try { await API.createTrackAlert(trackId, data); Toast.success('Alert added'); await loadTracks(); }
    catch (e) { Toast.error(e.message); }
}

async function toggleAlert(trackId, alertId, enabled) {
    try { await API.updateTrackAlert(trackId, alertId, { enabled }); await loadTracks(); }
    catch (e) { Toast.error(e.message); }
}

async function deleteAlert(trackId, alertId) {
    try { await API.deleteTrackAlert(trackId, alertId); Toast.success('Alert removed'); await loadTracks(); }
    catch (e) { Toast.error(e.message); }
}

// ── Untrack ──
async function untrackFlight(trackId) {
    try { await API.deleteTrack(trackId); allTracks = allTracks.filter(t => t.id !== trackId); renderTracks(); Toast.success('Untracked'); }
    catch (e) { Toast.error(e.message); }
}

// ── Chart ──
async function renderPriceChart(canvasId, track) {
    try {
        const data = await API.getTrackPriceHistory(track.id);
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        if (!data.length) { canvas.parentElement.innerHTML = '<div class="track-chart-empty">No price data yet</div>'; return; }

        const fmtDate = iso => { const d = new Date(iso); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
        const labels = data.map(d => fmtDate(d.recorded_at));
        const prices = data.map(d => d.price);

        // Projection (>= 2 points)
        let projLabels = [], projPrices = [];
        if (data.length >= 2) {
            const reg = linReg(data.map((d, i) => ({ x: i, y: d.price })));
            const last = new Date(data[data.length - 1].recorded_at);
            const flight = new Date(track.flight_date + 'T00:00:00');
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
            label: 'Price (\u20ac)', data: labels.map((l, i) => ({ x: l, y: prices[i] })),
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
                    y: { ticks: { color: 'rgba(255,255,255,0.3)', font: { size: 9 }, callback: v => v + '\u20ac' },
                        grid: { color: 'rgba(255,255,255,0.04)' } }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: ctx => ctx.dataset.label + ': ' + ctx.parsed.y + '\u20ac' } }
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
