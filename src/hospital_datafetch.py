from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class Hospital:
    id: str
    name: str
    city: str
    state: str
    zip: str
    county: str

    @classmethod
    def from_api(cls, record: dict[str, Any]) -> Hospital:
        return cls(
            id=str(record.get("facility_id", "")),
            name=str(record.get("facility_name", "")),
            city=str(record.get("citytown", "")),
            state=str(record.get("state", "")),
            zip=str(record.get("zip_code", "")),
            county=str(record.get("countyparish", "")),
        )


class CMSHospitalApiError(RuntimeError):
    """Raised when the CMS API cannot be reached or returns invalid data."""


class CMSHospitalClient:

    BASE_URL = (
        "https://data.cms.gov/provider-data/api/1/datastore/query/"
        "xubh-q36u/0"
    )

    def __init__(self, base_url: str = BASE_URL, timeout: float = 30.0) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        self.base_url = base_url
        self.timeout = timeout

    def fetch(self, offset: int = 0, limit: int = 10) -> list[Hospital]:
        payload = self._request(offset=offset, limit=limit)
        results = payload.get("results")

        if not isinstance(results, list):
            raise CMSHospitalApiError(
                "CMS API response did not contain a results list"
            )

        return [
            Hospital.from_api(record)
            for record in results
            if isinstance(record, dict)
        ]

    def fetch_all(
        self, page_size: int = 500, start_offset: int = 0
    ) -> Iterator[Hospital]:
        offset = start_offset

        while True:
            payload = self._request(offset=offset, limit=page_size)
            results = payload.get("results")

            if not isinstance(results, list):
                raise CMSHospitalApiError(
                    "CMS API response did not contain a results list"
                )

            for record in results:
                if isinstance(record, dict):
                    yield Hospital.from_api(record)

            offset += len(results)
            total = payload.get("count")
            if not results or (isinstance(total, int) and offset >= total):
                break

    def _request(self, offset: int, limit: int) -> dict[str, Any]:
        if offset < 0:
            raise ValueError("offset cannot be negative")
        if limit <= 0:
            raise ValueError("limit must be greater than zero")

        url = f"{self.base_url}?{urlencode({'offset': offset, 'limit': limit})}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "MedScout/1.0",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except HTTPError as error:
            raise CMSHospitalApiError(
                f"CMS API returned HTTP {error.code}"
            ) from error
        except URLError as error:
            raise CMSHospitalApiError(
                f"Could not connect to CMS API: {error.reason}"
            ) from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise CMSHospitalApiError(
                "CMS API returned invalid JSON"
            ) from error

        if not isinstance(payload, dict):
            raise CMSHospitalApiError("CMS API returned an invalid response")

        return payload
