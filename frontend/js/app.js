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
let searchTimerInterval = null;
let searchStartTime = null;

// ── Init ──
async function init() {
    setDefaultDates();
    setupDateConstraints();
    await Promise.all([
        loadCityList(),
        loadAirlineToggles(),
        loadCrawlerStatus(),
        loadSettingsForApp(),
    ]);
    handleUrlParams();
    // Always load last search info (dates, airports, etc.)
    await loadLastSearchInfo();
    // Check if a background search is still running
    await checkForBackgroundSearch();
}

function setDefaultDates() {
    const today = new Date();
    const nextMonth = new Date(today);
    nextMonth.setMonth(nextMonth.getMonth() + 1);
    const dateFromEl = document.getElementById('dateFrom');
    const dateToEl = document.getElementById('dateTo');
    dateFromEl.value = formatDateISO(today);
    dateToEl.value = formatDateISO(nextMonth);
    // Set min attribute to prevent past dates
    dateFromEl.min = formatDateISO(today);
    dateToEl.min = formatDateISO(today);
}

function setupDateConstraints() {
    const dateFromEl = document.getElementById('dateFrom');
    const dateToEl = document.getElementById('dateTo');

    dateFromEl.addEventListener('change', () => {
        // Ensure return date is always after departure date
        if (dateFromEl.value) {
            const nextDay = new Date(dateFromEl.value + 'T00:00:00');
            nextDay.setDate(nextDay.getDate() + 1);
            dateToEl.min = formatDateISO(nextDay);
            if (dateToEl.value && dateToEl.value <= dateFromEl.value) {
                dateToEl.value = formatDateISO(nextDay);
            }
        }
    });

    dateToEl.addEventListener('change', () => {
        if (dateToEl.value && dateFromEl.value && dateToEl.value <= dateFromEl.value) {
            const nextDay = new Date(dateFromEl.value + 'T00:00:00');
            nextDay.setDate(nextDay.getDate() + 1);
            dateToEl.value = formatDateISO(nextDay);
        }
    });
}

function formatDateISO(d) {
    return d.getFullYear() + '-' +
        String(d.getMonth() + 1).padStart(2, '0') + '-' +
        String(d.getDate()).padStart(2, '0');
}

// ── Search timer & estimate ──
function startSearchTimer() {
    searchStartTime = Date.now();
    const timerEl = document.getElementById('searchTimer');
    const estimateEl = document.getElementById('searchEstimate');
    if (timerEl) timerEl.textContent = '⏱ 00:00';

    // Compute dynamic estimate based on date range × airlines
    if (estimateEl) {
        const dateFrom = document.getElementById('dateFrom').value;
        const dateTo = document.getElementById('dateTo').value;
        const activeAirlines = document.querySelectorAll('.airline-toggle.active').length || 1;
        let days = 30;
        if (dateFrom && dateTo) {
            const d1 = new Date(dateFrom + 'T00:00:00');
            const d2 = new Date(dateTo + 'T00:00:00');
            days = Math.max(1, Math.round((d2 - d1) / (1000 * 60 * 60 * 24)));
        }
        // ~3 seconds per day per airline (empirical estimate)
        const estimatedSec = Math.max(30, days * activeAirlines * 3);
        const estMin = Math.floor(estimatedSec / 60);
        const estSec = estimatedSec % 60;
        const estStr = estMin > 0
            ? `~${estMin}min${estSec > 0 ? ` ${estSec}s` : ''}`
            : `~${estSec}s`;
        estimateEl.textContent = `Estimated time: ${estStr} (${days} days × ${activeAirlines} airline${activeAirlines > 1 ? 's' : ''})`;
    }

    if (searchTimerInterval) clearInterval(searchTimerInterval);
    searchTimerInterval = setInterval(() => {
        if (!searchStartTime || !timerEl) return;
        const elapsed = Math.floor((Date.now() - searchStartTime) / 1000);
        const mm = String(Math.floor(elapsed / 60)).padStart(2, '0');
        const ss = String(elapsed % 60).padStart(2, '0');
        timerEl.textContent = `⏱ ${mm}:${ss}`;
    }, 1000);
}

function stopSearchTimer() {
    if (searchTimerInterval) {
        clearInterval(searchTimerInterval);
        searchTimerInterval = null;
    }
    searchStartTime = null;
}

// ── Search completion notification ──
function notifySearchComplete(flightCount) {
    const origin = document.getElementById('originCity').value.trim().toUpperCase();
    const destination = document.getElementById('destinationCity').value.trim().toUpperCase();
    const msg = `Search complete: ${origin} → ${destination} — ${flightCount} flight${flightCount !== 1 ? 's' : ''} found`;
    Toast.success(msg, 6000);
}

async function loadSettingsForApp() {
    try {
        appSettings = await API.getSettings();
    } catch (e) {
        appSettings = { ideal_price: 100, time_slots: [] };
    }
}

// ── Always load last search info ──
async function loadLastSearchInfo() {
    try {
        const data = await API.getLastSearch();
        if (data && data.origin_city) {
            document.getElementById('originCity').value = (data.origin_city || '').toUpperCase();
            document.getElementById('destinationCity').value = (data.destination_city || '').toUpperCase();
            if (data.date_from) document.getElementById('dateFrom').value = data.date_from;
            if (data.date_to) document.getElementById('dateTo').value = data.date_to;
            // If search already has results and not currently searching, show them
            if (data.flights && data.flights.length > 0 && !isSearching) {
                allFlights = data.flights;
                currentSearchId = data.id;
                renderFlights();
                autoSelectBestFlights();
            }
        }
    } catch (e) {
        console.error('Failed to load last search info:', e);
    }
}

// ── Check for background search (crawler running) ──
async function checkForBackgroundSearch() {
    try {
        const status = await API.getCrawlerStatus();
        if (status && status.last_run && status.last_run.status === 'running') {
            // A search is running in background, resume polling — clear old results
            const data = await API.getLastSearch();
            if (data && data.id) {
                isSearching = true;
                currentSearchId = data.id;
                allFlights = [];
                showSearchingState();
                startPolling(data.id);
                console.log(`[FlyCal Crawler] Resumed polling for background search #${data.id}`);
            }
        } else if (!isSearching) {
            // Only auto-launch on first session load
            if (!sessionStorage.getItem('flycal_launched') && !currentSearchId) {
                const data = await API.getLastSearch();
                if (data && data.origin_city) {
                    sessionStorage.setItem('flycal_launched', '1');
                    launchSearch();
                }
            }
        }
    } catch (e) {
        console.error('Failed to check background search:', e);
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
        const result = await API.toggleCrawler();
        await loadCrawlerStatus();
        await showCrawlerToggleNotification(result.enabled);
    } catch (e) {
        Toast.error('Failed to toggle crawler: ' + e.message);
    }
}

async function showCrawlerToggleNotification(enabled) {
    try {
        const status = await API.getCrawlerStatus();
        const target = status.target_search;
        let msg = enabled ? 'Crawler enabled' : 'Crawler disabled';
        if (enabled && target) {
            msg += ` for ${(target.origin_city||'').toUpperCase()} → ${(target.destination_city||'').toUpperCase()}`;
            if (status.next_run) {
                const next = new Date(status.next_run).toLocaleString('en-US', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' });
                msg += ` — Next run: ${next}`;
            }
        }
        if (enabled) Toast.success(msg, 6000);
        else Toast.info(msg);
    } catch(e) {}
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
            setTimeout(() => launchSearch(), 300);
        }
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

// ── Show/hide searching state ──
function showSearchingState() {
    const searchBar = document.getElementById('searchBar');
    const progressBand = document.getElementById('searchProgressBand');
    const centralLoader = document.getElementById('centralLoader');
    const gridHeader = document.getElementById('flightGridHeader');
    const flightGrid = document.getElementById('flightGrid');
    const btn = document.getElementById('btnSearch');
    searchBar.classList.add('greyed-out');
    progressBand.classList.remove('hidden');
    btn.disabled = true;
    // Always show central loader and clear flight grid during search
    if (centralLoader) centralLoader.classList.remove('hidden');
    if (gridHeader) gridHeader.classList.add('hidden');
    if (flightGrid) flightGrid.innerHTML = '';
    // Animate logo
    document.querySelectorAll('.logo-img').forEach(el => el.classList.add('logo-searching'));
    startSearchTimer();
}

function hideSearchingState() {
    isSearching = false;
    const searchBar = document.getElementById('searchBar');
    const progressBand = document.getElementById('searchProgressBand');
    const centralLoader = document.getElementById('centralLoader');
    const gridHeader = document.getElementById('flightGridHeader');
    const btn = document.getElementById('btnSearch');
    searchBar.classList.remove('greyed-out');
    progressBand.classList.add('hidden');
    btn.disabled = false;
    if (centralLoader) centralLoader.classList.add('hidden');
    if (gridHeader) gridHeader.classList.remove('hidden');
    // Stop logo animation
    document.querySelectorAll('.logo-img').forEach(el => el.classList.remove('logo-searching'));
    stopSearchTimer();
}

// ── Search ──
async function launchSearch() {
    if (isSearching) {
        console.log('[FlyCal] Search already in progress, ignoring.');
        return;
    }

    const origin = document.getElementById('originCity').value.trim().toUpperCase();
    const destination = document.getElementById('destinationCity').value.trim().toUpperCase();
    const dateFrom = document.getElementById('dateFrom').value;
    const dateTo = document.getElementById('dateTo').value;

    if (!origin || !destination || !dateFrom || !dateTo) {
        Toast.warning('Please fill in all search fields.');
        return;
    }

    isSearching = true;

    const progressText = document.getElementById('progressText');
    progressText.textContent = `${origin} → ${destination} | ${dateFrom} → ${dateTo}`;

    selectedOutbound = null;
    selectedReturn = null;
    allFlights = [];
    renderFlights();
    showSearchingState();

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
        Toast.error('Search error: ' + e.message);
        hideSearchingState();
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
            const lastRunStatus = status && status.last_run ? status.last_run.status : null;
            const done = lastRunStatus && lastRunStatus !== 'running';
            const wasCancelled = lastRunStatus === 'cancelled';

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
                // Hide central loader and show grid header once we have results
                const centralLoader = document.getElementById('centralLoader');
                const gridHeader = document.getElementById('flightGridHeader');
                if (centralLoader) centralLoader.classList.add('hidden');
                if (gridHeader) gridHeader.classList.remove('hidden');
                if (done) {
                    console.log(`[FlyCal Crawler] Search ${wasCancelled ? 'cancelled' : 'complete'}: ${allFlights.length} total flights`);
                    clearInterval(pollingTimer);
                    pollingTimer = null;
                    hideSearchingState();
                    if (wasCancelled) Toast.warning('Search cancelled');
                    else notifySearchComplete(allFlights.length);
                }
            } else if (done) {
                allFlights = data ? (data.flights || []) : [];
                renderFlights();
                console.log(`[FlyCal Crawler] Search ${wasCancelled ? 'cancelled' : 'complete'}: ${allFlights.length} total flights`);
                clearInterval(pollingTimer);
                pollingTimer = null;
                hideSearchingState();
                if (wasCancelled) Toast.warning('Search cancelled');
                else notifySearchComplete(allFlights.length);
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

// ── Auto-select best flights: earliest outbound, latest return ──
function autoSelectBestFlights() {
    if (selectedOutbound && selectedReturn) return;

    const outbound = allFlights.filter(f => f.direction === 'outbound');
    const ret = allFlights.filter(f => f.direction === 'return');

    if (outbound.length > 0 && !selectedOutbound) {
        const sorted = [...outbound].sort((a, b) => {
            if (a.flight_date !== b.flight_date) return a.flight_date.localeCompare(b.flight_date);
            return (a.departure_time || '').localeCompare(b.departure_time || '');
        });
        selectedOutbound = sorted[0];
    }

    if (ret.length > 0 && !selectedReturn) {
        const sorted = [...ret].sort((a, b) => {
            if (a.flight_date !== b.flight_date) return b.flight_date.localeCompare(a.flight_date);
            return (b.departure_time || '').localeCompare(a.departure_time || '');
        });
        selectedReturn = sorted[0];
    }

    renderFlights();
}

// ── Week helpers ──
function getISOWeekNumber(dateStr) {
    const d = new Date(dateStr + 'T00:00:00');
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
}

function getMondayOfWeek(dateStr) {
    const d = new Date(dateStr + 'T00:00:00');
    const day = d.getDay();
    const diff = d.getDate() - day + (day === 0 ? -6 : 1);
    const monday = new Date(d);
    monday.setDate(diff);
    return monday;
}

// ── Render flights with aligned grid layout (outbound | date | return per row) ──
function renderFlights() {
    const outbound = allFlights.filter(f => f.direction === 'outbound');
    const ret = allFlights.filter(f => f.direction === 'return');

    const allDates = new Set();
    outbound.forEach(f => allDates.add(f.flight_date));
    ret.forEach(f => allDates.add(f.flight_date));
    const sortedDates = [...allDates].sort();

    const grid = document.getElementById('flightGrid');
    const emptyState = document.getElementById('emptyState');

    if (sortedDates.length === 0) {
        grid.innerHTML = '';
        if (emptyState) { emptyState.classList.remove('hidden'); grid.appendChild(emptyState); }
        updateRecap();
        return;
    }

    if (emptyState) emptyState.classList.add('hidden');

    const outByDate = {};
    const retByDate = {};
    outbound.forEach(f => { (outByDate[f.flight_date] = outByDate[f.flight_date] || []).push(f); });
    ret.forEach(f => { (retByDate[f.flight_date] = retByDate[f.flight_date] || []).push(f); });

    let html = '';
    let prevMondayStr = null;

    for (const dateKey of sortedDates) {
        const currentMonday = getMondayOfWeek(dateKey);
        const currentMondayStr = formatDateISO(currentMonday);
        const weekNum = getISOWeekNumber(dateKey);

        // Week header when week changes
        if (currentMondayStr !== prevMondayStr) {
            const mondayDay = currentMonday.getDate();
            const mondayMonth = currentMonday.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
            html += `<div class="week-header-row">
                <div class="week-header-label">Week ${weekNum} — Mon ${mondayDay} ${mondayMonth}</div>
            </div>`;
            prevMondayStr = currentMondayStr;
        }

        const dayFlightsOut = (outByDate[dateKey] || []).sort((a, b) =>
            (a.departure_time || '').localeCompare(b.departure_time || '')
        );
        const dayFlightsRet = (retByDate[dateKey] || []).sort((a, b) =>
            (a.departure_time || '').localeCompare(b.departure_time || '')
        );

        const isDimForOutbound = selectedReturn && dateKey > selectedReturn.flight_date;
        const isDimForReturn = selectedOutbound && dateKey < selectedOutbound.flight_date;

        const d = new Date(dateKey + 'T00:00:00');
        const dayName = d.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
        const dayNum = d.getDate();
        const monthName = d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();

        html += `<div class="flight-day-row" data-date="${dateKey}">`;

        // Outbound column
        html += `<div class="flight-day-col${isDimForOutbound ? ' dimmed' : ''}">`;
        if (dayFlightsOut.length > 0) {
            html += renderDayFlights(dayFlightsOut, 'outbound', isDimForOutbound);
        }
        html += `</div>`;

        // Date column (center)
        html += `<div class="flight-day-date">
            <span class="day-name">${dayName}</span>
            <span class="day-num">${dayNum}</span>
            <span class="day-month">${monthName}</span>
        </div>`;

        // Return column
        html += `<div class="flight-day-col${isDimForReturn ? ' dimmed' : ''}">`;
        if (dayFlightsRet.length > 0) {
            html += renderDayFlights(dayFlightsRet, 'return', isDimForReturn);
        }
        html += `</div>`;

        html += `</div>`;
    }

    grid.innerHTML = html;
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

    // Prevent selection of dimmed flights
    if (direction === 'outbound' && selectedReturn && flight.flight_date > selectedReturn.flight_date) return;
    if (direction === 'return' && selectedOutbound && flight.flight_date < selectedOutbound.flight_date) return;

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

    const grandTotal = totalBase + totalFixed + totalPercent;
    totalEl.textContent = `${Math.round(grandTotal)} €`;

    if (selectedOutbound && selectedReturn) {
        const outDate = new Date(selectedOutbound.flight_date + 'T00:00:00');
        const retDate = new Date(selectedReturn.flight_date + 'T00:00:00');
        const diffMs = retDate - outDate;
        const diffDays = Math.max(0, Math.round(diffMs / (1000 * 60 * 60 * 24)) - 1);
        daysEl.textContent = `| ${diffDays} Day${diffDays !== 1 ? 's' : ''}`;
    } else {
        daysEl.textContent = '';
    }

    breakdownEl.textContent = '';
}

document.addEventListener('DOMContentLoaded', init);
