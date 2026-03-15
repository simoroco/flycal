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

from .base import FlightResult, make_route_not_served, parse_price

logger = logging.getLogger("flycal.scraper.google_flights")

CITY_AIRPORT_MAP = {
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
    "porto": "OPO",
    "lisbonne": "LIS",
    "lisbon": "LIS",
    "madrid": "MAD",
    "barcelone": "BCN",
    "barcelona": "BCN",
    "rome": "FCO",
    "milan": "MXP",
    "london": "LHR",
    "londres": "LHR",
    "dublin": "DUB",
    "amsterdam": "AMS",
    "bruxelles": "BRU",
    "brussels": "BRU",
    "berlin": "BER",
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
    "alger": "ALG",
    "algiers": "ALG",
    "oran": "ORN",
    "tunis": "TUN",
    "malaga": "AGP",
    "seville": "SVQ",
    "palma": "PMI",
    "athenes": "ATH",
    "athens": "ATH",
    "budapest": "BUD",
    "prague": "PRG",
    "cracovie": "KRK",
    "krakow": "KRK",
    "new york": "JFK",
    "montreal": "YUL",
    "dakar": "DSS",
    "abidjan": "ABJ",
    "istanbul": "IST",
    "dubai": "DXB",
    "doha": "DOH",
    "le caire": "CAI",
    "cairo": "CAI",
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
    "lufthansa": "Lufthansa",
    "klm": "KLM",
    "tap portugal": "TAP Portugal",
    "tap air portugal": "TAP Portugal",
    "british airways": "British Airways",
    "wizz air": "Wizz Air",
}


def _resolve_airport(city: str) -> str:
    normalized = city.strip().lower()
    return CITY_AIRPORT_MAP.get(normalized, normalized.upper()[:3])


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

    try:
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=1)

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

    real_count = sum(1 for r in results if not r.route_not_served)
    logger.info(f"Google Flights ({airline_name}): found {real_count} flights for {origin_city}->{destination_city}")
    return results
