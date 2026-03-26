"""
Google Flights scraper using fast-flights library.

Uses the local Playwright mode to fetch real flight data from Google Flights.
No API key required. Covers all airlines.
"""

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta, datetime
from typing import List, Optional

from .base import FlightResult, make_route_not_served, parse_price, resolve_airport

logger = logging.getLogger("flycal.scraper.google_flights")

CITY_AIRPORT_MAP = {
    # France
    "paris": "PAR",
    "orly": "ORY",
    "cdg": "CDG",
    "beauvais": "BVA",
    "marseille": "MRS",
    "lyon": "LYS",
    "toulouse": "TLS",
    "nantes": "NTE",
    "montpellier": "MPL",
    "bordeaux": "BOD",
    "lille": "LIL",
    "nice": "NCE",
    "strasbourg": "SXB",
    # French Overseas (DOM-TOM)
    "pointe-a-pitre": "PTP",
    "pointe a pitre": "PTP",
    "fort-de-france": "FDF",
    "fort de france": "FDF",
    "cayenne": "CAY",
    "saint-denis reunion": "RUN",
    "saint denis reunion": "RUN",
    "la reunion": "RUN",
    "reunion": "RUN",
    # Portugal
    "porto": "OPO",
    "lisbonne": "LIS",
    "lisbon": "LIS",
    "faro": "FAO",
    "funchal": "FNC",
    "madere": "FNC",
    # Spain
    "madrid": "MAD",
    "barcelone": "BCN",
    "barcelona": "BCN",
    "malaga": "AGP",
    "seville": "SVQ",
    "valencia": "VLC",
    "valence": "VLC",
    "palma": "PMI",
    "palma de mallorca": "PMI",
    "majorque": "PMI",
    "ibiza": "IBZ",
    "tenerife": "TFS",
    "teneriffe": "TFS",
    "gran canaria": "LPA",
    "grande canarie": "LPA",
    "bilbao": "BIO",
    "alicante": "ALC",
    # Italy
    "rome": "FCO",
    "milan": "MXP",
    "venice": "VCE",
    "venise": "VCE",
    "naples": "NAP",
    "florence": "FLR",
    "firenze": "FLR",
    "bologna": "BLQ",
    "bologne": "BLQ",
    "turin": "TRN",
    "catania": "CTA",
    "catane": "CTA",
    "palermo": "PMO",
    "palerme": "PMO",
    "bari": "BRI",
    # United Kingdom
    "london": "LHR",
    "londres": "LHR",
    "edinburgh": "EDI",
    "edimbourg": "EDI",
    "manchester": "MAN",
    "birmingham": "BHX",
    "glasgow": "GLA",
    "bristol": "BRS",
    "liverpool": "LPL",
    "newcastle": "NCL",
    # Ireland
    "dublin": "DUB",
    # Netherlands
    "amsterdam": "AMS",
    # Belgium
    "bruxelles": "BRU",
    "brussels": "BRU",
    # Germany
    "berlin": "BER",
    "frankfurt": "FRA",
    "francfort": "FRA",
    "dusseldorf": "DUS",
    "munich": "MUC",
    "hamburg": "HAM",
    "hambourg": "HAM",
    "cologne": "CGN",
    "stuttgart": "STR",
    "hanover": "HAJ",
    "hanovre": "HAJ",
    "nuremberg": "NUE",
    # Austria
    "vienna": "VIE",
    "vienne": "VIE",
    "salzburg": "SZG",
    "salzbourg": "SZG",
    "innsbruck": "INN",
    # Switzerland
    "zurich": "ZRH",
    "geneva": "GVA",
    "geneve": "GVA",
    "basel": "BSL",
    "bale": "BSL",
    # Scandinavia
    "copenhagen": "CPH",
    "copenhague": "CPH",
    "stockholm": "ARN",
    "oslo": "OSL",
    "helsinki": "HEL",
    "gothenburg": "GOT",
    "goteborg": "GOT",
    "bergen": "BGO",
    "tampere": "TMP",
    "turku": "TKU",
    "rovaniemi": "RVN",
    # Eastern Europe
    "warsaw": "WAW",
    "varsovie": "WAW",
    "prague": "PRG",
    "budapest": "BUD",
    "bucharest": "OTP",
    "bucarest": "OTP",
    "sofia": "SOF",
    "krakow": "KRK",
    "cracovie": "KRK",
    "zagreb": "ZAG",
    "belgrade": "BEG",
    "bratislava": "BTS",
    "ljubljana": "LJU",
    # Baltic States
    "tallinn": "TLL",
    "riga": "RIX",
    "vilnius": "VNO",
    # Greece
    "athenes": "ATH",
    "athens": "ATH",
    "thessaloniki": "SKG",
    "thessalonique": "SKG",
    "santorini": "JTR",
    "santorin": "JTR",
    "mykonos": "JMK",
    "myconos": "JMK",
    "heraklion": "HER",
    "heraclion": "HER",
    "rhodes": "RHO",
    "corfu": "CFU",
    "corfou": "CFU",
    # Turkey
    "istanbul": "IST",
    "ankara": "ESB",
    "antalya": "AYT",
    "izmir": "ADB",
    "bodrum": "BJV",
    # Cyprus
    "larnaca": "LCA",
    "larnaka": "LCA",
    "paphos": "PFO",
    # Malta
    "malta": "MLA",
    "malte": "MLA",
    # Morocco
    "marrakech": "RAK",
    "fes": "FEZ",
    "fez": "FEZ",
    "tanger": "TNG",
    "tangier": "TNG",
    "nador": "NDR",
    "oujda": "OUD",
    "agadir": "AGA",
    "casablanca": "CMN",
    "rabat": "RBA",
    "essaouira": "ESU",
    # Algeria
    "alger": "ALG",
    "algiers": "ALG",
    "oran": "ORN",
    # Tunisia
    "tunis": "TUN",
    # Egypt
    "le caire": "CAI",
    "cairo": "CAI",
    "hurghada": "HRG",
    "sharm el sheikh": "SSH",
    "charm el cheikh": "SSH",
    "luxor": "LXR",
    "louxor": "LXR",
    "alexandria": "HBE",
    "alexandrie": "HBE",
    # Middle East
    "dubai": "DXB",
    "abu dhabi": "AUH",
    "abou dabi": "AUH",
    "doha": "DOH",
    "riyadh": "RUH",
    "riyad": "RUH",
    "jeddah": "JED",
    "djeddah": "JED",
    "muscat": "MCT",
    "mascate": "MCT",
    "kuwait city": "KWI",
    "koweit": "KWI",
    "bahrain": "BAH",
    "bahrein": "BAH",
    "amman": "AMM",
    "beirut": "BEY",
    "beyrouth": "BEY",
    "tel aviv": "TLV",
    "medina": "MED",
    "medine": "MED",
    # North America
    "new york": "JFK",
    "los angeles": "LAX",
    "chicago": "ORD",
    "miami": "MIA",
    "dallas": "DFW",
    "san francisco": "SFO",
    "washington": "IAD",
    "boston": "BOS",
    "houston": "IAH",
    "seattle": "SEA",
    "atlanta": "ATL",
    "denver": "DEN",
    "philadelphia": "PHL",
    "philadelphie": "PHL",
    "phoenix": "PHX",
    "orlando": "MCO",
    "charlotte": "CLT",
    "las vegas": "LAS",
    "toronto": "YYZ",
    "montreal": "YUL",
    "vancouver": "YVR",
    "mexico city": "MEX",
    "mexico": "MEX",
    "cancun": "CUN",
    # South America
    "sao paulo": "GRU",
    "buenos aires": "EZE",
    "lima": "LIM",
    "bogota": "BOG",
    "santiago": "SCL",
    "rio de janeiro": "GIG",
    # East Asia
    "tokyo": "NRT",
    "beijing": "PEK",
    "pekin": "PEK",
    "shanghai": "PVG",
    "hong kong": "HKG",
    "seoul": "ICN",
    "taipei": "TPE",
    "osaka": "KIX",
    "guangzhou": "CAN",
    "canton": "CAN",
    "chengdu": "CTU",
    "shenzhen": "SZX",
    # Southeast Asia
    "singapore": "SIN",
    "singapour": "SIN",
    "bangkok": "BKK",
    "kuala lumpur": "KUL",
    "jakarta": "CGK",
    "djakarta": "CGK",
    "manila": "MNL",
    "manille": "MNL",
    "ho chi minh city": "SGN",
    "hanoi": "HAN",
    "bali": "DPS",
    # South Asia
    "mumbai": "BOM",
    "bombay": "BOM",
    "delhi": "DEL",
    "new delhi": "DEL",
    "bangalore": "BLR",
    "hyderabad": "HYD",
    "chennai": "MAA",
    "kolkata": "CCU",
    "calcutta": "CCU",
    "colombo": "CMB",
    "islamabad": "ISB",
    "karachi": "KHI",
    "lahore": "LHE",
    "dhaka": "DAC",
    "dacca": "DAC",
    "kathmandu": "KTM",
    "katmandou": "KTM",
    "male": "MLE",
    # Central Asia
    "almaty": "ALA",
    "tashkent": "TAS",
    "tachkent": "TAS",
    "baku": "GYD",
    "bakou": "GYD",
    "tbilisi": "TBS",
    "tbilissi": "TBS",
    # West Africa
    "dakar": "DSS",
    "abidjan": "ABJ",
    "lagos": "LOS",
    "accra": "ACC",
    # East Africa
    "nairobi": "NBO",
    "addis ababa": "ADD",
    "addis abeba": "ADD",
    "dar es salaam": "DAR",
    "entebbe": "EBB",
    "kigali": "KGL",
    "zanzibar": "ZNZ",
    # Southern Africa
    "johannesburg": "JNB",
    "cape town": "CPT",
    "le cap": "CPT",
    "durban": "DUR",
    # North Africa
    "tripoli": "TIP",
    # Indian Ocean
    "mauritius": "MRU",
    "maurice": "MRU",
    "ile maurice": "MRU",
    # Oceania
    "sydney": "SYD",
    "melbourne": "MEL",
    "perth": "PER",
    "brisbane": "BNE",
    "auckland": "AKL",
    "christchurch": "CHC",
    # Caribbean
    "havana": "HAV",
    "la havane": "HAV",
    "punta cana": "PUJ",
    "santo domingo": "SDQ",
    "saint domingue": "SDQ",
}

# Map airline display names (from Google Flights) to our internal names
AIRLINE_NAME_MAP = {
    "transavia": "Transavia",
    "air france": "Air France",
    "air arabia": "Air Arabia",
    "air arabia maroc": "Air Arabia",
    "royal air maroc": "Royal Air Maroc",
    "ryanair": "Ryanair",
    "easyjet": "EasyJet",
    "vueling": "Vueling",
    "iberia": "Iberia",
    "iberia express": "Iberia",
    "lufthansa": "Lufthansa",
    "klm": "KLM",
    "tap portugal": "TAP Portugal",
    "tap air portugal": "TAP Portugal",
    "british airways": "British Airways",
    "wizz air": "Wizz Air",
    "american airlines": "American Airlines",
    "american": "American Airlines",
    "emirates": "Emirates",
    "qatar airways": "Qatar Airways",
    "qatar": "Qatar Airways",
    "singapore airlines": "Singapore Airlines",
    "air china": "Air China",
    "turkish airlines": "Turkish Airlines",
    "finnair": "Finnair",
    "air caraibes": "Air Caraibes",
    "air caraïbes": "Air Caraibes",
    "corsair": "Corsair",
    "corsair international": "Corsair",
    "ita airways": "ITA Airways",
    "ita": "ITA Airways",
}


def _resolve_airport(city: str) -> str:
    return resolve_airport(city, CITY_AIRPORT_MAP)


def _normalize_airline(name: str) -> str:
    """Map Google Flights airline name to our internal name."""
    lower = name.strip().lower()
    return AIRLINE_NAME_MAP.get(lower, name.strip())


def _parse_gf_time(raw: str) -> str:
    """Parse Google Flights time format like '8:00 PM on Wed, Apr 1' to 'HH:MM'."""
    if not raw:
        return ""
    # Extract time part before "on"
    time_part = raw.split(" on ")[0].strip() if " on " in raw else raw.strip()
    # Parse 12h format
    m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)", time_part, re.IGNORECASE)
    if m:
        hour = int(m.group(1))
        minute = m.group(2)
        ampm = m.group(3).upper()
        if ampm == "PM" and hour != 12:
            hour += 12
        elif ampm == "AM" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute}"
    # Try 24h format
    m2 = re.match(r"(\d{1,2}):(\d{2})", time_part)
    if m2:
        return f"{int(m2.group(1)):02d}:{m2.group(2)}"
    return ""


def _parse_gf_price(raw: str) -> float:
    """Parse Google Flights price format like '€120' or '$234'."""
    if not raw:
        return 0.0
    cleaned = raw.replace(",", "").replace("\xa0", "")
    m = re.search(r"(\d+\.?\d*)", cleaned)
    if m:
        return float(m.group(1))
    return 0.0


def _run_google_flights_sync(dep: str, arr: str, flight_date: str):
    """Run fast-flights in a synchronous context (separate thread)."""
    from fast_flights import FlightData, Passengers, get_flights

    result = get_flights(
        flight_data=[FlightData(date=flight_date, from_airport=dep, to_airport=arr)],
        trip="one-way",
        seat="economy",
        passengers=Passengers(adults=1),
        fetch_mode="local",
    )
    return result


async def google_flights_bulk_search(
    airline_names: List[str],
    origin_city: str,
    destination_city: str,
    date_from: date,
    date_to: date,
    trip_type: str,
) -> dict:
    """Search Google Flights once and return results grouped by airline name.
    Returns dict: {airline_name: [FlightResult, ...]}
    """
    origin = _resolve_airport(origin_city)
    destination = _resolve_airport(destination_city)

    directions = [("outbound", origin, destination)]
    if trip_type == "roundtrip":
        directions.append(("return", destination, origin))

    # Collect all flights grouped by airline
    by_airline = {name: [] for name in airline_names}
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)

    try:
        for direction, dep, arr in directions:
            current = date_from
            while current <= date_to:
                try:
                    date_str = current.strftime("%Y-%m-%d")
                    gf_result = await loop.run_in_executor(
                        executor, _run_google_flights_sync, dep, arr, date_str
                    )

                    for flight in gf_result.flights:
                        gf_airline = _normalize_airline(flight.name)
                        if gf_airline not in by_airline:
                            continue
                        if flight.stops != 0:
                            continue

                        dep_time = _parse_gf_time(flight.departure)
                        arr_time = _parse_gf_time(flight.arrival)
                        price = _parse_gf_price(flight.price)

                        if dep_time and arr_time and price > 0:
                            by_airline[gf_airline].append(FlightResult(
                                airline=gf_airline,
                                direction=direction,
                                flight_date=current,
                                departure_time=dep_time,
                                arrival_time=arr_time,
                                origin_airport=dep,
                                destination_airport=arr,
                                price=price,
                                currency="EUR",
                            ))
                except Exception as e:
                    logger.warning(f"Google Flights error for {dep}->{arr} on {current}: {e}")

                current += timedelta(days=1)

        # Add route_not_served for airlines with no results
        for name in airline_names:
            if not by_airline[name]:
                for direction, dep, arr in directions:
                    by_airline[name].append(make_route_not_served(name, direction, date_from))

    except Exception as e:
        logger.error(f"Google Flights bulk search error: {e}")
    finally:
        executor.shutdown(wait=False)

    for name, flights in by_airline.items():
        real = sum(1 for f in flights if not f.route_not_served)
        logger.info(f"Google Flights ({name}): {real} direct flights for {origin_city}->{destination_city}")

    return by_airline


async def google_flights_search(
    airline_name: str,
    origin_city: str,
    destination_city: str,
    date_from: date,
    date_to: date,
    trip_type: str,
) -> List[FlightResult]:
    """Search flights for a specific airline via Google Flights."""

    results: List[FlightResult] = []
    origin = _resolve_airport(origin_city)
    destination = _resolve_airport(destination_city)

    directions = [("outbound", origin, destination)]
    if trip_type == "roundtrip":
        directions.append(("return", destination, origin))

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        for direction, dep, arr in directions:
            direction_had_results = False
            current = date_from
            while current <= date_to:
                try:
                    date_str = current.strftime("%Y-%m-%d")
                    gf_result = await loop.run_in_executor(
                        executor, _run_google_flights_sync, dep, arr, date_str
                    )

                    for flight in gf_result.flights:
                        gf_airline = _normalize_airline(flight.name)
                        if gf_airline.lower() != airline_name.lower():
                            continue
                        if flight.stops != 0:
                            continue  # only direct flights

                        dep_time = _parse_gf_time(flight.departure)
                        arr_time = _parse_gf_time(flight.arrival)
                        price = _parse_gf_price(flight.price)

                        if dep_time and arr_time and price > 0:
                            results.append(FlightResult(
                                airline=airline_name,
                                direction=direction,
                                flight_date=current,
                                departure_time=dep_time,
                                arrival_time=arr_time,
                                origin_airport=dep,
                                destination_airport=arr,
                                price=price,
                                currency="EUR",
                            ))
                            direction_had_results = True

                except Exception as e:
                    logger.warning(f"Google Flights error for {dep}->{arr} on {current}: {e}")

                current += timedelta(days=1)

            if not direction_had_results:
                results.append(make_route_not_served(airline_name, direction, date_from))

    except Exception as e:
        logger.error(f"Google Flights scraper error for {airline_name}: {e}")
    finally:
        executor.shutdown(wait=False)

    real_count = sum(1 for r in results if not r.route_not_served)
    logger.info(f"Google Flights ({airline_name}): found {real_count} flights for {origin_city}->{destination_city}")
    return results
