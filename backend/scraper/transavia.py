import asyncio
import json
import logging
import random
from datetime import date, timedelta
from typing import List

from .base import FlightResult, ScraperBase

logger = logging.getLogger("flycal.scraper.transavia")

CITY_AIRPORT_MAP = {
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
    "porto": "OPO",
    "lisbonne": "LIS",
    "lisbon": "LIS",
    "madrid": "MAD",
    "barcelone": "BCN",
    "barcelona": "BCN",
    "rome": "FCO",
    "milan": "MXP",
    "london": "LTN",
    "londres": "LTN",
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
}


def _resolve_airport(city: str) -> str:
    normalized = city.strip().lower()
    return CITY_AIRPORT_MAP.get(normalized, normalized.upper()[:3])


class TransaviaScraper(ScraperBase):
    async def search(
        self,
        origin_city: str,
        destination_city: str,
        date_from: date,
        date_to: date,
        trip_type: str,
    ) -> List[FlightResult]:
        return await self._retry(
            self._do_search, origin_city, destination_city, date_from, date_to, trip_type
        )

    async def _do_search(
        self,
        origin_city: str,
        destination_city: str,
        date_from: date,
        date_to: date,
        trip_type: str,
    ) -> List[FlightResult]:
        results: List[FlightResult] = []
        origin = _resolve_airport(origin_city)
        destination = _resolve_airport(destination_city)

        directions = [("outbound", origin, destination)]
        if trip_type == "roundtrip":
            directions.append(("return", destination, origin))

        page = None
        try:
            page = await self._init_browser()

            for direction, dep, arr in directions:
                current = date_from
                while current <= date_to:
                    try:
                        captured_responses = []

                        async def handle_response(response):
                            url = response.url
                            if "availability" in url.lower() or "search" in url.lower():
                                try:
                                    body = await response.json()
                                    captured_responses.append(body)
                                except Exception:
                                    pass

                        page.on("response", handle_response)

                        search_url = (
                            f"https://www.transavia.com/fr-FR/book-a-flight/flights/search/"
                            f"?routeSelection={dep}-{arr}"
                            f"&dateSelection={current.isoformat()}"
                            f"&flexibleSearch=false"
                            f"&selectPassengers=1"
                        )
                        await page.goto(search_url, wait_until="networkidle", timeout=30000)
                        await asyncio.sleep(random.uniform(2, 4))

                        page.remove_listener("response", handle_response)

                        for resp_data in captured_responses:
                            flights = self._parse_api_response(resp_data, direction, dep, arr, current)
                            results.extend(flights)

                        if not captured_responses:
                            dom_flights = await self._parse_dom(page, direction, dep, arr, current)
                            results.extend(dom_flights)

                    except Exception as e:
                        logger.error(f"Transavia error for {dep}->{arr} on {current}: {e}")
                    current += timedelta(days=1)

        except Exception as e:
            logger.error(f"Transavia browser error: {e}")
        finally:
            await self._close_browser()

        logger.info(f"Transavia: found {len(results)} flights for {origin_city}->{destination_city}")
        return results

    def _parse_api_response(self, data, direction, dep, arr, flight_date) -> List[FlightResult]:
        results = []
        try:
            journeys = []
            if isinstance(data, dict):
                for key in ("outboundFlights", "flights", "journeys", "flightOffer"):
                    if key in data:
                        val = data[key]
                        if isinstance(val, list):
                            journeys = val
                            break
                        elif isinstance(val, dict):
                            for sub_key in val:
                                if isinstance(val[sub_key], list):
                                    journeys = val[sub_key]
                                    break

            for flight in journeys:
                if isinstance(flight, dict):
                    segments = flight.get("segments", flight.get("flightSegments", [flight]))
                    if isinstance(segments, list) and len(segments) > 1:
                        continue  # skip non-direct

                    seg = segments[0] if segments else flight
                    dep_time = seg.get("departureTime", seg.get("departureDateTime", ""))
                    arr_time = seg.get("arrivalTime", seg.get("arrivalDateTime", ""))
                    if isinstance(dep_time, str) and len(dep_time) > 5:
                        dep_time = dep_time[11:16] if "T" in dep_time else dep_time[:5]
                    if isinstance(arr_time, str) and len(arr_time) > 5:
                        arr_time = arr_time[11:16] if "T" in arr_time else arr_time[:5]

                    origin_iata = seg.get("origin", seg.get("departureAirport", {
                    })).get("iataCode", dep) if isinstance(seg.get("origin", seg.get("departureAirport")), dict) else dep
                    dest_iata = seg.get("destination", seg.get("arrivalAirport", {
                    })).get("iataCode", arr) if isinstance(seg.get("destination", seg.get("arrivalAirport")), dict) else arr

                    price = None
                    for price_key in ("price", "priceFrom", "fare", "totalPrice"):
                        if price_key in flight:
                            pval = flight[price_key]
                            if isinstance(pval, (int, float)):
                                price = float(pval)
                            elif isinstance(pval, dict):
                                price = float(pval.get("amount", pval.get("value", 0)))
                            break

                    if price and price > 0 and dep_time and arr_time:
                        results.append(FlightResult(
                            airline="Transavia",
                            direction=direction,
                            flight_date=flight_date,
                            departure_time=str(dep_time)[:5],
                            arrival_time=str(arr_time)[:5],
                            origin_airport=str(origin_iata)[:3] if origin_iata else dep,
                            destination_airport=str(dest_iata)[:3] if dest_iata else arr,
                            price=price,
                            currency="EUR",
                        ))
        except Exception as e:
            logger.error(f"Transavia parse error: {e}")
        return results

    async def _parse_dom(self, page, direction, dep, arr, flight_date) -> List[FlightResult]:
        results = []
        try:
            cards = await page.query_selector_all("[class*='flight'], [class*='result'], [data-testid*='flight']")
            for card in cards:
                try:
                    text = await card.inner_text()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    price = None
                    dep_time = None
                    arr_time = None
                    for line in lines:
                        if "€" in line:
                            digits = "".join(c for c in line.replace(",", ".") if c.isdigit() or c == ".")
                            if digits:
                                price = float(digits)
                        elif ":" in line and len(line) <= 5:
                            if dep_time is None:
                                dep_time = line
                            elif arr_time is None:
                                arr_time = line
                    if price and price > 0 and dep_time and arr_time:
                        results.append(FlightResult(
                            airline="Transavia",
                            direction=direction,
                            flight_date=flight_date,
                            departure_time=dep_time,
                            arrival_time=arr_time,
                            origin_airport=dep,
                            destination_airport=arr,
                            price=price,
                            currency="EUR",
                        ))
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Transavia DOM parse error: {e}")
        return results
