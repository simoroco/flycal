"""
Transavia scraper — delegates to Google Flights via fast-flights.

Transavia.com uses Cloudflare protection that blocks all headless browser
searches. Instead, we use Google Flights (via fast-flights library) as the
data source for Transavia flight availability and pricing.
"""
import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import List

from .base import FlightResult, ScraperBase, make_route_not_served, resolve_airport

logger = logging.getLogger("flycal.scraper.transavia")

CITY_AIRPORT_MAP = {
    # France
    "paris": "ORY",
    "orly": "ORY",
    "marseille": "MRS",
    "lyon": "LYS",
    "toulouse": "TLS",
    "nantes": "NTE",
    "montpellier": "MPL",
    "bordeaux": "BOD",
    "lille": "LIL",
    "nice": "NCE",
    "strasbourg": "SXB",
    # Portugal
    "porto": "OPO",
    "lisbonne": "LIS",
    "lisbon": "LIS",
    "faro": "FAO",
    "funchal": "FNC",
    # Spain
    "madrid": "MAD",
    "barcelone": "BCN",
    "barcelona": "BCN",
    "malaga": "AGP",
    "seville": "SVQ",
    "valencia": "VLC",
    "palma": "PMI",
    "palma de mallorca": "PMI",
    "ibiza": "IBZ",
    "tenerife": "TFS",
    "gran canaria": "LPA",
    "alicante": "ALC",
    # Italy
    "rome": "FCO",
    "milan": "MXP",
    "venice": "VCE",
    "naples": "NAP",
    "florence": "FLR",
    "bologna": "BLQ",
    "turin": "TRN",
    "catania": "CTA",
    "bari": "BRI",
    # United Kingdom
    "london": "LTN",
    "londres": "LTN",
    # Ireland
    "dublin": "DUB",
    # Netherlands
    "amsterdam": "AMS",
    # Belgium
    "bruxelles": "BRU",
    "brussels": "BRU",
    # Germany
    "berlin": "BER",
    "munich": "MUC",
    # Scandinavia
    "copenhague": "CPH",
    "copenhagen": "CPH",
    "stockholm": "ARN",
    # Eastern Europe
    "prague": "PRG",
    "budapest": "BUD",
    "cracovie": "KRK",
    "krakow": "KRK",
    "bucarest": "OTP",
    "bucharest": "OTP",
    # Greece
    "athenes": "ATH",
    "athens": "ATH",
    "santorini": "JTR",
    "mykonos": "JMK",
    "heraklion": "HER",
    "rhodes": "RHO",
    "corfu": "CFU",
    # Turkey
    "istanbul": "IST",
    "antalya": "AYT",
    "bodrum": "BJV",
    "izmir": "ADB",
    # Malta
    "malta": "MLA",
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
    "cairo": "CAI",
    "le caire": "CAI",
    "hurghada": "HRG",
    "sharm el sheikh": "SSH",
}


def _resolve_airport(city: str) -> str:
    return resolve_airport(city, CITY_AIRPORT_MAP)


def _parse_gf_time(raw: str) -> str:
    """Parse Google Flights time like '7:40 AM on Sun, Apr 5' → '07:40'."""
    if not raw:
        return ""
    time_part = raw.split(" on ")[0].strip() if " on " in raw else raw.strip()
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
    m2 = re.match(r"(\d{1,2}):(\d{2})", time_part)
    if m2:
        return f"{int(m2.group(1)):02d}:{m2.group(2)}"
    return ""


def _parse_gf_price(raw: str) -> float:
    if not raw:
        return 0.0
    cleaned = raw.replace(",", "").replace("\xa0", "")
    m = re.search(r"(\d+\.?\d*)", cleaned)
    return float(m.group(1)) if m else 0.0


def _fetch_day(dep: str, arr: str, date_str: str):
    """Run fast-flights for a single day (blocking — run in executor)."""
    from fast_flights import FlightData, Passengers, get_flights

    return get_flights(
        flight_data=[FlightData(date=date_str, from_airport=dep, to_airport=arr)],
        trip="one-way",
        seat="economy",
        passengers=Passengers(adults=1),
        fetch_mode="local",
    )


class TransaviaScraper(ScraperBase):
    AIRLINE = "Transavia"

    async def search(
        self, origin_city: str, destination_city: str,
        date_from: date, date_to: date, trip_type: str,
    ) -> List[FlightResult]:
        results: List[FlightResult] = []
        origin = _resolve_airport(origin_city)
        destination = _resolve_airport(destination_city)

        directions = [("outbound", origin, destination)]
        if trip_type == "roundtrip":
            directions.append(("return", destination, origin))

        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=2)

        try:
          for direction, dep, arr in directions:
            direction_results = []
            seen = set()
            current = date_from
            while current <= date_to:
                try:
                    date_str = current.strftime("%Y-%m-%d")
                    gf_result = await loop.run_in_executor(
                        executor, _fetch_day, dep, arr, date_str
                    )

                    for flight in gf_result.flights:
                        airline = (flight.name or "").strip()
                        if airline.lower() != "transavia":
                            continue
                        if flight.stops != 0:
                            continue

                        dep_time = _parse_gf_time(flight.departure)
                        arr_time = _parse_gf_time(flight.arrival)
                        price = _parse_gf_price(flight.price)

                        if dep_time and arr_time and price > 0:
                            key = (current, dep_time, arr_time, dep, arr)
                            if key in seen:
                                continue
                            seen.add(key)
                            direction_results.append(FlightResult(
                                airline=self.AIRLINE,
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
                    logger.warning(f"Transavia GF error {dep}->{arr} on {current}: {e}")

                current += timedelta(days=1)

            if direction_results:
                results.extend(direction_results)
                logger.info(
                    f"Transavia: {len(direction_results)} flights ({direction}) "
                    f"for {origin_city}->{destination_city}"
                )
            else:
                results.append(make_route_not_served(self.AIRLINE, direction, date_from))

        finally:
            executor.shutdown(wait=False)

        real_count = sum(1 for r in results if not r.route_not_served)
        logger.info(f"Transavia: total {real_count} flights for {origin_city}->{destination_city}")
        return results
