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

from .base import FlightResult, make_route_not_served, parse_time, resolve_airport

logger = logging.getLogger("flycal.scraper.amadeus")

# Map airline display names to IATA carrier codes
AIRLINE_IATA_CODES = {
    "Transavia": ["TO", "HV"],
    "Air France": ["AF"],
    "Air Arabia": ["G9", "3L", "E5"],
    "Royal Air Maroc": ["AT"],
    "Ryanair": ["FR"],
    "American Airlines": ["AA"],
    "Emirates": ["EK"],
    "Qatar Airways": ["QR"],
    "Lufthansa": ["LH"],
    "Singapore Airlines": ["SQ"],
    "British Airways": ["BA"],
    "Air China": ["CA"],
    "Turkish Airlines": ["TK"],
    "EasyJet": ["U2"],
    "Vueling": ["VY"],
    "Finnair": ["AY"],
    "Air Caraibes": ["TX"],
    "TAP Air Portugal": ["TP"],
    "Iberia": ["IB"],
    "Corsair": ["SS"],
    "ITA Airways": ["AZ"],
}

CITY_AIRPORT_MAP = {
    # France
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
    "strasbourg": "SXB",
    # French Overseas (DOM-TOM)
    "pointe-a-pitre": "PTP",
    "pointe a pitre": "PTP",
    "fort-de-france": "FDF",
    "fort de france": "FDF",
    "cayenne": "CAY",
    "saint-denis reunion": "RUN",
    "saint denis reunion": "RUN",
    "la reunion": "RUN",
    "reunion": "RUN",
    # Portugal
    "porto": "OPO",
    "lisbonne": "LIS",
    "lisbon": "LIS",
    "faro": "FAO",
    "funchal": "FNC",
    "madere": "FNC",
    # Spain
    "madrid": "MAD",
    "barcelone": "BCN",
    "barcelona": "BCN",
    "malaga": "AGP",
    "seville": "SVQ",
    "valencia": "VLC",
    "valence": "VLC",
    "palma": "PMI",
    "palma de mallorca": "PMI",
    "majorque": "PMI",
    "ibiza": "IBZ",
    "tenerife": "TFS",
    "gran canaria": "LPA",
    "bilbao": "BIO",
    "alicante": "ALC",
    # Italy
    "rome": "FCO",
    "milan": "MXP",
    "venice": "VCE",
    "venise": "VCE",
    "naples": "NAP",
    "florence": "FLR",
    "bologna": "BLQ",
    "turin": "TRN",
    "catania": "CTA",
    "palermo": "PMO",
    "bari": "BRI",
    # United Kingdom
    "london": "LON",
    "londres": "LON",
    "edinburgh": "EDI",
    "edimbourg": "EDI",
    "manchester": "MAN",
    "birmingham": "BHX",
    "glasgow": "GLA",
    "bristol": "BRS",
    "liverpool": "LPL",
    "newcastle": "NCL",
    # Ireland
    "dublin": "DUB",
    # Netherlands
    "amsterdam": "AMS",
    # Belgium
    "bruxelles": "BRU",
    "brussels": "BRU",
    # Germany
    "berlin": "BER",
    "frankfurt": "FRA",
    "francfort": "FRA",
    "dusseldorf": "DUS",
    "munich": "MUC",
    "hamburg": "HAM",
    "hambourg": "HAM",
    "cologne": "CGN",
    "stuttgart": "STR",
    "hanover": "HAJ",
    "hanovre": "HAJ",
    "nuremberg": "NUE",
    # Austria
    "vienna": "VIE",
    "vienne": "VIE",
    "salzburg": "SZG",
    "innsbruck": "INN",
    # Switzerland
    "zurich": "ZRH",
    "geneva": "GVA",
    "geneve": "GVA",
    "basel": "BSL",
    "bale": "BSL",
    # Scandinavia
    "copenhagen": "CPH",
    "copenhague": "CPH",
    "stockholm": "ARN",
    "oslo": "OSL",
    "helsinki": "HEL",
    "gothenburg": "GOT",
    "bergen": "BGO",
    "tampere": "TMP",
    "turku": "TKU",
    "rovaniemi": "RVN",
    # Eastern Europe
    "warsaw": "WAW",
    "varsovie": "WAW",
    "prague": "PRG",
    "budapest": "BUD",
    "bucharest": "OTP",
    "bucarest": "OTP",
    "sofia": "SOF",
    "krakow": "KRK",
    "cracovie": "KRK",
    "zagreb": "ZAG",
    "belgrade": "BEG",
    "bratislava": "BTS",
    "ljubljana": "LJU",
    # Baltic States
    "tallinn": "TLL",
    "riga": "RIX",
    "vilnius": "VNO",
    # Greece
    "athenes": "ATH",
    "athens": "ATH",
    "thessaloniki": "SKG",
    "santorini": "JTR",
    "mykonos": "JMK",
    "heraklion": "HER",
    "rhodes": "RHO",
    "corfu": "CFU",
    # Turkey
    "istanbul": "IST",
    "ankara": "ESB",
    "antalya": "AYT",
    "izmir": "ADB",
    "bodrum": "BJV",
    # Cyprus
    "larnaca": "LCA",
    "paphos": "PFO",
    # Malta
    "malta": "MLA",
    "malte": "MLA",
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
    "le caire": "CAI",
    "cairo": "CAI",
    "hurghada": "HRG",
    "sharm el sheikh": "SSH",
    "luxor": "LXR",
    "alexandria": "HBE",
    "alexandrie": "HBE",
    # Middle East
    "dubai": "DXB",
    "abu dhabi": "AUH",
    "doha": "DOH",
    "riyadh": "RUH",
    "jeddah": "JED",
    "muscat": "MCT",
    "kuwait city": "KWI",
    "bahrain": "BAH",
    "amman": "AMM",
    "beirut": "BEY",
    "beyrouth": "BEY",
    "tel aviv": "TLV",
    "medina": "MED",
    # North America
    "new york": "JFK",
    "los angeles": "LAX",
    "chicago": "ORD",
    "miami": "MIA",
    "dallas": "DFW",
    "san francisco": "SFO",
    "washington": "IAD",
    "boston": "BOS",
    "houston": "IAH",
    "seattle": "SEA",
    "atlanta": "ATL",
    "denver": "DEN",
    "philadelphia": "PHL",
    "phoenix": "PHX",
    "orlando": "MCO",
    "charlotte": "CLT",
    "las vegas": "LAS",
    "toronto": "YYZ",
    "montreal": "YUL",
    "vancouver": "YVR",
    "mexico city": "MEX",
    "cancun": "CUN",
    # South America
    "sao paulo": "GRU",
    "buenos aires": "EZE",
    "lima": "LIM",
    "bogota": "BOG",
    "santiago": "SCL",
    "rio de janeiro": "GIG",
    # East Asia
    "tokyo": "NRT",
    "beijing": "PEK",
    "pekin": "PEK",
    "shanghai": "PVG",
    "hong kong": "HKG",
    "seoul": "ICN",
    "taipei": "TPE",
    "osaka": "KIX",
    "guangzhou": "CAN",
    "chengdu": "CTU",
    "shenzhen": "SZX",
    # Southeast Asia
    "singapore": "SIN",
    "singapour": "SIN",
    "bangkok": "BKK",
    "kuala lumpur": "KUL",
    "jakarta": "CGK",
    "manila": "MNL",
    "ho chi minh city": "SGN",
    "hanoi": "HAN",
    "bali": "DPS",
    # South Asia
    "mumbai": "BOM",
    "bombay": "BOM",
    "delhi": "DEL",
    "new delhi": "DEL",
    "bangalore": "BLR",
    "hyderabad": "HYD",
    "chennai": "MAA",
    "kolkata": "CCU",
    "colombo": "CMB",
    "islamabad": "ISB",
    "karachi": "KHI",
    "lahore": "LHE",
    "dhaka": "DAC",
    "kathmandu": "KTM",
    "male": "MLE",
    # Central Asia
    "almaty": "ALA",
    "tashkent": "TAS",
    "baku": "GYD",
    "tbilisi": "TBS",
    # West Africa
    "dakar": "DSS",
    "abidjan": "ABJ",
    "lagos": "LOS",
    "accra": "ACC",
    # East Africa
    "nairobi": "NBO",
    "addis ababa": "ADD",
    "dar es salaam": "DAR",
    "entebbe": "EBB",
    "kigali": "KGL",
    "zanzibar": "ZNZ",
    # Southern Africa
    "johannesburg": "JNB",
    "cape town": "CPT",
    "le cap": "CPT",
    "durban": "DUR",
    # North Africa
    "tripoli": "TIP",
    # Indian Ocean
    "mauritius": "MRU",
    "maurice": "MRU",
    # Oceania
    "sydney": "SYD",
    "melbourne": "MEL",
    "perth": "PER",
    "brisbane": "BNE",
    "auckland": "AKL",
    "christchurch": "CHC",
    # Caribbean
    "havana": "HAV",
    "punta cana": "PUJ",
    "santo domingo": "SDQ",
}


def _resolve_airport(city: str) -> str:
    return resolve_airport(city, CITY_AIRPORT_MAP)


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
