"""
Amadeus API-based flight scraper.

Uses the Amadeus Flight Offers Search API as a reliable fallback for airlines
whose websites block headless browsers (Cloudflare, anti-bot, etc.).

Requires AMADEUS_API_KEY and AMADEUS_API_SECRET env vars.
Sign up free at https://developers.amadeus.com/
"""

import logging
import os
from datetime import date, timedelta
from typing import List

from .base import FlightResult, make_route_not_served, parse_time

logger = logging.getLogger("flycal.scraper.amadeus")

# Map airline display names to IATA carrier codes
AIRLINE_IATA_CODES = {
    "Transavia": ["TO", "HV"],
    "Air France": ["AF"],
    "Air Arabia": ["G9", "3L", "E5"],
    "Royal Air Maroc": ["AT"],
    "Ryanair": ["FR"],
}

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
    "london": "LON",
    "londres": "LON",
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


def _resolve_airport(city: str) -> str:
    normalized = city.strip().lower()
    return CITY_AIRPORT_MAP.get(normalized, normalized.upper()[:3])


def is_amadeus_configured() -> bool:
    return bool(os.environ.get("AMADEUS_API_KEY") and os.environ.get("AMADEUS_API_SECRET"))


def _get_amadeus_client():
    from amadeus import Amadeus
    key = os.environ.get("AMADEUS_API_KEY", "")
    secret = os.environ.get("AMADEUS_API_SECRET", "")
    if not key or not secret:
        return None
    hostname = os.environ.get("AMADEUS_HOSTNAME", "test")
    return Amadeus(client_id=key, client_secret=secret, hostname=hostname)


async def amadeus_search(
    airline_name: str,
    origin_city: str,
    destination_city: str,
    date_from: date,
    date_to: date,
    trip_type: str,
) -> List[FlightResult]:
    """Search flights for a specific airline via Amadeus API."""

    if not is_amadeus_configured():
        logger.debug("Amadeus API not configured, skipping")
        return []

    import asyncio

    results: List[FlightResult] = []
    origin = _resolve_airport(origin_city)
    destination = _resolve_airport(destination_city)
    carrier_codes = AIRLINE_IATA_CODES.get(airline_name, [])

    if not carrier_codes:
        logger.warning(f"No IATA codes configured for {airline_name}")
        return []

    directions = [("outbound", origin, destination)]
    if trip_type == "roundtrip":
        directions.append(("return", destination, origin))

    try:
        client = _get_amadeus_client()
        if not client:
            return []

        for direction, dep, arr in directions:
            direction_had_results = False
            current = date_from
            while current <= date_to:
                try:
                    date_str = current.strftime("%Y-%m-%d")
                    # Run the API call in a thread to not block the event loop
                    response = await asyncio.to_thread(
                        client.shopping.flight_offers_search.get,
                        originLocationCode=dep,
                        destinationLocationCode=arr,
                        departureDate=date_str,
                        adults=1,
                        nonStop="true",
                        currencyCode="EUR",
                        max=20,
                    )

                    for offer in response.data:
                        try:
                            itineraries = offer.get("itineraries", [])
                            if not itineraries:
                                continue

                            itin = itineraries[0]
                            segments = itin.get("segments", [])
                            if len(segments) != 1:
                                continue  # only direct flights

                            seg = segments[0]
                            carrier = seg.get("carrierCode", "")
                            if carrier not in carrier_codes:
                                continue

                            dep_time = parse_time(seg.get("departure", {}).get("at", ""))
                            arr_time = parse_time(seg.get("arrival", {}).get("at", ""))
                            dep_iata = seg.get("departure", {}).get("iataCode", dep)
                            arr_iata = seg.get("arrival", {}).get("iataCode", arr)

                            price = 0.0
                            try:
                                price = float(offer.get("price", {}).get("total", 0))
                            except (ValueError, TypeError):
                                pass

                            if dep_time and arr_time and price > 0:
                                results.append(FlightResult(
                                    airline=airline_name,
                                    direction=direction,
                                    flight_date=current,
                                    departure_time=dep_time,
                                    arrival_time=arr_time,
                                    origin_airport=dep_iata,
                                    destination_airport=arr_iata,
                                    price=price,
                                    currency="EUR",
                                ))
                                direction_had_results = True

                        except Exception as e:
                            logger.debug(f"Amadeus offer parse error: {e}")
                            continue

                except Exception as e:
                    logger.warning(f"Amadeus API error for {dep}->{arr} on {current}: {e}")

                current += timedelta(days=1)

            if not direction_had_results:
                results.append(make_route_not_served(airline_name, direction, date_from))

    except Exception as e:
        logger.error(f"Amadeus scraper error for {airline_name}: {e}")

    logger.info(f"Amadeus ({airline_name}): found {len(results)} results for {origin_city}->{destination_city}")
    return results
