from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from src.duckduckgo_search import (
    DuckDuckGoSearchClient,
    DuckDuckGoSearchError,
    SearchResult,
)


SEARCH_HTML = """
<html>
  <body>
    <div class="result results_links">
      <h2>
        <a class="result__a"
           href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fhospital.example%2Felectives">
          Visiting Students
        </a>
      </h2>
      <a class="result__snippet">Clinical elective information.</a>
    </div>
  </body>
</html>
"""


class FakeClient:
    def __init__(
        self,
        *,
        response: httpx.Response | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.closed = False

    def get(self, url: str, **options: object) -> httpx.Response:
        self.calls.append((url, options))
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response

    def close(self) -> None:
        self.closed = True


class DuckDuckGoSearchClientTests(unittest.TestCase):
    def test_text_returns_structured_results(self) -> None:
        client_backend = FakeClient(
            response=httpx.Response(200, text=SEARCH_HTML)
        )
        with patch(
            "src.duckduckgo_search.httpx.Client",
            return_value=client_backend,
        ):
            client = DuckDuckGoSearchClient()

        results = client.text(
            '"Example Hospital" "clinical elective rotations"',
            max_results=5,
            page=2,
            time_limit="y",
        )

        self.assertEqual(
            results,
            [
                SearchResult(
                    title="Visiting Students",
                    url="https://hospital.example/electives",
                    description="Clinical elective information.",
                )
            ],
        )
        self.assertEqual(
            client_backend.calls,
            [
                (
                    "https://html.duckduckgo.com/html/",
                    {
                        "params": {
                            "q": (
                                '"Example Hospital" '
                                '"clinical elective rotations"'
                            ),
                            "kl": "us-en",
                            "kp": "-1",
                            "s": "10",
                            "df": "y",
                        }
                    },
                )
            ],
        )

    def test_text_returns_empty_list_when_there_are_no_results(self) -> None:
        client_backend = FakeClient(
            response=httpx.Response(200, text="<html><body></body></html>")
        )
        with patch(
            "src.duckduckgo_search.httpx.Client",
            return_value=client_backend,
        ):
            client = DuckDuckGoSearchClient()

        self.assertEqual(client.text("electives"), [])

    def test_text_wraps_invalid_html(self) -> None:
        client_backend = FakeClient(response=httpx.Response(200, text=""))
        with patch(
            "src.duckduckgo_search.httpx.Client",
            return_value=client_backend,
        ):
            client = DuckDuckGoSearchClient()

        with self.assertRaises(DuckDuckGoSearchError):
            client.text("electives")

    def test_text_validates_arguments(self) -> None:
        with patch(
            "src.duckduckgo_search.httpx.Client",
            return_value=FakeClient(),
        ):
            client = DuckDuckGoSearchClient()

        invalid_calls = (
            lambda: client.text(""),
            lambda: client.text("query", max_results=0),
            lambda: client.text("query", page=0),
            lambda: client.text("query", time_limit="invalid"),
        )

        for call in invalid_calls:
            with self.subTest(call=call):
                with self.assertRaises(ValueError):
                    call()

    def test_text_wraps_backend_errors(self) -> None:
        client_backend = FakeClient(
            error=httpx.ConnectError("connection failed")
        )
        with patch(
            "src.duckduckgo_search.httpx.Client",
            return_value=client_backend,
        ):
            client = DuckDuckGoSearchClient()

        with self.assertRaises(DuckDuckGoSearchError) as context:
            client.text("Example Hospital electives")

        self.assertIsInstance(context.exception.__cause__, httpx.ConnectError)

    def test_text_reports_rejected_requests(self) -> None:
        client_backend = FakeClient(response=httpx.Response(202))
        with patch(
            "src.duckduckgo_search.httpx.Client",
            return_value=client_backend,
        ):
            client = DuckDuckGoSearchClient()

        with self.assertRaisesRegex(
            DuckDuckGoSearchError,
            "HTTP 202",
        ):
            client.text("Example Hospital electives")

    def test_constructor_validates_configuration(self) -> None:
        with self.assertRaises(ValueError):
            DuckDuckGoSearchClient(region="")
        with self.assertRaises(ValueError):
            DuckDuckGoSearchClient(safe_search="invalid")
        with self.assertRaises(ValueError):
            DuckDuckGoSearchClient(timeout=0)

    def test_context_manager_closes_client(self) -> None:
        client_backend = FakeClient()
        with patch(
            "src.duckduckgo_search.httpx.Client",
            return_value=client_backend,
        ):
            with DuckDuckGoSearchClient():
                pass

        self.assertTrue(client_backend.closed)


if __name__ == "__main__":
    unittest.main()
