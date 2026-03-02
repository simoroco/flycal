import asyncio
import random
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import List

logger = logging.getLogger("flycal.scraper")


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
