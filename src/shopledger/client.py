"""ScrapeCreators API client. Standard library only.

Every response carries `credits_remaining`, so the client tracks the balance as a
side effect of normal work and the caller never has to spend a call to check it.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://api.scrapecreators.com"
USER_AGENT = "shop-ledger/0.1 (+https://github.com/hudsonhild/shop-ledger)"


class ApiError(RuntimeError):
    """A call failed in a way retrying will not fix."""


class OutOfCredits(ApiError):
    """The key has no credits left. Runs abort rather than write a partial day."""


class NotFound(ApiError):
    """The resource does not exist, or is not available in the US region."""


class Client:
    def __init__(self, api_key: str, *, timeout: int = 30, retries: int = 3) -> None:
        if not api_key:
            raise ApiError("An API key is required.")
        self._key = api_key
        self._timeout = timeout
        self._retries = retries
        self.credits: int | None = None
        self.calls = 0
        self.errors = 0

    # ------------------------------------------------------------ transport

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={"x-api-key": self._key, "User-Agent": USER_AGENT, "Accept": "application/json"},
        )

        last: Exception | None = None
        for attempt in range(self._retries):
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")
                if exc.code == 402:
                    raise OutOfCredits(f"Out of credits: {body[:200]}") from exc
                if exc.code in (400, 404):
                    # A bad or unavailable resource. Not retryable, not fatal.
                    try:
                        payload = json.loads(body)
                        break
                    except json.JSONDecodeError:
                        raise ApiError(f"HTTP {exc.code} on {path}: {body[:200]}") from exc
                if exc.code in (429, 500, 502, 503, 504) and attempt < self._retries - 1:
                    time.sleep(2**attempt)
                    last = exc
                    continue
                raise ApiError(f"HTTP {exc.code} on {path}: {body[:200]}") from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt < self._retries - 1:
                    time.sleep(2**attempt)
                    last = exc
                    continue
                raise ApiError(f"{type(exc).__name__} on {path}: {exc}") from exc
        else:  # pragma: no cover - loop always breaks or raises
            raise ApiError(f"Exhausted retries on {path}: {last}")

        self.calls += 1
        if isinstance(payload.get("credits_remaining"), int):
            self.credits = payload["credits_remaining"]

        if payload.get("error") == "not_found":
            raise NotFound(payload.get("message", "not found"))
        if payload.get("success") is False:
            self.errors += 1
            raise ApiError(payload.get("message", "request failed"))
        return payload

    # ------------------------------------------------------------ endpoints

    def shop_search(self, query: str) -> list[dict[str, Any]]:
        """Discovery. 1 credit, returns up to ~39 products with a lifetime sold_count."""
        payload = self._get("/v1/tiktok/shop/search", {"query": query})
        return payload.get("products") or []

    def product(self, product_id: str) -> dict[str, Any]:
        """Full detail: SKUs with stock and price, plus up to 18 related videos.

        US TikTok Shop only. Other regions raise NotFound and cost nothing.
        """
        url = f"https://www.tiktok.com/shop/pdp/{product_id}"
        return self._get("/v1/tiktok/product", {"url": url})

    def video(self, url: str) -> dict[str, Any]:
        """Used only for videos that have dropped out of a product's top 18.

        Takes the stored page URL, which already carries the author id.
        """
        return self._get("/v2/tiktok/video", {"url": url})

    def check_credits(self) -> int | None:
        """Cheapest possible balance probe: a deliberately invalid product lookup.

        The API returns the balance on the error envelope and charges nothing.
        """
        try:
            self._get("/v1/tiktok/product", {"url": "https://www.tiktok.com/shop/pdp/0"})
        except (NotFound, ApiError):
            pass
        return self.credits
