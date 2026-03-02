import asyncio
import json
import logging
import random
from datetime import date, timedelta
from typing import List

from .base import FlightResult, ScraperBase

logger = logging.getLogger("flycal.scraper.airarabia")

CITY_AIRPORT_MAP = {
    "paris": "ORY",
    "marseille": "MRS",
    "lyon": "LYS",
    "toulouse": "TLS",
    "bordeaux": "BOD",
    "nantes": "NTE",
    "nice": "NCE",
    "montpellier": "MPL",
    "lille": "LIL",
    "bruxelles": "BRU",
    "brussels": "BRU",
    "amsterdam": "AMS",
    "london": "LGW",
    "londres": "LGW",
    "barcelona": "BCN",
    "barcelone": "BCN",
    "madrid": "MAD",
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
    "cairo": "CAI",
    "le caire": "CAI",
    "dubai": "SHJ",
    "sharjah": "SHJ",
    "abu dhabi": "AUH",
    "istanbul": "SAW",
    "amman": "AMM",
    "alexandrie": "HBE",
    "alexandria": "HBE",
}


def _resolve_airport(city: str) -> str:
    normalized = city.strip().lower()
    return CITY_AIRPORT_MAP.get(normalized, normalized.upper()[:3])


class AirArabiaScraper(ScraperBase):
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
                            if any(k in url.lower() for k in (
                                "availability", "search", "flight", "fare", "offer"
                            )):
                                try:
                                    ct = response.headers.get("content-type", "")
                                    if "json" in ct:
                                        body = await response.json()
                                        captured_responses.append(body)
                                except Exception:
                                    pass

                        page.on("response", handle_response)

                        date_str = current.strftime("%Y-%m-%d")
                        search_url = (
                            f"https://www.airarabia.com/en/booking"
                            f"?tripType={'R' if trip_type == 'roundtrip' else 'O'}"
                            f"&origin={dep}&destination={arr}"
                            f"&departDate={date_str}"
                            f"&adults=1&children=0&infants=0"
                        )

                        await page.goto(search_url, wait_until="networkidle", timeout=45000)
                        await asyncio.sleep(random.uniform(3, 6))
                        await self._handle_captcha(page)

                        page.remove_listener("response", handle_response)

                        for resp_data in captured_responses:
                            flights = self._parse_response(resp_data, direction, dep, arr, current)
                            results.extend(flights)

                        if not captured_responses:
                            dom_flights = await self._parse_dom(page, direction, dep, arr, current)
                            results.extend(dom_flights)

                    except Exception as e:
                        logger.error(f"Air Arabia error for {dep}->{arr} on {current}: {e}")
                    current += timedelta(days=1)

        except Exception as e:
            logger.error(f"Air Arabia browser error: {e}")
        finally:
            await self._close_browser()

        logger.info(f"Air Arabia: found {len(results)} flights for {origin_city}->{destination_city}")
        return results

    def _parse_response(self, data, direction, dep, arr, flight_date) -> List[FlightResult]:
        results = []
        try:
            if not isinstance(data, dict):
                return results

            flights_list = []
            for key in ("flights", "journeys", "availability", "flightList",
                        "outbound", "offers", "results"):
                if key in data:
                    val = data[key]
                    if isinstance(val, list):
                        flights_list = val
                        break
                    elif isinstance(val, dict):
                        for sub_key in val:
                            if isinstance(val[sub_key], list):
                                flights_list = val[sub_key]
                                break

            for flight in flights_list:
                if not isinstance(flight, dict):
                    continue

                segments = flight.get("segments", flight.get("legs", [flight]))
                if isinstance(segments, list) and len(segments) > 1:
                    continue

                seg = segments[0] if isinstance(segments, list) and segments else flight

                dep_time = seg.get("departureTime", seg.get("std", ""))
                arr_time = seg.get("arrivalTime", seg.get("sta", ""))

                if isinstance(dep_time, str) and "T" in dep_time:
                    dep_time = dep_time.split("T")[1][:5]
                elif isinstance(dep_time, str) and len(dep_time) > 5:
                    dep_time = dep_time[:5]

                if isinstance(arr_time, str) and "T" in arr_time:
                    arr_time = arr_time.split("T")[1][:5]
                elif isinstance(arr_time, str) and len(arr_time) > 5:
                    arr_time = arr_time[:5]

                origin_code = dep
                dest_code = arr
                for ak in ("departureStation", "origin", "departureAirport"):
                    a = seg.get(ak)
                    if isinstance(a, str) and len(a) == 3:
                        origin_code = a
                        break
                    elif isinstance(a, dict):
                        origin_code = a.get("code", a.get("iataCode", dep))
                        break
                for ak in ("arrivalStation", "destination", "arrivalAirport"):
                    a = seg.get(ak)
                    if isinstance(a, str) and len(a) == 3:
                        dest_code = a
                        break
                    elif isinstance(a, dict):
                        dest_code = a.get("code", a.get("iataCode", arr))
                        break

                price = None
                for pk in ("price", "fare", "totalPrice", "lowestFare", "amount"):
                    pv = flight.get(pk, seg.get(pk))
                    if pv is not None:
                        if isinstance(pv, (int, float)):
                            price = float(pv)
                        elif isinstance(pv, dict):
                            price = float(pv.get("amount", pv.get("value", 0)))
                        break

                if price and price > 0 and dep_time and arr_time:
                    results.append(FlightResult(
                        airline="Air Arabia",
                        direction=direction,
                        flight_date=flight_date,
                        departure_time=str(dep_time)[:5],
                        arrival_time=str(arr_time)[:5],
                        origin_airport=str(origin_code)[:3] if origin_code else dep,
                        destination_airport=str(dest_code)[:3] if dest_code else arr,
                        price=price,
                        currency="EUR",
                    ))
        except Exception as e:
            logger.error(f"Air Arabia parse error: {e}")
        return results

    async def _parse_dom(self, page, direction, dep, arr, flight_date) -> List[FlightResult]:
        results = []
        try:
            cards = await page.query_selector_all(
                "[class*='flight'], [class*='result'], [class*='fare'], [class*='journey']"
            )
            for card in cards:
                try:
                    text = await card.inner_text()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    price = None
                    dep_time = None
                    arr_time = None
                    for line in lines:
                        cleaned = line.replace(",", ".").replace(" ", "")
                        if any(c in line for c in ("€", "EUR", "eur")):
                            digits = "".join(c for c in cleaned if c.isdigit() or c == ".")
                            if digits:
                                try:
                                    price = float(digits)
                                except ValueError:
                                    pass
                        elif ":" in line and len(line) <= 5 and line.replace(":", "").isdigit():
                            if dep_time is None:
                                dep_time = line
                            elif arr_time is None:
                                arr_time = line
                    if price and price > 0 and dep_time and arr_time:
                        results.append(FlightResult(
                            airline="Air Arabia",
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
            logger.error(f"Air Arabia DOM parse error: {e}")
        return results
