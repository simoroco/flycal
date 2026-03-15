import asyncio
import json
import logging
import random
import re
from datetime import date, timedelta
from typing import List

from .base import FlightResult, ScraperBase, make_route_not_served, parse_time, parse_price

logger = logging.getLogger("flycal.scraper.royalairmaroc")

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
    "oujda": "OUD",
    "nador": "NDR",
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
    "istanbul": "IST",
    "dubai": "DXB",
    "doha": "DOH",
    "le caire": "CAI",
    "cairo": "CAI",
}


def _resolve_airport(city: str) -> str:
    normalized = city.strip().lower()
    return CITY_AIRPORT_MAP.get(normalized, normalized.upper()[:3])


class RoyalAirMarocScraper(ScraperBase):
    AIRLINE = "Royal Air Maroc"

    async def _init_browser(self):
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.firefox.launch(headless=True)
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
            locale="fr-FR",
            ignore_https_errors=True,
        )
        page = await self.context.new_page()
        return page

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

            # Visit homepage first for session/cookies
            await page.goto("https://www.royalairmaroc.com/fr-fr", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1)
            await self._dismiss_cookies(page)
            await asyncio.sleep(1)

            for direction, dep, arr in directions:
                day_had_results = False
                current = date_from
                while current <= date_to:
                    try:
                        captured_responses = []

                        async def handle_response(response):
                            url = response.url
                            if any(k in url.lower() for k in (
                                "availability", "search", "flight", "fare",
                                "offer", "/api/", "calendar", "schedule"
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
                        # Royal Air Maroc search URL pattern
                        search_url = (
                            f"https://www.royalairmaroc.com/fr-fr/book"
                            f"?from={dep}&to={arr}"
                            f"&departure={date_str}"
                            f"&adults=1&children=0&infants=0"
                            f"&tripType={'RT' if trip_type == 'roundtrip' else 'OW'}"
                            f"&cabin=ECONOMY"
                        )

                        await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                        await asyncio.sleep(random.uniform(3, 6))
                        await self._dismiss_cookies(page)

                        # Wait for results or error
                        try:
                            await page.wait_for_selector(
                                "[class*='flight'], [class*='result'], [class*='fare'], [class*='offer'], [class*='no-result'], [class*='error']",
                                timeout=20000,
                            )
                        except Exception:
                            pass

                        await asyncio.sleep(2)
                        page.remove_listener("response", handle_response)

                        day_results = []
                        for resp_data in captured_responses:
                            flights = self._parse_response(resp_data, direction, dep, arr, current)
                            day_results.extend(flights)

                        if not day_results:
                            dom_flights = await self._parse_dom(page, direction, dep, arr, current)
                            day_results.extend(dom_flights)

                        if day_results:
                            day_had_results = True
                        results.extend(day_results)

                    except Exception as e:
                        logger.error(f"Royal Air Maroc error for {dep}->{arr} on {current}: {e}")
                    current += timedelta(days=1)

                if not day_had_results:
                    results.append(make_route_not_served(self.AIRLINE, direction, date_from))

        except Exception as e:
            logger.error(f"Royal Air Maroc browser error: {e}")
        finally:
            await self._close_browser()

        logger.info(f"Royal Air Maroc: found {len(results)} flights for {origin_city}->{destination_city}")
        return results

    def _parse_response(self, data, direction, dep, arr, flight_date) -> List[FlightResult]:
        results = []
        try:
            if not isinstance(data, dict):
                return results

            flights_list = []
            for key in ("flights", "journeys", "itineraries", "boundOffers",
                        "flightProducts", "offers", "results", "outboundFlights",
                        "availability", "recommendations"):
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
                        if flights_list:
                            break

            for flight in flights_list:
                if not isinstance(flight, dict):
                    continue

                segments = flight.get("segments", flight.get("legs", flight.get("flights", [flight])))
                if isinstance(segments, list) and len(segments) > 1:
                    continue  # skip connecting flights

                seg = segments[0] if isinstance(segments, list) and segments else flight

                raw_dep = seg.get("departureTime", seg.get("departureDateTime",
                          seg.get("departure", {}).get("time", "") if isinstance(seg.get("departure"), dict) else seg.get("std", "")))
                raw_arr = seg.get("arrivalTime", seg.get("arrivalDateTime",
                          seg.get("arrival", {}).get("time", "") if isinstance(seg.get("arrival"), dict) else seg.get("sta", "")))
                dep_time = parse_time(str(raw_dep))
                arr_time = parse_time(str(raw_arr))

                origin_code = dep
                dest_code = arr
                for ak in ("departureAirport", "origin", "departure", "departureStation"):
                    a = seg.get(ak)
                    if isinstance(a, dict):
                        origin_code = a.get("iataCode", a.get("code", dep))
                        break
                    elif isinstance(a, str) and len(a) == 3:
                        origin_code = a
                        break
                for ak in ("arrivalAirport", "destination", "arrival", "arrivalStation"):
                    a = seg.get(ak)
                    if isinstance(a, dict):
                        dest_code = a.get("iataCode", a.get("code", arr))
                        break
                    elif isinstance(a, str) and len(a) == 3:
                        dest_code = a
                        break

                price = 0.0
                for pk in ("price", "totalPrice", "lowestPrice", "fare", "amount"):
                    pv = flight.get(pk, seg.get(pk))
                    if pv is not None:
                        if isinstance(pv, dict):
                            price = parse_price(pv.get("amount", pv.get("value", pv.get("totalAmount", 0))))
                        else:
                            price = parse_price(pv)
                        break

                if price > 0 and dep_time and arr_time:
                    results.append(FlightResult(
                        airline=self.AIRLINE,
                        direction=direction,
                        flight_date=flight_date,
                        departure_time=dep_time,
                        arrival_time=arr_time,
                        origin_airport=str(origin_code)[:3],
                        destination_airport=str(dest_code)[:3],
                        price=price,
                        currency="EUR",
                    ))
        except Exception as e:
            logger.error(f"Royal Air Maroc parse error: {e}")
        return results

    async def _parse_dom(self, page, direction, dep, arr, flight_date) -> List[FlightResult]:
        results = []
        try:
            selectors = [
                "[class*='flight-result']",
                "[class*='flight-card']",
                "[class*='offer-card']",
                "[class*='fare-card']",
                "[data-testid*='flight']",
                "[data-testid*='offer']",
                "section[class*='flight']",
            ]
            cards = []
            for sel in selectors:
                cards = await page.query_selector_all(sel)
                if cards:
                    break

            if not cards:
                cards = await page.query_selector_all(
                    "[class*='flight'], [class*='result'], [class*='offer'], [class*='fare']"
                )

            for card in cards:
                try:
                    text = await card.inner_text()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    price = 0.0
                    dep_time = None
                    arr_time = None
                    for line in lines:
                        if any(c in line for c in ("€", "EUR", "MAD", "eur")):
                            p = parse_price(line)
                            if p > 0:
                                price = p
                        else:
                            t = parse_time(line)
                            if t and re.match(r"\d{2}:\d{2}$", t):
                                if dep_time is None:
                                    dep_time = t
                                elif arr_time is None:
                                    arr_time = t
                    if price > 0 and dep_time and arr_time:
                        results.append(FlightResult(
                            airline=self.AIRLINE,
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
            logger.error(f"Royal Air Maroc DOM parse error: {e}")
        return results
