/* === FlyCal — App Controller === */

let currentSearchId = null;
let allFlights = [];
let selectedOutbound = null;
let selectedReturn = null;
let pollingTimer = null;
let appSettings = null;
let cityList = [];
let airlinesList = [];
let isSearching = false;

// ── Init ──
async function init() {
    setDefaultDates();
    await Promise.all([
        loadCityList(),
        loadAirlineToggles(),
        loadCrawlerStatus(),
        loadSettingsForApp(),
    ]);
    handleUrlParams();
    if (!currentSearchId) {
        await autoLaunchLastSearch();
    }
}

function setDefaultDates() {
    const today = new Date();
    const nextMonth = new Date(today);
    nextMonth.setMonth(nextMonth.getMonth() + 1);
    document.getElementById('dateFrom').value = formatDateISO(today);
    document.getElementById('dateTo').value = formatDateISO(nextMonth);
}

function formatDateISO(d) {
    return d.getFullYear() + '-' +
        String(d.getMonth() + 1).padStart(2, '0') + '-' +
        String(d.getDate()).padStart(2, '0');
}

async function loadSettingsForApp() {
    try {
        appSettings = await API.getSettings();
    } catch (e) {
        appSettings = { ideal_price: 100, time_slots: [] };
    }
}

// ── Airline toggles in search bar ──
async function loadAirlineToggles() {
    try {
        airlinesList = await API.getAirlines();
        const container = document.getElementById('airlineToggles');
        container.innerHTML = airlinesList
            .filter(a => a.enabled)
            .map(a => {
                const logoHtml = a.logo_url
                    ? `<img src="${a.logo_url}" alt="${a.name}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`
                    : '';
                const abbrev = (a.name || '??').substring(0, 2).toUpperCase();
                return `<div class="airline-toggle active" data-airline="${a.name}" onclick="toggleAirline(this)" title="${a.name}">
                    ${logoHtml}
                    <span class="at-abbrev" ${a.logo_url ? 'style="display:none"' : ''}>${abbrev}</span>
                </div>`;
            }).join('');
    } catch (e) {
        console.error('Failed to load airline toggles:', e);
    }
}

function toggleAirline(el) {
    el.classList.toggle('active');
}

function getSelectedAirlines() {
    const toggles = document.querySelectorAll('.airline-toggle.active');
    const names = [];
    toggles.forEach(t => names.push(t.dataset.airline));
    return names;
}

// ── City list for autocomplete (from all scrapers CITY_AIRPORT_MAP) ──
async function loadCityList() {
    try {
        // Build a static city list from known cities
        cityList = [
            'PARIS', 'MARRAKECH', 'CASABLANCA', 'NADOR', 'OUJDA', 'TANGIER', 'FEZ',
            'AGADIR', 'RABAT', 'ESSAOUIRA', 'LYON', 'MARSEILLE', 'TOULOUSE', 'BORDEAUX',
            'NANTES', 'NICE', 'MONTPELLIER', 'LILLE', 'STRASBOURG', 'LONDON', 'MADRID',
            'BARCELONA', 'ROME', 'MILAN', 'AMSTERDAM', 'BRUSSELS', 'BERLIN', 'FRANKFURT',
            'LISBON', 'PORTO', 'MALAGA', 'SEVILLE', 'VALENCIA', 'DUBLIN', 'EDINBURGH',
            'MANCHESTER', 'BIRMINGHAM', 'GLASGOW', 'BRISTOL', 'LIVERPOOL',
            'DUSSELDORF', 'MUNICH', 'HAMBURG', 'COLOGNE', 'VIENNA', 'ZURICH', 'GENEVA',
            'COPENHAGEN', 'STOCKHOLM', 'OSLO', 'HELSINKI', 'WARSAW', 'PRAGUE', 'BUDAPEST',
            'ATHENS', 'ISTANBUL', 'CAIRO', 'TUNIS',
        ];
        const datalist = document.getElementById('cityList');
        datalist.innerHTML = cityList.map(c => `<option value="${c}">`).join('');
    } catch (e) {
        console.error('Failed to load city list:', e);
    }
}

// ── Crawler toggle from header ──
async function toggleCrawlerFromHeader() {
    try {
        await API.toggleCrawler();
        await loadCrawlerStatus();
    } catch (e) {
        console.error('Failed to toggle crawler:', e);
    }
}

async function loadCrawlerStatus() {
    try {
        const status = await API.getCrawlerStatus();
        const dot = document.getElementById('crawlerDot');
        const label = document.getElementById('crawlerLabel');
        if (dot && label) {
            dot.className = 'crawler-dot ' + (status.enabled ? 'active' : 'inactive');
            label.textContent = status.enabled ? 'Stay Updated ON' : 'On-demand Only';
        }
    } catch (e) {}
}

// ── URL params handling ──
function handleUrlParams() {
    const params = new URLSearchParams(window.location.search);
    if (params.has('origin')) {
        document.getElementById('originCity').value = (params.get('origin') || '').toUpperCase();
        document.getElementById('destinationCity').value = (params.get('destination') || '').toUpperCase();
        document.getElementById('dateFrom').value = params.get('date_from') || '';
        document.getElementById('dateTo').value = params.get('date_to') || '';

        if (params.get('autorun') === '1') {
            window.history.replaceState({}, '', '/');
            // Explicit user action via URL — bypass sessionStorage check
            setTimeout(() => launchSearch(), 300);
        }
    }
}

// ── Auto-launch last search (only on first load per session) ──
async function autoLaunchLastSearch() {
    // Only auto-launch once per browser session
    if (sessionStorage.getItem('flycal_launched')) return;

    try {
        const data = await API.getLastSearch();
        if (data && data.origin_city) {
            document.getElementById('originCity').value = (data.origin_city || '').toUpperCase();
            document.getElementById('destinationCity').value = (data.destination_city || '').toUpperCase();
            if (data.date_from) document.getElementById('dateFrom').value = data.date_from;
            if (data.date_to) document.getElementById('dateTo').value = data.date_to;
            sessionStorage.setItem('flycal_launched', '1');
            launchSearch();
        }
    } catch (e) {
        console.error('Failed to auto-launch last search:', e);
    }
}

// ── City input: force uppercase ──
document.addEventListener('DOMContentLoaded', () => {
    ['originCity', 'destinationCity'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', () => {
                el.value = el.value.toUpperCase();
            });
        }
    });
    // Auto-show date picker on click
    ['dateFrom', 'dateTo'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('click', () => {
                if (el.showPicker) el.showPicker();
            });
        }
    });
});

// ── Search ──
async function launchSearch() {
    // Prevent multiple concurrent searches
    if (isSearching) {
        console.log('[FlyCal] Search already in progress, ignoring.');
        return;
    }

    const origin = document.getElementById('originCity').value.trim().toUpperCase();
    const destination = document.getElementById('destinationCity').value.trim().toUpperCase();
    const dateFrom = document.getElementById('dateFrom').value;
    const dateTo = document.getElementById('dateTo').value;

    if (!origin || !destination || !dateFrom || !dateTo) {
        alert('Please fill in all search fields.');
        return;
    }

    isSearching = true;

    // Grey out search bar, show progress band
    const searchBar = document.getElementById('searchBar');
    const progressBand = document.getElementById('searchProgressBand');
    const progressText = document.getElementById('progressText');
    searchBar.classList.add('greyed-out');
    progressBand.classList.remove('hidden');
    progressText.textContent = `${origin} → ${destination} | ${dateFrom} → ${dateTo}`;

    const btn = document.getElementById('btnSearch');
    btn.disabled = true;

    selectedOutbound = null;
    selectedReturn = null;
    allFlights = [];
    renderFlights();

    try {
        const result = await API.launchSearch({
            origin_city: origin,
            destination_city: destination,
            date_from: dateFrom,
            date_to: dateTo,
            trip_type: 'roundtrip',
            airlines: getSelectedAirlines(),
        });

        currentSearchId = result.search_id;
        console.log(`[FlyCal Crawler] Search started: #${result.search_id} ${origin}→${destination}`);
        startPolling(result.search_id);
    } catch (e) {
        alert('Search error: ' + e.message);
        isSearching = false;
        searchBar.classList.remove('greyed-out');
        progressBand.classList.add('hidden');
        btn.disabled = false;
    }
}

// ── Cancel search ──
async function cancelSearch() {
    try {
        await API.cancelSearch();
        console.log('[FlyCal Crawler] Search cancelled');
    } catch (e) {
        console.error('Cancel failed:', e);
    }
    if (pollingTimer) {
        clearInterval(pollingTimer);
        pollingTimer = null;
    }
    hideSearchingState();
}

// ── Polling ──
function startPolling(searchId) {
    if (pollingTimer) clearInterval(pollingTimer);
    let prevFlightCount = 0;

    console.log(`[FlyCal Crawler] Polling started for search #${searchId}`);

    pollingTimer = setInterval(async () => {
        try {
            const data = await API.getLastSearch();
            const status = await API.getCrawlerStatus();
            const done = status && status.last_run && status.last_run.status !== 'running';

            const flightCount = data && data.flights ? data.flights.length : 0;
            if (flightCount !== prevFlightCount) {
                console.log(`[FlyCal Crawler] Poll: ${flightCount} flights found (${done ? 'complete' : 'running'})`);
                if (flightCount > prevFlightCount && prevFlightCount > 0) {
                    console.log(`[FlyCal Crawler] New flights detected: +${flightCount - prevFlightCount}`);
                }
                prevFlightCount = flightCount;
            }

            if (data && data.flights && data.flights.length > 0) {
                allFlights = data.flights;
                renderFlights();
                autoSelectBestFlights();
                if (done) {
                    console.log(`[FlyCal Crawler] Search complete: ${allFlights.length} total flights`);
                    clearInterval(pollingTimer);
                    pollingTimer = null;
                    hideSearchingState();
                }
            } else if (done) {
                allFlights = data ? (data.flights || []) : [];
                renderFlights();
                console.log(`[FlyCal Crawler] Search complete: ${allFlights.length} total flights`);
                clearInterval(pollingTimer);
                pollingTimer = null;
                hideSearchingState();
            }
        } catch (e) {
            console.error('Polling error:', e);
        }
    }, 3000);

    // Timeout after 5 minutes
    setTimeout(() => {
        if (pollingTimer) {
            console.log('[FlyCal Crawler] Search timed out after 5 minutes');
            clearInterval(pollingTimer);
            pollingTimer = null;
            hideSearchingState();
        }
    }, 300000);
}

function hideSearchingState() {
    isSearching = false;
    const searchBar = document.getElementById('searchBar');
    const progressBand = document.getElementById('searchProgressBand');
    const btn = document.getElementById('btnSearch');
    searchBar.classList.remove('greyed-out');
    progressBand.classList.add('hidden');
    btn.disabled = false;
}

// ── Auto-select best flights: earliest outbound, latest return ──
function autoSelectBestFlights() {
    if (selectedOutbound && selectedReturn) return;

    const outbound = allFlights.filter(f => f.direction === 'outbound');
    const ret = allFlights.filter(f => f.direction === 'return');

    if (outbound.length > 0 && !selectedOutbound) {
        // Earliest outbound: sort by date then time
        const sorted = [...outbound].sort((a, b) => {
            if (a.flight_date !== b.flight_date) return a.flight_date.localeCompare(b.flight_date);
            return (a.departure_time || '').localeCompare(b.departure_time || '');
        });
        selectedOutbound = sorted[0];
    }

    if (ret.length > 0 && !selectedReturn) {
        // Latest return: sort by date desc then time desc
        const sorted = [...ret].sort((a, b) => {
            if (a.flight_date !== b.flight_date) return b.flight_date.localeCompare(a.flight_date);
            return (b.departure_time || '').localeCompare(a.departure_time || '');
        });
        selectedReturn = sorted[0];
    }

    renderFlights();
}

// ── Week separator helper ──
function getMondayOfWeek(dateStr) {
    const d = new Date(dateStr + 'T00:00:00');
    const day = d.getDay(); // 0=Sun, 1=Mon, ...
    const diff = d.getDate() - day + (day === 0 ? -6 : 1); // Monday
    const monday = new Date(d);
    monday.setDate(diff);
    return monday;
}

function formatWeekLabel(mondayDate) {
    const dd = String(mondayDate.getDate()).padStart(2, '0');
    const mm = String(mondayDate.getMonth() + 1).padStart(2, '0');
    return `Week of ${dd}/${mm}`;
}

// ── Render flights with vertical calendar layout ──
function renderFlights() {
    const outbound = allFlights.filter(f => f.direction === 'outbound');
    const ret = allFlights.filter(f => f.direction === 'return');

    // Collect all dates
    const allDates = new Set();
    outbound.forEach(f => allDates.add(f.flight_date));
    ret.forEach(f => allDates.add(f.flight_date));
    const sortedDates = [...allDates].sort();

    const outContainer = document.getElementById('listOutbound');
    const retContainer = document.getElementById('listReturn');
    const calStrip = document.getElementById('calendarStrip');
    const emptyOut = document.getElementById('emptyOutbound');
    const emptyRet = document.getElementById('emptyReturn');

    if (sortedDates.length === 0) {
        outContainer.innerHTML = '';
        retContainer.innerHTML = '';
        calStrip.innerHTML = '';
        if (emptyOut) { emptyOut.classList.remove('hidden'); outContainer.appendChild(emptyOut); }
        if (emptyRet) { emptyRet.classList.remove('hidden'); retContainer.appendChild(emptyRet); }
        updateRecap();
        return;
    }

    if (emptyOut) emptyOut.classList.add('hidden');
    if (emptyRet) emptyRet.classList.add('hidden');

    // Group by date
    const outByDate = {};
    const retByDate = {};
    outbound.forEach(f => { (outByDate[f.flight_date] = outByDate[f.flight_date] || []).push(f); });
    ret.forEach(f => { (retByDate[f.flight_date] = retByDate[f.flight_date] || []).push(f); });

    let outHtml = '';
    let calHtml = '';
    let retHtml = '';
    let prevMonday = null;

    for (const dateKey of sortedDates) {
        // Week separator
        const currentMonday = getMondayOfWeek(dateKey);
        const currentMondayStr = formatDateISO(currentMonday);
        if (prevMonday === null || currentMondayStr !== prevMonday) {
            if (prevMonday !== null) {
                // Insert week separator in all 3 columns
                const weekLabel = formatWeekLabel(currentMonday);
                outHtml += `<div class="week-separator"><span>${weekLabel}</span></div>`;
                calHtml += `<div class="week-separator"><span>${weekLabel}</span></div>`;
                retHtml += `<div class="week-separator"><span>${weekLabel}</span></div>`;
            }
            prevMonday = currentMondayStr;
        }

        const dayFlightsOut = (outByDate[dateKey] || []).sort((a, b) =>
            (a.departure_time || '').localeCompare(b.departure_time || '')
        );
        const dayFlightsRet = (retByDate[dateKey] || []).sort((a, b) =>
            (a.departure_time || '').localeCompare(b.departure_time || '')
        );

        // Determine dim state
        const isDimForOutbound = selectedReturn && dateKey > selectedReturn.flight_date;
        const isDimForReturn = selectedOutbound && dateKey < selectedOutbound.flight_date;

        // Calendar column
        const d = new Date(dateKey + 'T00:00:00');
        const dayName = d.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
        const dayNum = d.getDate();
        const monthName = d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();

        calHtml += `<div class="cal-day-cell" data-date="${dateKey}">
            <span class="cal-day-name">${dayName}</span>
            <span class="cal-day-num">${dayNum}</span>
            <span class="cal-month">${monthName}</span>
        </div>`;

        // Outbound flights for this day
        outHtml += `<div class="day-row${isDimForOutbound ? ' dimmed' : ''}" data-date="${dateKey}">`;
        if (dayFlightsOut.length > 0) {
            outHtml += renderDayFlights(dayFlightsOut, 'outbound', isDimForOutbound);
        }
        outHtml += `</div>`;

        // Return flights for this day
        retHtml += `<div class="day-row${isDimForReturn ? ' dimmed' : ''}" data-date="${dateKey}">`;
        if (dayFlightsRet.length > 0) {
            retHtml += renderDayFlights(dayFlightsRet, 'return', isDimForReturn);
        }
        retHtml += `</div>`;
    }

    outContainer.innerHTML = outHtml;
    calStrip.innerHTML = calHtml;
    retContainer.innerHTML = retHtml;

    updateRecap();
}

function renderDayFlights(flights, direction, isDimmed) {
    let html = '';
    for (const f of flights) {
        const color = appSettings ? getFlightColor(f, appSettings) : 'orange';
        const isSelected = (direction === 'outbound' && selectedOutbound && selectedOutbound.id === f.id) ||
                          (direction === 'return' && selectedReturn && selectedReturn.id === f.id);
        const duration = calculateDuration(f.departure_time, f.arrival_time);
        const abbrev = airlineAbbrev(f.airline_name);

        html += `<div class="flight-row color-${color}${isSelected ? ' selected' : ''}${isDimmed ? ' dim' : ''}"
                      data-flight-id="${f.id}"
                      onclick="handleFlightClick(${f.id}, '${direction}')"
                      onmouseenter="showPriceHistory(this, ${f.id})"
                      onmouseleave="hidePriceHistory(this)">`;

        // Compact single-line: logo | times | airports | price | oldest price
        if (f.airline_logo_url) {
            html += `<img src="${f.airline_logo_url}" alt="${f.airline_name}" class="flight-row-logo" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`;
            html += `<span class="flight-row-abbrev" style="display:none">${abbrev}</span>`;
        } else {
            html += `<span class="flight-row-abbrev">${abbrev}</span>`;
        }

        html += `<span class="flight-row-times">${f.departure_time || '--:--'} → ${f.arrival_time || '--:--'}</span>`;
        if (duration) {
            html += `<span class="flight-row-duration">${duration}</span>`;
        }
        html += `<span class="flight-row-airports">${f.origin_airport || '???'}→${f.destination_airport || '???'}</span>`;
        html += `<span class="flight-row-price">${Math.round(f.price)}€</span>`;

        // Oldest recorded price (only if ≥2 history entries)
        if (f.oldest_price != null && f.oldest_price !== f.price) {
            const diff = f.price - f.oldest_price;
            const arrow = diff < 0 ? '↓' : '↑';
            const cls = diff < 0 ? 'price-down' : 'price-up';
            html += `<span class="flight-row-old-price ${cls}">${arrow} ${Math.round(f.oldest_price)}€ (${f.oldest_price_date})</span>`;
        }

        html += `<div class="price-history-dropdown hidden"></div>`;
        html += `</div>`;
    }
    return html;
}

// ── Price history hover ──
async function showPriceHistory(el, flightId) {
    const dropdown = el.querySelector('.price-history-dropdown');
    if (!dropdown) return;
    try {
        const history = await API.getPriceHistory(flightId);
        if (history && history.length > 1) {
            dropdown.innerHTML = history.map(h => {
                const date = new Date(h.recorded_at);
                const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
                return `<div class="ph-entry"><span class="ph-date">${dateStr}</span><span class="ph-price">${Math.round(h.price)}€</span></div>`;
            }).join('');
            dropdown.classList.remove('hidden');
        }
    } catch (e) {}
}

function hidePriceHistory(el) {
    const dropdown = el.querySelector('.price-history-dropdown');
    if (dropdown) dropdown.classList.add('hidden');
}

// ── Flight click ──
function handleFlightClick(flightId, direction) {
    const flight = allFlights.find(f => f.id === flightId);
    if (!flight) return;

    if (direction === 'outbound') {
        selectedOutbound = (selectedOutbound && selectedOutbound.id === flightId) ? null : flight;
    } else {
        selectedReturn = (selectedReturn && selectedReturn.id === flightId) ? null : flight;
    }

    renderFlights();
}

// ── Recap banner ──
function updateRecap() {
    const banner = document.getElementById('recapBanner');
    const outDetail = document.getElementById('recapOutDetail');
    const retDetail = document.getElementById('recapRetDetail');
    const totalEl = document.getElementById('recapTotal');
    const daysEl = document.getElementById('recapDays');
    const breakdownEl = document.getElementById('recapBreakdown');

    if (!selectedOutbound && !selectedReturn) {
        banner.classList.add('hidden');
        return;
    }

    banner.classList.remove('hidden');

    let totalBase = 0;
    let totalFixed = 0;
    let totalPercent = 0;

    if (selectedOutbound) {
        const f = selectedOutbound;
        outDetail.textContent = `${f.airline_name} ${f.departure_time}→${f.arrival_time} ${Math.round(f.price)}€`;
        const base = f.price;
        const fixedFees = f.airline_fees_fixed || 0;
        const pctFees = base * (f.airline_fees_percent || 0) / 100;
        totalBase += base;
        totalFixed += fixedFees;
        totalPercent += pctFees;
    } else {
        outDetail.textContent = '—';
    }

    if (selectedReturn) {
        const f = selectedReturn;
        retDetail.textContent = `${f.airline_name} ${f.departure_time}→${f.arrival_time} ${Math.round(f.price)}€`;
        const base = f.price;
        const fixedFees = f.airline_fees_fixed || 0;
        const pctFees = base * (f.airline_fees_percent || 0) / 100;
        totalBase += base;
        totalFixed += fixedFees;
        totalPercent += pctFees;
    } else {
        retDetail.textContent = '—';
    }

    // Trip days (excluding flight days)
    if (selectedOutbound && selectedReturn) {
        const outDate = new Date(selectedOutbound.flight_date + 'T00:00:00');
        const retDate = new Date(selectedReturn.flight_date + 'T00:00:00');
        const diffMs = retDate - outDate;
        const diffDays = Math.max(0, Math.round(diffMs / (1000 * 60 * 60 * 24)) - 1);
        daysEl.textContent = `${diffDays}d`;
    } else {
        daysEl.textContent = '—';
    }

    // Fee breakdown
    const grandTotal = totalBase + totalFixed + totalPercent;
    if (totalFixed > 0 || totalPercent > 0) {
        breakdownEl.textContent = `${Math.round(totalBase)}€ + ${Math.round(totalFixed)}€ fees + ${Math.round(totalPercent)}€ %`;
    } else {
        breakdownEl.textContent = '';
    }
    totalEl.textContent = `${Math.round(grandTotal)} €`;
}

document.addEventListener('DOMContentLoaded', init);
