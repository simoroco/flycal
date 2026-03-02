import asyncio
import json
import logging
import random
from datetime import date, timedelta
from typing import List

from .base import FlightResult, ScraperBase

logger = logging.getLogger("flycal.scraper.airfrance")

CITY_AIRPORT_MAP = {
    "paris": "CDG",
    "cdg": "CDG",
    "orly": "ORY",
    "marseille": "MRS",
    "lyon": "LYS",
    "toulouse": "TLS",
    "nice": "NCE",
    "bordeaux": "BOD",
    "nantes": "NTE",
    "montpellier": "MPL",
    "lille": "LIL",
    "strasbourg": "SXB",
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
    "casablanca": "CMN",
    "rabat": "RBA",
    "agadir": "AGA",
    "alger": "ALG",
    "algiers": "ALG",
    "oran": "ORN",
    "tunis": "TUN",
    "new york": "JFK",
    "montreal": "YUL",
    "dakar": "DSS",
    "abidjan": "ABJ",
    "athenes": "ATH",
    "athens": "ATH",
    "budapest": "BUD",
    "prague": "PRG",
    "varsovie": "WAW",
    "warsaw": "WAW",
    "bucarest": "OTP",
    "bucharest": "OTP",
    "stockholm": "ARN",
    "oslo": "OSL",
    "copenhague": "CPH",
    "copenhagen": "CPH",
}


def _resolve_airport(city: str) -> str:
    normalized = city.strip().lower()
    return CITY_AIRPORT_MAP.get(normalized, normalized.upper()[:3])


class AirFranceScraper(ScraperBase):
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
                                "availability", "search", "offers", "lowest-fare",
                                "flight-search", "upsell"
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
                            f"https://www.airfrance.fr/search/offers"
                            f"?pax=1:0:0:0:0:0:0:0"
                            f"&cabinClass=ECONOMY"
                            f"&activeConnection=0"
                            f"&connections={dep}-A>{arr}-A-{date_str}"
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
                        logger.error(f"Air France error for {dep}->{arr} on {current}: {e}")
                    current += timedelta(days=1)

        except Exception as e:
            logger.error(f"Air France browser error: {e}")
        finally:
            await self._close_browser()

        logger.info(f"Air France: found {len(results)} flights for {origin_city}->{destination_city}")
        return results

    def _parse_response(self, data, direction, dep, arr, flight_date) -> List[FlightResult]:
        results = []
        try:
            if not isinstance(data, dict):
                return results

            itineraries = []
            for key in ("itineraries", "connections", "boundOffers", "flightProducts",
                        "recommendations", "flights", "offers"):
                if key in data:
                    val = data[key]
                    if isinstance(val, list):
                        itineraries = val
                        break
                    elif isinstance(val, dict):
                        for sub_key in val:
                            if isinstance(val[sub_key], list):
                                itineraries = val[sub_key]
                                break

            for itin in itineraries:
                if not isinstance(itin, dict):
                    continue

                segments = itin.get("segments", itin.get("flights", itin.get("legs", [itin])))
                if isinstance(segments, list) and len(segments) > 1:
                    continue  # skip connecting flights

                seg = segments[0] if isinstance(segments, list) and segments else itin

                dep_time = seg.get("departureTime", seg.get("departureDateTime",
                           seg.get("departure", {}).get("time", "")))
                arr_time = seg.get("arrivalTime", seg.get("arrivalDateTime",
                           seg.get("arrival", {}).get("time", "")))

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
                for airport_key in ("departureAirport", "origin", "departure"):
                    a = seg.get(airport_key)
                    if isinstance(a, dict):
                        origin_code = a.get("iataCode", a.get("code", dep))
                        break
                    elif isinstance(a, str) and len(a) == 3:
                        origin_code = a
                        break
                for airport_key in ("arrivalAirport", "destination", "arrival"):
                    a = seg.get(airport_key)
                    if isinstance(a, dict):
                        dest_code = a.get("iataCode", a.get("code", arr))
                        break
                    elif isinstance(a, str) and len(a) == 3:
                        dest_code = a
                        break

                price = None
                for pk in ("price", "totalPrice", "lowestPrice", "fare", "amount"):
                    pv = itin.get(pk, seg.get(pk))
                    if pv is not None:
                        if isinstance(pv, (int, float)):
                            price = float(pv)
                        elif isinstance(pv, dict):
                            price = float(pv.get("amount", pv.get("value", pv.get("totalAmount", 0))))
                        break

                if price and price > 0 and dep_time and arr_time:
                    results.append(FlightResult(
                        airline="Air France",
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
            logger.error(f"Air France parse error: {e}")
        return results

    async def _parse_dom(self, page, direction, dep, arr, flight_date) -> List[FlightResult]:
        results = []
        try:
            cards = await page.query_selector_all(
                "[class*='flight'], [class*='result'], [class*='offer'], [data-testid*='flight']"
            )
            for card in cards:
                try:
                    text = await card.inner_text()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    price = None
                    dep_time = None
                    arr_time = None
                    for line in lines:
                        if "€" in line or "EUR" in line:
                            digits = "".join(c for c in line.replace(",", ".").replace(" ", "")
                                             if c.isdigit() or c == ".")
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
                            airline="Air France",
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
            logger.error(f"Air France DOM parse error: {e}")
        return results
