from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx
from lxml import etree, html


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    description: str


class DuckDuckGoSearchError(RuntimeError):
    """Raised when a DuckDuckGo text search fails."""


class DuckDuckGoSearchClient:
    SEARCH_URL = "https://html.duckduckgo.com/html/"
    USER_AGENT = "Mozilla/5.0"
    VALID_SAFE_SEARCH = frozenset({"on", "moderate", "off"})
    VALID_TIME_LIMITS = frozenset({"d", "w", "m", "y"})
    SAFE_SEARCH_PARAMS = {
        "on": "1",
        "moderate": "-1",
        "off": "-2",
    }

    def __init__(
        self,
        *,
        region: str = "us-en",
        safe_search: str = "moderate",
        timeout: int = 10,
    ) -> None:
        if not region.strip():
            raise ValueError("region cannot be empty")
        if safe_search not in self.VALID_SAFE_SEARCH:
            raise ValueError(
                "safe_search must be one of: on, moderate, off"
            )
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        self.region = region
        self.safe_search = safe_search
        self.timeout = timeout
        self._client = httpx.Client(
            headers={"User-Agent": self.USER_AGENT},
            follow_redirects=True,
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DuckDuckGoSearchClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def text(
        self,
        query: str,
        *,
        max_results: int = 10,
        page: int = 1,
        time_limit: str | None = None,
    ) -> list[SearchResult]:
        query = query.strip()
        if not query:
            raise ValueError("query cannot be empty")
        if max_results <= 0:
            raise ValueError("max_results must be greater than zero")
        if page <= 0:
            raise ValueError("page must be greater than zero")
        if (
            time_limit is not None
            and time_limit not in self.VALID_TIME_LIMITS
        ):
            raise ValueError("time_limit must be one of: d, w, m, y")

        try:
            response = self._client.get(
                self.SEARCH_URL,
                params=self._build_params(query, page, time_limit),
            )
            if response.status_code != 200:
                raise DuckDuckGoSearchError(
                    "DuckDuckGo rejected the search request "
                    f"with HTTP {response.status_code}"
                )

            return self._parse_results(response.text)[:max_results]
        except DuckDuckGoSearchError:
            raise
        except (httpx.HTTPError, etree.ParserError) as error:
            raise DuckDuckGoSearchError(
                f"DuckDuckGo search failed for query: {query}"
            ) from error

    def _build_params(
        self,
        query: str,
        page: int,
        time_limit: str | None,
    ) -> dict[str, str]:
        params = {
            "q": query,
            "kl": self.region,
            "kp": self.SAFE_SEARCH_PARAMS[self.safe_search],
        }
        if page > 1:
            params["s"] = str(10 + (page - 2) * 15)
        if time_limit is not None:
            params["df"] = time_limit
        return params

    @staticmethod
    def _parse_results(document: str) -> list[SearchResult]:
        tree = html.fromstring(document)
        anchors = tree.xpath(
            '//a[contains(concat(" ", normalize-space(@class), " "), '
            '" result__a ")]'
        )
        results = []

        for anchor in anchors:
            title = " ".join(anchor.text_content().split())
            url = DuckDuckGoSearchClient._decode_result_url(
                anchor.get("href", "")
            )
            containers = anchor.xpath(
                'ancestor::div[contains('
                'concat(" ", normalize-space(@class), " "), " result "'
                ")][1]"
            )
            description = ""
            if containers:
                snippets = containers[0].xpath(
                    './/*[contains('
                    'concat(" ", normalize-space(@class), " "), '
                    '" result__snippet ")]'
                )
                if snippets:
                    description = " ".join(
                        snippets[0].text_content().split()
                    )

            if title and url:
                results.append(
                    SearchResult(
                        title=title,
                        url=url,
                        description=description,
                    )
                )

        return results

    @staticmethod
    def _decode_result_url(url: str) -> str:
        if url.startswith("//"):
            url = f"https:{url}"

        parsed = urlparse(url)
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path == "/l/":
            return parse_qs(parsed.query).get("uddg", [url])[0]
        return url
