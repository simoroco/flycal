import asyncio
import json
import logging
import random
import re
from datetime import date, timedelta
from typing import List

from .base import FlightResult, ScraperBase, make_route_not_served, parse_time, parse_price

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
    AIRLINE = "Air France"

    async def _init_browser(self):
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.firefox.launch(
            headless=True,
        )
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

            # Load the booking page
            home_loaded = False
            for url in ["https://www.airfrance.fr/", "https://wwws.airfrance.fr/"]:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    home_loaded = True
                    break
                except Exception:
                    continue

            if not home_loaded:
                logger.error("Air France: could not load any homepage")
                for direction, _, _ in directions:
                    results.append(make_route_not_served(self.AIRLINE, direction, date_from))
                return results

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
                                "availability", "search", "offers", "lowest-fare",
                                "flight-search", "upsell", "result"
                            )):
                                try:
                                    ct = response.headers.get("content-type", "")
                                    if "json" in ct:
                                        body = await response.json()
                                        captured_responses.append(body)
                                except Exception:
                                    pass

                        page.on("response", handle_response)

                        # Try to fill the search form on the homepage
                        search_done = False
                        try:
                            search_done = await self._fill_search_form(page, dep, arr, current, trip_type)
                        except Exception as e:
                            logger.warning(f"Air France form fill failed: {e}")

                        if not search_done:
                            # Fallback: try direct search URL navigation
                            date_str = current.strftime("%Y-%m-%d")
                            for surl in [
                                f"https://www.airfrance.fr/search/offers?pax=1:0:0:0:0:0:0:0&cabinClass=ECONOMY&activeConnection=0&connections={dep}-A>{arr}-A-{date_str}",
                                f"https://wwws.airfrance.fr/search/offers?pax=1:0:0:0:0:0:0:0&cabinClass=ECONOMY&activeConnection=0&connections={dep}-A>{arr}-A-{date_str}",
                            ]:
                                try:
                                    await page.goto(surl, wait_until="domcontentloaded", timeout=30000)
                                    search_done = True
                                    break
                                except Exception:
                                    continue

                        if not search_done:
                            logger.warning(f"Air France: could not search for {dep}->{arr} on {current}")
                            current += timedelta(days=1)
                            page.remove_listener("response", handle_response)
                            continue

                        await asyncio.sleep(random.uniform(3, 6))
                        await self._dismiss_cookies(page)

                        # Wait for flight results or error indicators
                        try:
                            await page.wait_for_selector(
                                "[class*='flight'], [class*='result'], [class*='offer'], [class*='no-result'], [class*='error'], [data-testid*='flight'], [class*='bound']",
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
                        logger.error(f"Air France error for {dep}->{arr} on {current}: {e}")
                    current += timedelta(days=1)

                if not day_had_results:
                    results.append(make_route_not_served(self.AIRLINE, direction, date_from))

        except Exception as e:
            logger.error(f"Air France browser error: {e}")
        finally:
            await self._close_browser()

        logger.info(f"Air France: found {len(results)} flights for {origin_city}->{destination_city}")
        return results

    async def _fill_search_form(self, page, dep, arr, flight_date, trip_type) -> bool:
        """Try to fill in the Air France search form and submit it."""
        try:
            # Look for the search form on the homepage
            # Air France uses various form selectors
            origin_selectors = [
                "input[name*='origin']",
                "input[placeholder*='Départ']",
                "input[placeholder*='depart']",
                "input[aria-label*='Départ']",
                "input[data-testid*='origin']",
                "#search-origin",
            ]
            dest_selectors = [
                "input[name*='destination']",
                "input[placeholder*='Destination']",
                "input[placeholder*='destination']",
                "input[aria-label*='Destination']",
                "input[data-testid*='destination']",
                "#search-destination",
            ]

            # Fill origin
            origin_filled = False
            for sel in origin_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        await el.click()
                        await el.fill(dep)
                        await asyncio.sleep(0.5)
                        # Select from autocomplete dropdown
                        try:
                            await page.keyboard.press("Enter")
                        except Exception:
                            pass
                        await asyncio.sleep(0.5)
                        origin_filled = True
                        break
                except Exception:
                    continue

            if not origin_filled:
                return False

            # Fill destination
            dest_filled = False
            for sel in dest_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        await el.click()
                        await el.fill(arr)
                        await asyncio.sleep(0.5)
                        try:
                            await page.keyboard.press("Enter")
                        except Exception:
                            pass
                        await asyncio.sleep(0.5)
                        dest_filled = True
                        break
                except Exception:
                    continue

            if not dest_filled:
                return False

            # Set one-way if needed
            if trip_type == "oneway":
                oneway_selectors = [
                    "button:has-text('Aller simple')",
                    "label:has-text('Aller simple')",
                    "[data-testid*='one-way']",
                    "input[value='ONE_WAY']",
                ]
                for sel in oneway_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=1000):
                            await el.click()
                            await asyncio.sleep(0.3)
                            break
                    except Exception:
                        continue

            # Click search button
            search_selectors = [
                "button[type='submit']",
                "button:has-text('Rechercher')",
                "button:has-text('Recherche')",
                "button[data-testid*='search']",
                "button[class*='search']",
            ]
            for sel in search_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        await el.click()
                        await asyncio.sleep(2)
                        return True
                except Exception:
                    continue

            return False
        except Exception as e:
            logger.warning(f"Air France form fill error: {e}")
            return False

    def _parse_response(self, data, direction, dep, arr, flight_date) -> List[FlightResult]:
        results = []
        try:
            if not isinstance(data, dict):
                return results

            itineraries = []
            for key in ("itineraries", "connections", "boundOffers", "flightProducts",
                        "recommendations", "flights", "offers", "results",
                        "outboundFlights", "journeys"):
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
                        if itineraries:
                            break

            for itin in itineraries:
                if not isinstance(itin, dict):
                    continue

                segments = itin.get("segments", itin.get("flights", itin.get("legs", [itin])))
                if isinstance(segments, list) and len(segments) > 1:
                    continue  # skip connecting flights

                seg = segments[0] if isinstance(segments, list) and segments else itin

                raw_dep = seg.get("departureTime", seg.get("departureDateTime",
                          seg.get("departure", {}).get("time", "") if isinstance(seg.get("departure"), dict) else ""))
                raw_arr = seg.get("arrivalTime", seg.get("arrivalDateTime",
                          seg.get("arrival", {}).get("time", "") if isinstance(seg.get("arrival"), dict) else ""))
                dep_time = parse_time(str(raw_dep))
                arr_time = parse_time(str(raw_arr))

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

                price = 0.0
                for pk in ("price", "totalPrice", "lowestPrice", "fare", "amount"):
                    pv = itin.get(pk, seg.get(pk))
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
            logger.error(f"Air France parse error: {e}")
        return results

    async def _parse_dom(self, page, direction, dep, arr, flight_date) -> List[FlightResult]:
        results = []
        try:
            selectors = [
                "[class*='flight-result']",
                "[class*='flight-card']",
                "[class*='offer-card']",
                "[data-testid*='flight']",
                "[data-testid*='offer']",
                "[class*='bound-proposal']",
                "section[class*='flight']",
            ]
            cards = []
            for sel in selectors:
                cards = await page.query_selector_all(sel)
                if cards:
                    break

            if not cards:
                cards = await page.query_selector_all("[class*='flight'], [class*='result'], [class*='offer']")

            for card in cards:
                try:
                    text = await card.inner_text()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    price = 0.0
                    dep_time = None
                    arr_time = None
                    for line in lines:
                        if "€" in line or "EUR" in line:
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
            logger.error(f"Air France DOM parse error: {e}")
        return results
