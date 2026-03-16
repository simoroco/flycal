/* === FlyCal — Calendar Utilities === */

let _settings = null;

async function loadSettings() {
    if (!_settings) {
        try {
            _settings = await API.getSettings();
        } catch (e) {
            _settings = {
                ideal_price: 100,
                time_slots: [
                    { label: 'Comfortable', start: '10:00', end: '18:00', color: 'green' },
                    { label: 'Acceptable', start: '06:00', end: '10:00', color: 'orange' },
                    { label: 'Difficult', start: '00:00', end: '06:00', color: 'red' },
                    { label: 'Late', start: '18:00', end: '00:00', color: 'orange' },
                ],
            };
        }
    }
    return _settings;
}

function invalidateSettingsCache() {
    _settings = null;
}

function timeToMinutes(timeStr) {
    if (!timeStr) return 0;
    const parts = timeStr.split(':');
    return parseInt(parts[0], 10) * 60 + parseInt(parts[1] || '0', 10);
}

function getTimeColor(departureTime, timeSlots) {
    const t = timeToMinutes(departureTime);
    for (const slot of timeSlots) {
        const s = timeToMinutes(slot.start);
        const e = timeToMinutes(slot.end);
        if (e <= s) {
            if (t >= s || t < e) return slot.color;
        } else {
            if (t >= s && t < e) return slot.color;
        }
    }
    return 'orange';
}

function getPriceColor(price, idealPrice) {
    const ip = parseFloat(idealPrice) || 100;
    if (price <= ip * 0.8) return 'green';
    if (price <= ip * 1.2) return 'orange';
    return 'red';
}

function compositeColor(c1, c2) {
    const rank = { green: 0, orange: 1, red: 2 };
    const r1 = rank[c1] !== undefined ? rank[c1] : 1;
    const r2 = rank[c2] !== undefined ? rank[c2] : 1;
    if (r1 === 0 && r2 === 0) return 'green';
    if (r1 === 2 && r2 === 2) return 'red';
    if ((r1 === 2 && r2 === 1) || (r1 === 1 && r2 === 2)) return 'red';
    return 'orange';
}

function getFlightColor(flight, settings) {
    const timeSlots = settings.time_slots || [];
    const idealPrice = settings.ideal_price || 100;
    const tc = getTimeColor(flight.departure_time, timeSlots);
    const pc = getPriceColor(flight.price, idealPrice);
    return compositeColor(tc, pc);
}

function calculateDuration(depTime, arrTime) {
    if (!depTime || !arrTime) return '';
    const d = timeToMinutes(depTime);
    let a = timeToMinutes(arrTime);
    if (a < d) a += 24 * 60;
    const diff = a - d;
    const h = Math.floor(diff / 60);
    const m = diff % 60;
    if (h === 0) return `${m}min`;
    if (m === 0) return `${h}h`;
    return `${h}h${m.toString().padStart(2, '0')}`;
}

function airlineAbbrev(name) {
    if (!name) return '??';
    const words = name.split(' ');
    if (words.length >= 2) {
        return (words[0][0] + words[1][0]).toUpperCase();
    }
    return name.substring(0, 2).toUpperCase();
}

function formatDateHeader(dateStr) {
    try {
        const d = new Date(dateStr + 'T00:00:00');
        const options = { weekday: 'long', day: 'numeric', month: 'long' };
        const formatted = d.toLocaleDateString('en-US', options);
        return formatted;
    } catch (e) {
        return dateStr;
    }
}

/**
 * Render a traditional calendar view (used on searches page modal).
 */
function renderCalendar(container, flights, selectedId, onSelect, settings) {
    if (!flights || flights.length === 0) {
        container.innerHTML = '<div class="no-flights">No flights found</div>';
        return;
    }

    const grouped = {};
    for (const f of flights) {
        const dateKey = f.flight_date;
        if (!grouped[dateKey]) grouped[dateKey] = [];
        grouped[dateKey].push(f);
    }

    const sortedDates = Object.keys(grouped).sort();

    let html = '';
    for (const dateKey of sortedDates) {
        const dayFlights = grouped[dateKey].sort((a, b) => {
            return timeToMinutes(a.departure_time) - timeToMinutes(b.departure_time);
        });

        html += `<div class="calendar-day">`;
        html += `<div class="day-header">`;
        html += `<span class="day-date">${formatDateHeader(dateKey)}</span>`;
        html += `<span class="day-count">${dayFlights.length} flight${dayFlights.length > 1 ? 's' : ''}</span>`;
        html += `</div>`;
        html += `<div class="day-flights">`;

        for (const f of dayFlights) {
            const color = settings ? getFlightColor(f, settings) : 'orange';
            const isSelected = selectedId === f.id;
            const duration = calculateDuration(f.departure_time, f.arrival_time);
            const abbrev = airlineAbbrev(f.airline_name);

            html += `<div class="flight-card color-${color}${isSelected ? ' selected' : ''}" data-flight-id="${f.id}">`;
            html += `<div class="flight-airline">`;
            if (f.airline_logo_url) {
                html += `<img src="${f.airline_logo_url}" alt="${f.airline_name}" class="airline-logo-img" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`;
                html += `<div class="airline-logo" style="display:none">${abbrev}</div>`;
            } else {
                html += `<div class="airline-logo">${abbrev}</div>`;
            }
            html += `<div class="airline-name">${f.airline_name || ''}</div>`;
            html += `</div>`;
            html += `<div class="flight-details">`;
            html += `<div class="flight-times">`;
            html += `<span class="flight-time">${f.departure_time || '--:--'}</span>`;
            html += `<span class="flight-arrow">→</span>`;
            html += `<span class="flight-time">${f.arrival_time || '--:--'}</span>`;
            if (duration) {
                html += `<span class="flight-duration">${duration}</span>`;
            }
            html += `</div>`;
            html += `<div class="flight-airports">`;
            html += `<span class="airport-code">${f.origin_airport || '???'}</span>`;
            html += `<span class="flight-arrow">→</span>`;
            html += `<span class="airport-code">${f.destination_airport || '???'}</span>`;
            html += `</div>`;
            html += `</div>`;
            html += `<div class="flight-price">`;
            html += `<span class="price-amount">${Math.round(f.price)}</span>`;
            html += `<span class="price-currency">€</span>`;
            html += `</div>`;
            html += `</div>`;
        }

        html += `</div></div>`;
    }

    container.innerHTML = html;
}
