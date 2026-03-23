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

function syncDateDisplay(pickerId) {
    const picker = document.getElementById(pickerId);
    const display = document.getElementById(pickerId + 'Display');
    if (picker && display) display.value = picker.value;
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
    syncDateDisplay('dateFrom');
    syncDateDisplay('dateTo');
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
        syncDateDisplay('dateFrom');
        syncDateDisplay('dateTo');
    });

    dateToEl.addEventListener('change', () => {
        if (dateToEl.value && dateFromEl.value && dateToEl.value <= dateFromEl.value) {
            const nextDay = new Date(dateFromEl.value + 'T00:00:00');
            nextDay.setDate(nextDay.getDate() + 1);
            dateToEl.value = formatDateISO(nextDay);
        }
        syncDateDisplay('dateTo');
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
        appSettings = { ideal_price: 40, time_slots: [] };
    }
}

// ── Always load last search info ──
async function loadLastSearchInfo() {
    try {
        const data = await API.getLastSearch();
        if (data && data.origin_city) {
            document.getElementById('originCity').value = (data.origin_city || '').toUpperCase();
            document.getElementById('destinationCity').value = (data.destination_city || '').toUpperCase();
            if (data.date_from) { document.getElementById('dateFrom').value = data.date_from; syncDateDisplay('dateFrom'); }
            if (data.date_to) { document.getElementById('dateTo').value = data.date_to; syncDateDisplay('dateTo'); }
            // Set airline toggles to match the last search
            if (data.airlines && data.airlines.length > 0) {
                const searchAirlines = data.airlines.map(a => a.toUpperCase());
                document.querySelectorAll('.airline-toggle').forEach(el => {
                    const name = (el.dataset.airline || '').toUpperCase();
                    if (searchAirlines.includes(name)) {
                        el.classList.add('active');
                    } else {
                        el.classList.remove('active');
                    }
                });
            }
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

                // Populate search parameters in the UI
                if (data.origin_city) document.getElementById('originCity').value = data.origin_city.toUpperCase();
                if (data.destination_city) document.getElementById('destinationCity').value = data.destination_city.toUpperCase();
                if (data.date_from) { document.getElementById('dateFrom').value = data.date_from; syncDateDisplay('dateFrom'); }
                if (data.date_to) { document.getElementById('dateTo').value = data.date_to; syncDateDisplay('dateTo'); }

                // Set airline toggles to match the running search
                if (data.airlines && data.airlines.length > 0) {
                    const searchAirlines = data.airlines.map(a => a.toUpperCase());
                    document.querySelectorAll('.airline-toggle').forEach(el => {
                        const name = (el.dataset.airline || '').toUpperCase();
                        if (searchAirlines.includes(name)) {
                            el.classList.add('active');
                        } else {
                            el.classList.remove('active');
                        }
                    });
                }

                // Update progress text
                const origin = data.origin_city || '';
                const dest = data.destination_city || '';
                const progressText = document.getElementById('progressText');
                if (progressText) progressText.textContent = `${origin} → ${dest} | ${data.date_from || ''} → ${data.date_to || ''}`;

                showSearchingState();

                // Resume timer from actual search start time
                if (status.last_run.started_at) {
                    const startedAtStr = status.last_run.started_at.endsWith('Z') ? status.last_run.started_at : status.last_run.started_at + 'Z';
                    const serverStart = new Date(startedAtStr).getTime();
                    searchStartTime = serverStart;
                    const timerEl = document.getElementById('searchTimer');
                    const estimateEl = document.getElementById('searchEstimate');
                    if (estimateEl) estimateEl.textContent = '';
                    if (searchTimerInterval) clearInterval(searchTimerInterval);
                    searchTimerInterval = setInterval(() => {
                        if (!searchStartTime || !timerEl) return;
                        const elapsed = Math.floor((Date.now() - searchStartTime) / 1000);
                        const mm = String(Math.floor(elapsed / 60)).padStart(2, '0');
                        const ss = String(elapsed % 60).padStart(2, '0');
                        timerEl.textContent = `⏱ ${mm}:${ss}`;
                    }, 1000);
                }

                startPolling(data.id);
                console.log(`[FlyCal Crawler] Resumed polling for background search #${data.id}`);
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

function toggleAllAirlines() {
    const toggles = document.querySelectorAll('.airline-toggle');
    const allActive = Array.from(toggles).every(t => t.classList.contains('active'));
    toggles.forEach(t => {
        if (allActive) t.classList.remove('active');
        else t.classList.add('active');
    });
}

function swapCities() {
    const originEl = document.getElementById('originCity');
    const destEl = document.getElementById('destinationCity');
    const tmp = originEl.value;
    originEl.value = destEl.value;
    destEl.value = tmp;
}

function getSelectedAirlines() {
    const toggles = document.querySelectorAll('.airline-toggle.active');
    const names = [];
    toggles.forEach(t => names.push(t.dataset.airline));
    return names;
}

// ── City data: grouped by country ──
const CITIES_BY_COUNTRY = {
    "France": ["PARIS", "LYON", "MARSEILLE", "TOULOUSE", "BORDEAUX", "NANTES", "NICE", "MONTPELLIER", "LILLE", "STRASBOURG"],
    "French Overseas": ["POINTE-A-PITRE", "FORT-DE-FRANCE", "CAYENNE", "SAINT-DENIS REUNION"],
    "Morocco": ["MARRAKECH", "CASABLANCA", "NADOR", "OUJDA", "TANGIER", "FEZ", "AGADIR", "RABAT", "ESSAOUIRA"],
    "Spain": ["MADRID", "BARCELONA", "MALAGA", "SEVILLE", "VALENCIA", "PALMA DE MALLORCA", "IBIZA", "TENERIFE", "GRAN CANARIA", "BILBAO", "ALICANTE"],
    "United Kingdom": ["LONDON", "EDINBURGH", "MANCHESTER", "BIRMINGHAM", "GLASGOW", "BRISTOL", "LIVERPOOL", "NEWCASTLE"],
    "Italy": ["ROME", "MILAN", "VENICE", "NAPLES", "FLORENCE", "BOLOGNA", "TURIN", "CATANIA", "PALERMO", "BARI"],
    "Germany": ["BERLIN", "FRANKFURT", "DUSSELDORF", "MUNICH", "HAMBURG", "COLOGNE", "STUTTGART", "HANOVER", "NUREMBERG"],
    "Portugal": ["LISBON", "PORTO", "FARO", "FUNCHAL"],
    "Netherlands": ["AMSTERDAM"],
    "Belgium": ["BRUSSELS"],
    "Ireland": ["DUBLIN"],
    "Austria": ["VIENNA", "SALZBURG", "INNSBRUCK"],
    "Switzerland": ["ZURICH", "GENEVA", "BASEL"],
    "Scandinavia": ["COPENHAGEN", "STOCKHOLM", "OSLO", "HELSINKI", "GOTHENBURG", "BERGEN", "TAMPERE", "TURKU", "ROVANIEMI"],
    "Eastern Europe": ["WARSAW", "PRAGUE", "BUDAPEST", "BUCHAREST", "SOFIA", "KRAKOW", "ZAGREB", "BELGRADE", "BRATISLAVA", "LJUBLJANA"],
    "Baltic States": ["TALLINN", "RIGA", "VILNIUS"],
    "Greece": ["ATHENS", "THESSALONIKI", "SANTORINI", "MYKONOS", "HERAKLION", "RHODES", "CORFU"],
    "Turkey": ["ISTANBUL", "ANKARA", "ANTALYA", "IZMIR", "BODRUM"],
    "Cyprus": ["LARNACA", "PAPHOS"],
    "Malta": ["MALTA"],
    "Tunisia": ["TUNIS"],
    "Algeria": ["ALGIERS", "ORAN"],
    "Egypt": ["CAIRO", "HURGHADA", "SHARM EL SHEIKH", "LUXOR", "ALEXANDRIA"],
    "Middle East": ["DUBAI", "ABU DHABI", "DOHA", "RIYADH", "JEDDAH", "MUSCAT", "KUWAIT CITY", "BAHRAIN", "AMMAN", "BEIRUT", "TEL AVIV", "MEDINA"],
    "North America": ["NEW YORK", "LOS ANGELES", "CHICAGO", "MIAMI", "DALLAS", "SAN FRANCISCO", "WASHINGTON", "BOSTON", "HOUSTON", "SEATTLE", "ATLANTA", "DENVER", "PHILADELPHIA", "PHOENIX", "ORLANDO", "CHARLOTTE", "LAS VEGAS", "TORONTO", "MONTREAL", "VANCOUVER", "MEXICO CITY", "CANCUN"],
    "South America": ["SAO PAULO", "BUENOS AIRES", "LIMA", "BOGOTA", "SANTIAGO", "RIO DE JANEIRO"],
    "East Asia": ["TOKYO", "BEIJING", "SHANGHAI", "HONG KONG", "SEOUL", "TAIPEI", "OSAKA", "GUANGZHOU", "CHENGDU", "SHENZHEN"],
    "Southeast Asia": ["SINGAPORE", "BANGKOK", "KUALA LUMPUR", "JAKARTA", "MANILA", "HO CHI MINH CITY", "HANOI", "BALI"],
    "South Asia": ["MUMBAI", "DELHI", "BANGALORE", "HYDERABAD", "CHENNAI", "KOLKATA", "COLOMBO", "ISLAMABAD", "KARACHI", "LAHORE", "DHAKA", "KATHMANDU", "MALE"],
    "Central Asia": ["ALMATY", "TASHKENT", "BAKU", "TBILISI"],
    "West Africa": ["DAKAR", "ABIDJAN", "LAGOS", "ACCRA"],
    "East Africa": ["NAIROBI", "ADDIS ABABA", "DAR ES SALAAM", "ENTEBBE", "KIGALI", "ZANZIBAR"],
    "Southern Africa": ["JOHANNESBURG", "CAPE TOWN", "DURBAN"],
    "North Africa": ["TRIPOLI"],
    "Indian Ocean": ["MAURITIUS"],
    "Oceania": ["SYDNEY", "MELBOURNE", "PERTH", "BRISBANE", "AUCKLAND", "CHRISTCHURCH"],
    "Caribbean": ["HAVANA", "PUNTA CANA", "SANTO DOMINGO"],
};

// Build flat lookup: city → country
const CITY_COUNTRY_MAP = {};
for (const [country, cities] of Object.entries(CITIES_BY_COUNTRY)) {
    for (const city of cities) CITY_COUNTRY_MAP[city] = country;
}

// Recent cities (persisted in localStorage)
const RECENT_CITIES_KEY = 'flycal_recent_cities';
const MAX_RECENT_CITIES = 3;

function getRecentCities() {
    try {
        return JSON.parse(localStorage.getItem(RECENT_CITIES_KEY)) || [];
    } catch { return []; }
}

function addRecentCity(city) {
    if (!city) return;
    city = city.toUpperCase();
    let recents = getRecentCities().filter(c => c !== city);
    recents.unshift(city);
    if (recents.length > MAX_RECENT_CITIES) recents = recents.slice(0, MAX_RECENT_CITIES);
    localStorage.setItem(RECENT_CITIES_KEY, JSON.stringify(recents));
}

// ── City dropdown component ──
function initCityDropdown(inputId, dropdownId) {
    const input = document.getElementById(inputId);
    const dropdown = document.getElementById(dropdownId);
    let highlightIdx = -1;

    // Build dropdown HTML
    function renderDropdown(filter = '') {
        const f = filter.toUpperCase().trim();
        let html = '<div class="city-dropdown-search"><input type="text" placeholder="Search city..." class="city-search-input"></div>';
        html += '<div class="city-dropdown-list">';

        // Recent cities
        const recents = getRecentCities();
        if (!f && recents.length > 0) {
            html += '<div class="city-group">';
            html += '<div class="city-group-label recent-label">Recent</div>';
            for (const city of recents) {
                const country = CITY_COUNTRY_MAP[city] || '';
                html += `<div class="city-option" data-city="${city}"><span class="city-name">${city}</span><span class="city-country">${country}</span></div>`;
            }
            html += '</div>';
        }

        // Countries
        let hasResults = false;
        for (const [country, cities] of Object.entries(CITIES_BY_COUNTRY)) {
            const filtered = f ? cities.filter(c => c.includes(f) || country.toUpperCase().includes(f)) : cities;
            if (filtered.length === 0) continue;
            hasResults = true;
            html += '<div class="city-group">';
            html += `<div class="city-group-label">${country}</div>`;
            for (const city of filtered) {
                html += `<div class="city-option" data-city="${city}"><span class="city-name">${city}</span></div>`;
            }
            html += '</div>';
        }

        if (f && !hasResults) {
            html += '<div class="city-no-results">No cities found</div>';
        }

        html += '</div>';
        dropdown.innerHTML = html;
        highlightIdx = -1;

        // Attach click handlers
        dropdown.querySelectorAll('.city-option').forEach(opt => {
            opt.addEventListener('mousedown', (e) => {
                e.preventDefault();
                selectCity(opt.dataset.city);
            });
        });

        // Attach search input events
        const searchInput = dropdown.querySelector('.city-search-input');
        if (searchInput) {
            searchInput.value = filter;
            // Focus search input after render
            requestAnimationFrame(() => searchInput.focus());
            searchInput.addEventListener('input', () => {
                renderDropdown(searchInput.value);
            });
            searchInput.addEventListener('keydown', handleKeydown);
        }
    }

    function selectCity(city) {
        input.value = city;
        addRecentCity(city);
        closeDropdown();
        // Trigger change event for any listeners
        input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function openDropdown() {
        dropdown.classList.remove('hidden');
        renderDropdown('');
    }

    function closeDropdown() {
        dropdown.classList.add('hidden');
    }

    function handleKeydown(e) {
        const options = dropdown.querySelectorAll('.city-option');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            highlightIdx = Math.min(highlightIdx + 1, options.length - 1);
            updateHighlight(options);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            highlightIdx = Math.max(highlightIdx - 1, 0);
            updateHighlight(options);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (highlightIdx >= 0 && highlightIdx < options.length) {
                selectCity(options[highlightIdx].dataset.city);
            } else if (options.length > 0) {
                selectCity(options[0].dataset.city);
            }
        } else if (e.key === 'Escape') {
            closeDropdown();
        }
    }

    function updateHighlight(options) {
        options.forEach((opt, i) => {
            opt.classList.toggle('highlighted', i === highlightIdx);
            if (i === highlightIdx) opt.scrollIntoView({ block: 'nearest' });
        });
    }

    // Open on click
    input.addEventListener('click', (e) => {
        e.stopPropagation();
        // Close the other dropdown if open
        document.querySelectorAll('.city-dropdown').forEach(d => {
            if (d !== dropdown) d.classList.add('hidden');
        });
        if (dropdown.classList.contains('hidden')) {
            openDropdown();
        } else {
            closeDropdown();
        }
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
        if (!dropdown.contains(e.target) && e.target !== input) {
            closeDropdown();
        }
    });

    // Prevent dropdown from closing when clicking inside it
    dropdown.addEventListener('click', (e) => {
        e.stopPropagation();
    });
}

async function loadCityList() {
    try {
        // Build flat city list for validation
        cityList = [];
        for (const cities of Object.values(CITIES_BY_COUNTRY)) {
            cityList.push(...cities);
        }
        // Init custom dropdowns
        initCityDropdown('originCity', 'originCityDropdown');
        initCityDropdown('destinationCity', 'destinationCityDropdown');
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
                const next = fmtDT(status.next_run);
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
        syncDateDisplay('dateFrom');
        syncDateDisplay('dateTo');

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

    if (origin === destination) {
        Toast.warning('Origin and destination cities must be different.');
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

            if (done) {
                // Search finished — render results now
                allFlights = data ? (data.flights || []) : [];
                renderFlights();
                autoSelectBestFlights();
                console.log(`[FlyCal Crawler] Search ${wasCancelled ? 'cancelled' : 'complete'}: ${allFlights.length} total flights`);
                clearInterval(pollingTimer);
                pollingTimer = null;
                hideSearchingState();
                if (wasCancelled) Toast.warning('Search cancelled');
                else notifySearchComplete(allFlights.length);
            }
            // While running, keep loader visible — don't render intermediate results
        } catch (e) {
            console.error('Polling error:', e);
        }
    }, 3000);

    // Timeout after 30 minutes (safety net — polling stops naturally when backend finishes)
    setTimeout(() => {
        if (pollingTimer) {
            console.log('[FlyCal Crawler] Search timed out after 30 minutes');
            clearInterval(pollingTimer);
            pollingTimer = null;
            hideSearchingState();
            Toast.warning('Search timed out after 30 minutes');
        }
    }, 1800000);
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
        html += `<span class="flight-row-prices">`;
        if (f.oldest_price != null && f.oldest_price !== f.price) {
            const diff = f.price - f.oldest_price;
            const arrow = diff < 0 ? '↓' : '↑';
            const cls = diff < 0 ? 'price-down' : 'price-up';
            html += `<span class="flight-row-old-price ${cls}">${arrow} ${Math.round(f.oldest_price)}€ (${f.oldest_price_date})</span>`;
        }
        html += `<span class="flight-row-price">${Math.round(f.price)}€</span>`;
        html += `</span>`;

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
                const dateStr = fmtDT(h.recorded_at);
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
