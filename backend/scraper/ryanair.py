import logging
from datetime import date, timedelta
from typing import List

import httpx

from .base import FlightResult, ScraperBase, make_route_not_served

logger = logging.getLogger("flycal.scraper.ryanair")

RYANAIR_API = "https://www.ryanair.com/api/farfnd/3/oneWayFares"

CITY_AIRPORT_MAP = {
    "paris": "BVA",
    "beauvais": "BVA",
    "marseille": "MRS",
    "lyon": "LYS",
    "toulouse": "TLS",
    "bordeaux": "BOD",
    "nantes": "NTE",
    "lille": "LIL",
    "nice": "NCE",
    "montpellier": "MPL",
    "porto": "OPO",
    "lisbonne": "LIS",
    "lisbon": "LIS",
    "madrid": "MAD",
    "barcelone": "BCN",
    "barcelona": "BCN",
    "rome": "CIA",
    "milan": "BGY",
    "london": "STN",
    "londres": "STN",
    "dublin": "DUB",
    "bruxelles": "CRL",
    "brussels": "CRL",
    "amsterdam": "EIN",
    "berlin": "BER",
    "marrakech": "RAK",
    "fes": "FEZ",
    "fez": "FEZ",
    "tanger": "TNG",
    "tangier": "TNG",
    "nador": "NDR",
    "oujda": "OUD",
    "agadir": "AGA",
    "rabat": "RBA",
    "casablanca": "CMN",
    "alger": "ALG",
    "algiers": "ALG",
    "oran": "ORN",
    "tunis": "TUN",
    "malaga": "AGP",
    "seville": "SVQ",
    "palma": "PMI",
    "ibiza": "IBZ",
    "athenes": "ATH",
    "athens": "ATH",
    "budapest": "BUD",
    "prague": "PRG",
    "cracovie": "KRK",
    "krakow": "KRK",
    "varsovie": "WMI",
    "warsaw": "WMI",
    "bucarest": "OTP",
    "bucharest": "OTP",
    "sofia": "SOF",
    "stockholm": "NYO",
    "oslo": "TRF",
    "copenhague": "CPH",
    "copenhagen": "CPH",
}


def _resolve_airport(city: str) -> str:
    normalized = city.strip().lower()
    return CITY_AIRPORT_MAP.get(normalized, normalized.upper()[:3])


class RyanairScraper(ScraperBase):
    AIRLINE = "Ryanair"

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
        origin = _resolve_airport(origin_city)
        destination = _resolve_airport(destination_city)
        results: List[FlightResult] = []

        directions = [("outbound", origin, destination)]
        if trip_type == "roundtrip":
            directions.append(("return", destination, origin))

        async with httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            },
        ) as client:
            for direction, dep, arr in directions:
                current = date_from
                while current <= date_to:
                    try:
                        params = {
                            "departureAirportIataCode": dep,
                            "arrivalAirportIataCode": arr,
                            "outboundDepartureDateFrom": current.isoformat(),
                            "outboundDepartureDateTo": current.isoformat(),
                            "currency": "EUR",
                        }
                        resp = await client.get(RYANAIR_API, params=params)
                        if resp.status_code == 200:
                            data = resp.json()
                            fares = data.get("fares", [])
                            for fare in fares:
                                outbound_info = fare.get("outbound", {})
                                dep_date_str = outbound_info.get("departureDate", "")
                                arr_date_str = outbound_info.get("arrivalDate", "")
                                price_info = outbound_info.get("price", {})
                                fare_price = price_info.get("value", 0)
                                fare_currency = price_info.get("currencyCode", "EUR")
                                dep_airport = outbound_info.get("departureAirport", {}).get("iataCode", dep)
                                arr_airport = outbound_info.get("arrivalAirport", {}).get("iataCode", arr)

                                dep_time = ""
                                arr_time = ""
                                if dep_date_str:
                                    dep_time = dep_date_str[11:16] if len(dep_date_str) > 16 else "00:00"
                                if arr_date_str:
                                    arr_time = arr_date_str[11:16] if len(arr_date_str) > 16 else "00:00"

                                if fare_price and fare_price > 0:
                                    results.append(
                                        FlightResult(
                                            airline="Ryanair",
                                            direction=direction,
                                            flight_date=current,
                                            departure_time=dep_time,
                                            arrival_time=arr_time,
                                            origin_airport=dep_airport,
                                            destination_airport=arr_airport,
                                            price=float(fare_price),
                                            currency=fare_currency if fare_currency else "EUR",
                                        )
                                    )
                        else:
                            logger.warning(
                                f"Ryanair API returned {resp.status_code} for {dep}->{arr} on {current}"
                            )
                    except Exception as e:
                        logger.error(f"Ryanair error for {dep}->{arr} on {current}: {e}")
                    current += timedelta(days=1)

                direction_results = [r for r in results if r.direction == direction]
                if not direction_results:
                    results.append(make_route_not_served(self.AIRLINE, direction, date_from))

        logger.info(f"Ryanair: found {len(results)} flights for {origin_city}->{destination_city}")
        return results
