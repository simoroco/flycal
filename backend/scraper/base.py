import asyncio
import re
import random
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import List

logger = logging.getLogger("flycal.scraper")

COOKIE_ACCEPT_SELECTORS = [
    "button[id*='accept']",
    "button[id*='cookie']",
    "button[class*='accept']",
    "button[class*='consent']",
    "button[data-testid*='accept']",
    "button[data-testid*='cookie']",
    "#onetrust-accept-btn-handler",
    ".onetrust-accept-btn-handler",
    "#didomi-notice-agree-button",
    ".didomi-accept",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "button:has-text('Accepter')",
    "button:has-text('Tout accepter')",
    "button:has-text('Accept all')",
    "button:has-text('Accept')",
    "button:has-text('J\\'accepte')",
    "button:has-text('OK')",
    "a:has-text('Accepter')",
    "a:has-text('Tout accepter')",
]


# Global city-to-airport fallback map (used when a scraper's own map doesn't have the city)
GLOBAL_CITY_AIRPORT_MAP = {
    # France
    "paris": "PAR", "orly": "ORY", "cdg": "CDG", "beauvais": "BVA",
    "marseille": "MRS", "lyon": "LYS", "toulouse": "TLS", "nantes": "NTE",
    "montpellier": "MPL", "bordeaux": "BOD", "lille": "LIL", "nice": "NCE",
    "strasbourg": "SXB",
    # French Overseas
    "pointe-a-pitre": "PTP", "pointe a pitre": "PTP",
    "fort-de-france": "FDF", "fort de france": "FDF",
    "cayenne": "CAY", "saint-denis reunion": "RUN", "saint denis reunion": "RUN",
    "la reunion": "RUN", "reunion": "RUN",
    # Portugal
    "porto": "OPO", "lisbonne": "LIS", "lisbon": "LIS", "faro": "FAO",
    "funchal": "FNC", "madere": "FNC",
    # Spain
    "madrid": "MAD", "barcelone": "BCN", "barcelona": "BCN", "malaga": "AGP",
    "seville": "SVQ", "valencia": "VLC", "valence": "VLC", "palma": "PMI",
    "palma de mallorca": "PMI", "majorque": "PMI", "ibiza": "IBZ",
    "tenerife": "TFS", "gran canaria": "LPA", "bilbao": "BIO", "alicante": "ALC",
    # Italy
    "rome": "FCO", "milan": "MXP", "venice": "VCE", "venise": "VCE",
    "naples": "NAP", "florence": "FLR", "bologna": "BLQ", "turin": "TRN",
    "catania": "CTA", "palermo": "PMO", "bari": "BRI",
    # UK
    "london": "LHR", "londres": "LHR", "edinburgh": "EDI", "manchester": "MAN",
    "birmingham": "BHX", "glasgow": "GLA", "bristol": "BRS", "liverpool": "LPL",
    "newcastle": "NCL",
    # Ireland
    "dublin": "DUB",
    # Benelux
    "amsterdam": "AMS", "bruxelles": "BRU", "brussels": "BRU",
    # Germany
    "berlin": "BER", "frankfurt": "FRA", "francfort": "FRA", "dusseldorf": "DUS",
    "munich": "MUC", "hamburg": "HAM", "cologne": "CGN", "stuttgart": "STR",
    "hanover": "HAJ", "nuremberg": "NUE",
    # Austria / Switzerland
    "vienna": "VIE", "vienne": "VIE", "salzburg": "SZG", "innsbruck": "INN",
    "zurich": "ZRH", "geneva": "GVA", "geneve": "GVA", "basel": "BSL",
    # Scandinavia
    "copenhagen": "CPH", "copenhague": "CPH", "stockholm": "ARN", "oslo": "OSL",
    "helsinki": "HEL", "gothenburg": "GOT", "bergen": "BGO",
    "tampere": "TMP", "turku": "TKU", "rovaniemi": "RVN",
    # Eastern Europe
    "warsaw": "WAW", "varsovie": "WAW", "prague": "PRG", "budapest": "BUD",
    "bucharest": "OTP", "bucarest": "OTP", "sofia": "SOF", "krakow": "KRK",
    "cracovie": "KRK", "zagreb": "ZAG", "belgrade": "BEG",
    "bratislava": "BTS", "ljubljana": "LJU",
    # Baltic
    "tallinn": "TLL", "riga": "RIX", "vilnius": "VNO",
    # Greece
    "athenes": "ATH", "athens": "ATH", "thessaloniki": "SKG",
    "santorini": "JTR", "mykonos": "JMK", "heraklion": "HER",
    "rhodes": "RHO", "corfu": "CFU",
    # Turkey
    "istanbul": "IST", "ankara": "ESB", "antalya": "AYT", "izmir": "ADB",
    "bodrum": "BJV",
    # Cyprus / Malta
    "larnaca": "LCA", "paphos": "PFO", "malta": "MLA",
    # Morocco
    "marrakech": "RAK", "fes": "FEZ", "fez": "FEZ", "tanger": "TNG",
    "tangier": "TNG", "nador": "NDR", "oujda": "OUD", "agadir": "AGA",
    "casablanca": "CMN", "rabat": "RBA", "essaouira": "ESU",
    # Algeria / Tunisia
    "alger": "ALG", "algiers": "ALG", "oran": "ORN", "tunis": "TUN",
    # Egypt
    "le caire": "CAI", "cairo": "CAI", "hurghada": "HRG",
    "sharm el sheikh": "SSH", "luxor": "LXR", "alexandria": "HBE",
    # Middle East
    "dubai": "DXB", "abu dhabi": "AUH", "doha": "DOH",
    "riyadh": "RUH", "jeddah": "JED", "muscat": "MCT",
    "kuwait city": "KWI", "bahrain": "BAH", "amman": "AMM",
    "beirut": "BEY", "tel aviv": "TLV", "medina": "MED",
    # North America
    "new york": "JFK", "los angeles": "LAX", "chicago": "ORD", "miami": "MIA",
    "dallas": "DFW", "san francisco": "SFO", "washington": "IAD", "boston": "BOS",
    "houston": "IAH", "seattle": "SEA", "atlanta": "ATL", "denver": "DEN",
    "philadelphia": "PHL", "phoenix": "PHX", "orlando": "MCO",
    "charlotte": "CLT", "las vegas": "LAS",
    "toronto": "YYZ", "montreal": "YUL", "vancouver": "YVR",
    "mexico city": "MEX", "cancun": "CUN",
    # South America
    "sao paulo": "GRU", "buenos aires": "EZE", "lima": "LIM",
    "bogota": "BOG", "santiago": "SCL", "rio de janeiro": "GIG",
    # East Asia
    "tokyo": "NRT", "beijing": "PEK", "pekin": "PEK", "shanghai": "PVG",
    "hong kong": "HKG", "seoul": "ICN", "taipei": "TPE", "osaka": "KIX",
    "guangzhou": "CAN", "chengdu": "CTU", "shenzhen": "SZX",
    # Southeast Asia
    "singapore": "SIN", "singapour": "SIN", "bangkok": "BKK",
    "kuala lumpur": "KUL", "jakarta": "CGK", "manila": "MNL",
    "ho chi minh city": "SGN", "hanoi": "HAN", "bali": "DPS",
    # South Asia
    "mumbai": "BOM", "bombay": "BOM", "delhi": "DEL", "new delhi": "DEL",
    "bangalore": "BLR", "hyderabad": "HYD", "chennai": "MAA",
    "kolkata": "CCU", "colombo": "CMB", "islamabad": "ISB",
    "karachi": "KHI", "lahore": "LHE", "dhaka": "DAC",
    "kathmandu": "KTM", "male": "MLE",
    # Central Asia
    "almaty": "ALA", "tashkent": "TAS", "baku": "GYD", "tbilisi": "TBS",
    # Africa
    "dakar": "DSS", "abidjan": "ABJ", "lagos": "LOS", "accra": "ACC",
    "nairobi": "NBO", "addis ababa": "ADD", "dar es salaam": "DAR",
    "entebbe": "EBB", "kigali": "KGL", "zanzibar": "ZNZ",
    "johannesburg": "JNB", "cape town": "CPT", "durban": "DUR",
    "mauritius": "MRU",
    # Oceania
    "sydney": "SYD", "melbourne": "MEL", "perth": "PER",
    "brisbane": "BNE", "auckland": "AKL",
    # Caribbean
    "havana": "HAV", "punta cana": "PUJ", "santo domingo": "SDQ",
}


def resolve_airport(city: str, local_map: dict = None) -> str:
    """Resolve city name to IATA airport code.
    Checks local_map first (airline-specific), then falls back to global map.
    """
    normalized = city.strip().lower()
    if local_map:
        code = local_map.get(normalized)
        if code:
            return code
    return GLOBAL_CITY_AIRPORT_MAP.get(normalized, normalized.upper()[:3])


@dataclass
class FlightResult:
    airline: str
    direction: str  # outbound or return
    flight_date: date
    departure_time: str  # HH:MM
    arrival_time: str  # HH:MM
    origin_airport: str  # IATA code
    destination_airport: str  # IATA code
    price: float
    currency: str = "EUR"
    route_not_served: bool = False


def make_route_not_served(airline: str, direction: str, flight_date: date) -> FlightResult:
    return FlightResult(
        airline=airline,
        direction=direction,
        flight_date=flight_date,
        departure_time="",
        arrival_time="",
        origin_airport="",
        destination_airport="",
        price=0.0,
        currency="EUR",
        route_not_served=True,
    )


def parse_time(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    if "T" in raw:
        raw = raw.split("T")[1][:5]
    m = re.search(r"(\d{1,2})[:\.](\d{2})", raw)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return raw[:5] if len(raw) >= 5 else raw


def parse_price(raw) -> float:
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        cleaned = raw.replace("\xa0", "").replace(" ", "").replace(",", ".").replace("€", "").replace("EUR", "")
        m = re.search(r"(\d+\.?\d*)", cleaned)
        if m:
            return float(m.group(1))
    return 0.0


class ScraperBase(ABC):
    MAX_RETRIES = 3
    RETRY_DELAY_MIN = 2
    RETRY_DELAY_MAX = 5

    def __init__(self):
        self.browser = None
        self.context = None

    async def _init_browser(self):
        from playwright.async_api import async_playwright
        from playwright_stealth import stealth_async

        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-http2",
            ],
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="fr-FR",
        )
        page = await self.context.new_page()
        await stealth_async(page)
        return page

    async def _close_browser(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.stop()
        self.browser = None
        self.context = None

    async def _dismiss_cookies(self, page):
        for selector in COOKIE_ACCEPT_SELECTORS:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=600):
                    await btn.click(timeout=2000)
                    await asyncio.sleep(0.5)
                    logger.info(f"[{self.__class__.__name__}] Cookie banner dismissed via {selector}")
                    return True
            except Exception:
                continue
        return False

    async def _handle_captcha(self, page):
        await asyncio.sleep(random.uniform(self.RETRY_DELAY_MIN, self.RETRY_DELAY_MAX))

    async def _retry(self, coro_func, *args, **kwargs):
        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return await coro_func(*args, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(f"[{self.__class__.__name__}] Attempt {attempt}/{self.MAX_RETRIES} failed: {e}")
                await asyncio.sleep(random.uniform(self.RETRY_DELAY_MIN, self.RETRY_DELAY_MAX))
        logger.error(f"[{self.__class__.__name__}] All {self.MAX_RETRIES} retries exhausted: {last_error}")
        return []

    @abstractmethod
    async def search(
        self,
        origin_city: str,
        destination_city: str,
        date_from: date,
        date_to: date,
        trip_type: str,
    ) -> List[FlightResult]:
        pass
