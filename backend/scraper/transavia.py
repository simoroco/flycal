"""
Transavia scraper using curl_cffi to bypass Cloudflare.
Attempts direct scraping from transavia.com, returns empty results quickly
if flight data can't be extracted (triggers Google Flights fallback).
"""
import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import List

from .base import FlightResult, make_route_not_served, parse_time, parse_price

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


def _scrape_transavia_sync(dep: str, arr: str, flight_date: str) -> list:
    """Synchronous scraping via curl_cffi (runs in thread pool)."""
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        logger.warning("curl_cffi not installed, skipping Transavia direct scraping")
        return []

    results = []
    try:
        session = cffi_requests.Session(impersonate="chrome")

        # Load search page (bypasses Cloudflare via TLS fingerprinting)
        search_url = (
            f"https://www.transavia.com/fr-FR/book-a-flight/flights/search/"
            f"?routeSelection={dep}-{arr}"
            f"&dateSelection={flight_date}"
            f"&flexibleSearch=false"
            f"&selectPassengers=1"
        )
        r = session.get(search_url, timeout=12)
        if r.status_code != 200:
            logger.warning(f"Transavia: got {r.status_code} for {dep}->{arr} on {flight_date}")
            return []

        html = r.text

        # Extract CSRF token and form action
        token_match = re.search(
            r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html
        )
        csrf = token_match.group(1) if token_match else ""

        form_match = re.search(r'<form[^>]*action="([^"]*)"[^>]*>', html)
        form_action = form_match.group(1) if form_match else "/fr-FR/reservez-un-vol/vols/rechercher/"

        # POST to form action with XHR header (ASP.NET returns partial HTML)
        form_data = {
            "__RequestVerificationToken": csrf,
            "routeSelection": f"{dep}-{arr}",
            "dateSelection": flight_date,
            "flexibleSearch": "false",
            "selectPassengers": "1",
        }
        r2 = session.post(
            f"https://www.transavia.com{form_action}",
            data=form_data,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/html, */*",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=12,
        )

        if r2.status_code == 200:
            ct = r2.headers.get("content-type", "")
            if "json" in ct:
                try:
                    data = r2.json()
                    results = _parse_json_response(data, dep, arr, flight_date)
                except Exception:
                    pass
            else:
                results = _parse_html_response(r2.text, dep, arr, flight_date)

        session.close()
    except Exception as e:
        logger.warning(f"Transavia curl_cffi error for {dep}->{arr} on {flight_date}: {e}")

    return results


def _parse_json_response(data: dict, dep: str, arr: str, flight_date: str) -> list:
    """Parse JSON response from Transavia API."""
    results = []
    if not isinstance(data, dict):
        return results

    journeys = []
    for key in ("outboundFlights", "flights", "journeys", "flightOffer",
                "flightProducts", "availableFlights", "results"):
        if key in data:
            val = data[key]
            if isinstance(val, list):
                journeys = val
                break

    for flight in journeys:
        if not isinstance(flight, dict):
            continue
        segments = flight.get("segments", flight.get("flightSegments", flight.get("legs", [flight])))
        if isinstance(segments, list) and len(segments) > 1:
            continue

        seg = segments[0] if isinstance(segments, list) and segments else flight
        dep_time = parse_time(str(seg.get("departureTime", seg.get("departureDateTime", ""))))
        arr_time = parse_time(str(seg.get("arrivalTime", seg.get("arrivalDateTime", ""))))

        price = 0.0
        for pk in ("price", "priceFrom", "fare", "totalPrice"):
            if pk in flight:
                pval = flight[pk]
                price = parse_price(pval) if not isinstance(pval, dict) else parse_price(pval.get("amount", 0))
                break

        if price > 0 and dep_time and arr_time:
            results.append({
                "departure_time": dep_time,
                "arrival_time": arr_time,
                "origin": dep,
                "destination": arr,
                "price": price,
            })
    return results


def _parse_html_response(html: str, dep: str, arr: str, flight_date: str) -> list:
    """Parse HTML response for embedded flight data."""
    results = []
    # Look for flight product cards with prices and times
    cards = re.findall(
        r'class="[^"]*flight-product[^"]*"[^>]*>(.*?)</(?:div|section|article)',
        html, re.DOTALL | re.IGNORECASE
    )
    for card in cards:
        times = re.findall(r'(\d{2}:\d{2})', card)
        prices = re.findall(r'(\d+)[,.](\d{2})', card)
        if len(times) >= 2 and prices:
            price = float(f"{prices[0][0]}.{prices[0][1]}")
            if price > 10:
                results.append({
                    "departure_time": times[0],
                    "arrival_time": times[1],
                    "origin": dep,
                    "destination": arr,
                    "price": price,
                })
    return results


class TransaviaScraper:
    """
    Transavia scraper - Direct scraping disabled.
    
    Transavia.com is a Next.js/React SPA that loads all flight data via client-side
    JavaScript. Direct HTTP scraping fails because:
    - HTTP 429 rate limiting (Cloudflare blocks after ~10 requests)
    - No accessible REST API endpoints
    - Flight data requires JavaScript execution
    
    This scraper immediately returns route_not_served to trigger Google Flights
    fallback (phase 2), which successfully finds Transavia flights.
    """
    AIRLINE = "Transavia"

    async def search(
        self,
        origin_city: str,
        destination_city: str,
        date_from: date,
        date_to: date,
        trip_type: str,
    ) -> List[FlightResult]:
        """Return route_not_served immediately to trigger Google Flights fallback."""
        logger.info(f"Transavia: skipping direct scraping (using Google Flights fallback)")
        
        results = [
            make_route_not_served(self.AIRLINE, "outbound", date_from)
        ]
        
        if trip_type == "roundtrip":
            results.append(make_route_not_served(self.AIRLINE, "return", date_from))
        
        return results
