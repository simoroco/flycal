let currentTripType = 'oneway';
let currentSearchId = null;
let allFlights = [];
let selectedOutbound = null;
let selectedReturn = null;
let pollingTimer = null;
let appSettings = null;

async function init() {
    await Promise.all([
        loadAirlinesCheckboxes(),
        loadCrawlerStatus(),
        loadSettingsForApp(),
    ]);
    handleUrlParams();
    if (!currentSearchId) {
        await loadLastSearch();
    }
}

async function loadSettingsForApp() {
    try {
        appSettings = await API.getSettings();
    } catch (e) {
        appSettings = { ideal_price: 100, time_slots: [] };
    }
}

async function loadAirlinesCheckboxes() {
    try {
        const airlines = await API.getAirlines();
        const container = document.getElementById('airlinesCheckboxes');
        container.innerHTML = airlines
            .filter(a => a.enabled)
            .map(a => `
                <label class="airline-checkbox">
                    <input type="checkbox" value="${a.name}" checked>
                    ${a.name}
                </label>
            `).join('');
    } catch (e) {
        console.error('Failed to load airlines:', e);
    }
}

async function loadCrawlerStatus() {
    try {
        const status = await API.getCrawlerStatus();
        const dot = document.getElementById('crawlerDot');
        const label = document.getElementById('crawlerLabel');
        if (dot && label) {
            dot.className = 'crawler-dot ' + (status.enabled ? 'active' : 'inactive');
            label.textContent = status.enabled ? 'Crawler actif' : 'Crawler inactif';
        }
    } catch (e) {}
}

function handleUrlParams() {
    const params = new URLSearchParams(window.location.search);
    if (params.has('origin')) {
        document.getElementById('originCity').value = params.get('origin') || '';
        document.getElementById('destinationCity').value = params.get('destination') || '';
        document.getElementById('dateFrom').value = params.get('date_from') || '';
        document.getElementById('dateTo').value = params.get('date_to') || '';
        const tripType = params.get('trip_type') || 'oneway';
        setTripType(tripType);

        const airlinesStr = params.get('airlines') || '';
        if (airlinesStr) {
            const requested = airlinesStr.split(',');
            document.querySelectorAll('#airlinesCheckboxes input[type="checkbox"]').forEach(cb => {
                cb.checked = requested.includes(cb.value);
            });
        }

        if (params.get('autorun') === '1') {
            window.history.replaceState({}, '', '/');
            setTimeout(() => launchSearch(), 300);
        }
    }
}

function setTripType(type) {
    currentTripType = type;
    document.getElementById('btnOneway').classList.toggle('active', type === 'oneway');
    document.getElementById('btnRoundtrip').classList.toggle('active', type === 'roundtrip');

    const colReturn = document.getElementById('colReturn');
    if (colReturn) {
        colReturn.style.display = type === 'roundtrip' ? '' : 'none';
    }

    const recapReturn = document.getElementById('recapReturn');
    if (recapReturn) {
        recapReturn.style.display = type === 'roundtrip' ? '' : 'none';
    }

    updateRecap();
}

async function launchSearch() {
    const origin = document.getElementById('originCity').value.trim();
    const destination = document.getElementById('destinationCity').value.trim();
    const dateFrom = document.getElementById('dateFrom').value;
    const dateTo = document.getElementById('dateTo').value;

    if (!origin || !destination || !dateFrom || !dateTo) {
        alert('Veuillez remplir tous les champs de recherche.');
        return;
    }

    const airlines = [];
    document.querySelectorAll('#airlinesCheckboxes input[type="checkbox"]:checked').forEach(cb => {
        airlines.push(cb.value);
    });

    const btn = document.getElementById('btnSearch');
    const btnText = document.getElementById('searchBtnText');
    const loader = document.getElementById('searchLoader');
    btn.disabled = true;
    btnText.textContent = 'Recherche en cours...';
    loader.classList.remove('hidden');

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
            trip_type: currentTripType,
            airlines: airlines,
        });

        currentSearchId = result.search_id;
        startPolling(result.search_id);
    } catch (e) {
        alert('Erreur lors du lancement de la recherche : ' + e.message);
        btn.disabled = false;
        btnText.textContent = 'Lancer la recherche';
        loader.classList.add('hidden');
    }
}

function startPolling(searchId) {
    if (pollingTimer) clearInterval(pollingTimer);

    showPollingState();

    pollingTimer = setInterval(async () => {
        try {
            const data = await API.getLastSearch();
            if (data && data.flights && data.flights.length > 0) {
                allFlights = data.flights;
                renderFlights();
                clearInterval(pollingTimer);
                pollingTimer = null;
                hidePollingState();
            } else if (data && data.id && data.id !== searchId) {
                clearInterval(pollingTimer);
                pollingTimer = null;
                hidePollingState();
            }
        } catch (e) {
            console.error('Polling error:', e);
        }
    }, 3000);

    setTimeout(() => {
        if (pollingTimer) {
            clearInterval(pollingTimer);
            pollingTimer = null;
            hidePollingState();
            loadLastSearch();
        }
    }, 300000);
}

function showPollingState() {
    const outContainer = document.getElementById('calendarOutbound');
    const retContainer = document.getElementById('calendarReturn');
    const pollingHtml = '<div class="polling-indicator"><span class="loader"></span> Scraping en cours, veuillez patienter...</div>';
    outContainer.innerHTML = pollingHtml;
    retContainer.innerHTML = pollingHtml;
}

function hidePollingState() {
    const btn = document.getElementById('btnSearch');
    const btnText = document.getElementById('searchBtnText');
    const loader = document.getElementById('searchLoader');
    btn.disabled = false;
    btnText.textContent = 'Lancer la recherche';
    loader.classList.add('hidden');
}

async function loadLastSearch() {
    try {
        const data = await API.getLastSearch();
        if (data && data.flights && data.flights.length > 0) {
            allFlights = data.flights;
            currentSearchId = data.id;

            if (data.origin_city) document.getElementById('originCity').value = data.origin_city;
            if (data.destination_city) document.getElementById('destinationCity').value = data.destination_city;
            if (data.date_from) document.getElementById('dateFrom').value = data.date_from;
            if (data.date_to) document.getElementById('dateTo').value = data.date_to;
            if (data.trip_type) setTripType(data.trip_type);

            if (data.airlines && data.airlines.length > 0) {
                document.querySelectorAll('#airlinesCheckboxes input[type="checkbox"]').forEach(cb => {
                    cb.checked = data.airlines.includes(cb.value);
                });
            }

            renderFlights();
        }
    } catch (e) {
        console.error('Failed to load last search:', e);
    }
}

function renderFlights() {
    const outbound = allFlights.filter(f => f.direction === 'outbound');
    const ret = allFlights.filter(f => f.direction === 'return');

    const outContainer = document.getElementById('calendarOutbound');
    const retContainer = document.getElementById('calendarReturn');
    const emptyOut = document.getElementById('emptyOutbound');
    const emptyRet = document.getElementById('emptyReturn');

    if (outbound.length > 0) {
        if (emptyOut) emptyOut.classList.add('hidden');
        renderCalendar(outContainer, outbound, selectedOutbound ? selectedOutbound.id : null, () => {}, appSettings);
    } else {
        outContainer.innerHTML = '';
        if (emptyOut) {
            emptyOut.classList.remove('hidden');
            outContainer.appendChild(emptyOut);
        }
    }

    if (ret.length > 0) {
        if (emptyRet) emptyRet.classList.add('hidden');
        renderCalendar(retContainer, ret, selectedReturn ? selectedReturn.id : null, () => {}, appSettings);
    } else {
        retContainer.innerHTML = '';
        if (emptyRet) {
            emptyRet.classList.remove('hidden');
            retContainer.appendChild(emptyRet);
        }
    }

    updateRecap();
}

function handleFlightClick(flightId, direction) {
    const flight = allFlights.find(f => f.id === flightId);
    if (!flight) return;

    if (direction === 'outbound') {
        if (selectedOutbound && selectedOutbound.id === flightId) {
            selectedOutbound = null;
        } else {
            selectedOutbound = flight;
        }
    } else {
        if (selectedReturn && selectedReturn.id === flightId) {
            selectedReturn = null;
        } else {
            selectedReturn = flight;
        }
    }

    renderFlights();
}

function updateRecap() {
    const banner = document.getElementById('recapBanner');
    const outDetail = document.getElementById('recapOutDetail');
    const retDetail = document.getElementById('recapRetDetail');
    const totalEl = document.getElementById('recapTotal');

    const hasSelection = selectedOutbound || selectedReturn;

    if (!hasSelection) {
        banner.classList.add('hidden');
        return;
    }

    banner.classList.remove('hidden');

    if (selectedOutbound) {
        const f = selectedOutbound;
        outDetail.textContent = `${f.airline_name} — ${f.departure_time} → ${f.arrival_time} (${f.origin_airport}→${f.destination_airport}) — ${Math.round(f.price)}€`;
    } else {
        outDetail.textContent = '—';
    }

    if (selectedReturn && currentTripType === 'roundtrip') {
        const f = selectedReturn;
        retDetail.textContent = `${f.airline_name} — ${f.departure_time} → ${f.arrival_time} (${f.origin_airport}→${f.destination_airport}) — ${Math.round(f.price)}€`;
    } else {
        retDetail.textContent = '—';
    }

    let total = 0;
    if (selectedOutbound) {
        let price = selectedOutbound.price;
        let feesFixed = selectedOutbound.airline_fees_fixed || 0;
        let feesPercent = selectedOutbound.airline_fees_percent || 0;
        total += price + feesFixed + (price * feesPercent / 100);
    }
    if (selectedReturn && currentTripType === 'roundtrip') {
        let price = selectedReturn.price;
        let feesFixed = selectedReturn.airline_fees_fixed || 0;
        let feesPercent = selectedReturn.airline_fees_percent || 0;
        total += price + feesFixed + (price * feesPercent / 100);
    }

    totalEl.textContent = `${Math.round(total)} €`;
}

document.addEventListener('DOMContentLoaded', init);
