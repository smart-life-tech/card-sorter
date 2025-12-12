import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional

import requests

from .models import PriceQuote


@dataclass
class _CacheEntry:
    price_usd: Optional[float]
    source: str
    fetched_at: datetime
    expires_at: datetime


class PriceProvider:
    name: str

    def fetch_price(self, name: str, set_code: Optional[str] = None, collector_number: Optional[str] = None) -> PriceQuote:
        raise NotImplementedError


class ScryfallProvider(PriceProvider):
    name = "scryfall"

    def fetch_price(self, name: str, set_code: Optional[str] = None, collector_number: Optional[str] = None) -> PriceQuote:
        if collector_number and set_code:
            url = f"https://api.scryfall.com/cards/{set_code}/{collector_number}"
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
        else:
            url = "https://api.scryfall.com/cards/named"
            params = {"exact": name}
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()
        price = data.get("prices", {}).get("usd")
        price_val = float(price) if price else None
        return PriceQuote(price_usd=price_val, source=self.name, fetched_at=datetime.utcnow())


class TcgplayerProvider(PriceProvider):
    name = "tcgplayer"

    def __init__(self, public_key: Optional[str] = None, private_key: Optional[str] = None, session: Optional[requests.Session] = None) -> None:
        self.public_key = public_key or os.getenv("TCGPLAYER_PUBLIC_KEY")
        self.private_key = private_key or os.getenv("TCGPLAYER_PRIVATE_KEY")
        self.session = session or requests.Session()
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    def _ensure_token(self) -> Optional[str]:
        now = time.time()
        if self._token and now < self._token_expiry:
            return self._token
        if not self.public_key or not self.private_key:
            return None
        url = "https://api.tcgplayer.com/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.public_key,
            "client_secret": self.private_key,
        }
        resp = self.session.post(url, data=data, timeout=10)
        if resp.status_code != 200:
            return None
        payload = resp.json()
        self._token = payload.get("access_token")
        expires_in = payload.get("expires_in", 900)
        self._token_expiry = now + expires_in - 30
        return self._token

    def _request(self, method: str, url: str, headers: Dict[str, str], params=None) -> Optional[requests.Response]:
        retries = 3
        backoff = 0.5
        for attempt in range(retries):
            resp = self.session.request(method, url, headers=headers, params=params, timeout=10)
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(backoff)
                backoff *= 2
                continue
            return resp
        return None

    def _find_product_id(self, name: str, set_code: Optional[str], collector_number: Optional[str], token: str) -> Optional[int]:
        headers = {"Authorization": f"bearer {token}"}
        params = {
            "categoryId": 1,  # Magic: The Gathering
            "productName": name,
            "getExtendedFields": True,
        }
        resp = self._request("GET", "https://api.tcgplayer.com/catalog/products", headers=headers, params=params)
        if not resp or resp.status_code != 200:
            return None
        data = resp.json()
        products = data.get("results", [])
        if not products:
            return None
        if set_code:
            set_code_lower = set_code.lower()
            for prod in products:
                extended = prod.get("extendedData", [])
                for ext in extended:
                    if ext.get("name") == "Set Code" and ext.get("value", "").lower() == set_code_lower:
                        return prod.get("productId")
        return products[0].get("productId")

    def _fetch_price_for_product(self, product_id: int, token: str) -> Optional[float]:
        headers = {"Authorization": f"bearer {token}"}
        url = f"https://api.tcgplayer.com/pricing/product/{product_id}"
        resp = self._request("GET", url, headers=headers)
        if not resp or resp.status_code != 200:
            return None
        data = resp.json()
        prices = data.get("results", [])
        if not prices:
            return None
        market = prices[0].get("marketPrice")
        if market is None:
            return None
        try:
            return float(market)
        except (TypeError, ValueError):
            return None

    def fetch_price(self, name: str, set_code: Optional[str] = None, collector_number: Optional[str] = None) -> PriceQuote:
        token = self._ensure_token()
        if not token:
            return PriceQuote(price_usd=None, source=self.name, fetched_at=datetime.utcnow())
        product_id = self._find_product_id(name, set_code, collector_number, token)
        if not product_id:
            return PriceQuote(price_usd=None, source=self.name, fetched_at=datetime.utcnow())
        price = self._fetch_price_for_product(product_id, token)
        return PriceQuote(price_usd=price, source=self.name, fetched_at=datetime.utcnow())


class PriceService:
    def __init__(self, primary: PriceProvider, fallback: PriceProvider, cache_ttl_hours: int = 24) -> None:
        self.primary = primary
        self.fallback = fallback
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.cache: Dict[str, _CacheEntry] = {}

    def _cache_key(self, name: str, set_code: Optional[str], collector_number: Optional[str]) -> str:
        return "|".join([name.lower(), set_code or "", collector_number or ""])

    def get_price(self, name: str, set_code: Optional[str], collector_number: Optional[str]) -> PriceQuote:
        key = self._cache_key(name, set_code, collector_number)
        now = datetime.utcnow()
        if key in self.cache and self.cache[key].expires_at > now:
            entry = self.cache[key]
            return PriceQuote(price_usd=entry.price_usd, source=entry.source, fetched_at=entry.fetched_at)

        quote = self._try_provider(self.primary, name, set_code, collector_number)
        if quote.price_usd is None:
            fallback_quote = self._try_provider(self.fallback, name, set_code, collector_number)
            if fallback_quote.price_usd is not None:
                quote = fallback_quote
        self.cache[key] = _CacheEntry(
            price_usd=quote.price_usd,
            source=quote.source,
            fetched_at=quote.fetched_at,
            expires_at=now + self.cache_ttl,
        )
        return quote

    @staticmethod
    def _try_provider(provider: PriceProvider, name: str, set_code: Optional[str], collector_number: Optional[str]) -> PriceQuote:
        try:
            return provider.fetch_price(name, set_code, collector_number)
        except Exception:
            return PriceQuote(price_usd=None, source=provider.name, fetched_at=datetime.utcnow())

    def purge_expired(self) -> None:
        now = datetime.utcnow()
        expired = [k for k, v in self.cache.items() if v.expires_at <= now]
        for k in expired:
            self.cache.pop(k, None)


def build_price_service(primary_name: str, fallback_name: str, ttl_hours: int) -> PriceService:
    providers: Dict[str, PriceProvider] = {
        "scryfall": ScryfallProvider(),
        "tcgplayer": TcgplayerProvider(),
    }
    primary = providers.get(primary_name.lower()) or ScryfallProvider()
    fallback = providers.get(fallback_name.lower()) or ScryfallProvider()
    return PriceService(primary=primary, fallback=fallback, cache_ttl_hours=ttl_hours)
