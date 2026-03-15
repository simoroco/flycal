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
