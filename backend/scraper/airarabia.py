import asyncio
import json
import logging
import random
import re
from datetime import date, timedelta
from typing import List

from .base import FlightResult, ScraperBase, make_route_not_served, parse_time, parse_price, resolve_airport

logger = logging.getLogger("flycal.scraper.airarabia")

CITY_AIRPORT_MAP = {
    # France
    "paris": "ORY",
    "marseille": "MRS",
    "lyon": "LYS",
    "toulouse": "TLS",
    "bordeaux": "BOD",
    "nantes": "NTE",
    "nice": "NCE",
    "montpellier": "MPL",
    "lille": "LIL",
    "strasbourg": "SXB",
    # Spain
    "barcelona": "BCN",
    "barcelone": "BCN",
    "madrid": "MAD",
    "malaga": "AGP",
    "valencia": "VLC",
    "alicante": "ALC",
    # Italy
    "rome": "FCO",
    "milan": "MXP",
    "naples": "NAP",
    "bologna": "BLQ",
    # United Kingdom
    "london": "LGW",
    "londres": "LGW",
    "manchester": "MAN",
    # Belgium
    "bruxelles": "BRU",
    "brussels": "BRU",
    # Netherlands
    "amsterdam": "AMS",
    # Germany
    "berlin": "BER",
    "frankfurt": "FRA",
    "cologne": "CGN",
    "dusseldorf": "DUS",
    # Austria
    "vienna": "VIE",
    # Turkey
    "istanbul": "SAW",
    "antalya": "AYT",
    # Greece
    "athenes": "ATH",
    "athens": "ATH",
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
    "luxor": "LXR",
    "alexandrie": "HBE",
    "alexandria": "HBE",
    # Middle East
    "dubai": "SHJ",
    "sharjah": "SHJ",
    "abu dhabi": "AUH",
    "amman": "AMM",
    "riyadh": "RUH",
    "jeddah": "JED",
    "muscat": "MCT",
    "kuwait city": "KWI",
    "bahrain": "BAH",
    # South Asia
    "islamabad": "ISB",
    "karachi": "KHI",
    "lahore": "LHE",
    "dhaka": "DAC",
    "kathmandu": "KTM",
    "colombo": "CMB",
    # East Africa
    "nairobi": "NBO",
    "addis ababa": "ADD",
    "dar es salaam": "DAR",
    "entebbe": "EBB",
}


def _resolve_airport(city: str) -> str:
    return resolve_airport(city, CITY_AIRPORT_MAP)


class AirArabiaScraper(ScraperBase):
    AIRLINE = "Air Arabia"

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
            await page.goto("https://www.airarabia.com/", wait_until="domcontentloaded", timeout=30000)
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
                                "availability", "search", "flight", "fare", "offer", "/api/"
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

                        await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                        await asyncio.sleep(random.uniform(3, 6))
                        await self._dismiss_cookies(page)

                        # Wait for results or error
                        try:
                            await page.wait_for_selector(
                                "[class*='flight'], [class*='result'], [class*='fare'], [class*='journey'], [class*='no-result'], [class*='error']",
                                timeout=15000,
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
                        logger.error(f"Air Arabia error for {dep}->{arr} on {current}: {e}")
                    current += timedelta(days=1)

                if not day_had_results:
                    results.append(make_route_not_served(self.AIRLINE, direction, date_from))

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
                        "outbound", "offers", "results", "outboundFlights"):
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

                segments = flight.get("segments", flight.get("legs", [flight]))
                if isinstance(segments, list) and len(segments) > 1:
                    continue

                seg = segments[0] if isinstance(segments, list) and segments else flight

                dep_time = parse_time(str(seg.get("departureTime", seg.get("std", ""))))
                arr_time = parse_time(str(seg.get("arrivalTime", seg.get("sta", ""))))

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

                price = 0.0
                for pk in ("price", "fare", "totalPrice", "lowestFare", "amount"):
                    pv = flight.get(pk, seg.get(pk))
                    if pv is not None:
                        if isinstance(pv, dict):
                            price = parse_price(pv.get("amount", pv.get("value", 0)))
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
            logger.error(f"Air Arabia parse error: {e}")
        return results

    async def _parse_dom(self, page, direction, dep, arr, flight_date) -> List[FlightResult]:
        results = []
        try:
            selectors = [
                "[class*='flight-result']",
                "[class*='flight-card']",
                "[class*='fare-card']",
                "[class*='journey-card']",
                "[data-testid*='flight']",
                "section[class*='flight']",
            ]
            cards = []
            for sel in selectors:
                cards = await page.query_selector_all(sel)
                if cards:
                    break

            if not cards:
                cards = await page.query_selector_all(
                    "[class*='flight'], [class*='result'], [class*='fare'], [class*='journey']"
                )

            for card in cards:
                try:
                    text = await card.inner_text()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    price = 0.0
                    dep_time = None
                    arr_time = None
                    for line in lines:
                        if any(c in line for c in ("€", "EUR", "eur", "MAD", "AED")):
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
            logger.error(f"Air Arabia DOM parse error: {e}")
        return results
