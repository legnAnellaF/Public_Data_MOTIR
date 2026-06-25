"""Configurable Public Data Portal dataset search client.

The first integration step intentionally keeps the real portal endpoint configurable.
TODO: Confirm the production 공공데이터포털 dataset-search endpoint and response contract,
then set PUBLIC_DATA_PORTAL_BASE_URL in deployment without hard-coding secrets here.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_PUBLIC_DATA_PORTAL_BASE_URL = "https://api.odcloud.kr/api"


@dataclass(frozen=True)
class DatasetSearchResult:
    """Normalized dataset search response used by the API route."""

    status: str
    query: str
    items: list[dict[str, Any]]
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "query": self.query,
            "items": self.items,
            "message": self.message,
        }


def _clean_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_text(source: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = source.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return ""


def _first_nullable_text(source: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    value = _first_text(source, keys)
    return value or None


def _extract_items(payload: Any) -> list[Any]:
    """Extract a candidate item array from common public-data response shapes."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("items", "data", "result", "results", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _extract_items(value)
            if nested:
                return nested

    response = payload.get("response")
    if isinstance(response, dict):
        body = response.get("body")
        nested = _extract_items(body if body is not None else response)
        if nested:
            return nested

    return []


def normalize_dataset_item(item: Any) -> dict[str, Any] | None:
    """Normalize one raw portal item into the frontend-friendly dataset card schema."""
    if not isinstance(item, dict):
        return None

    title = _first_text(
        item,
        (
            "title",
            "name",
            "datasetName",
            "dataName",
            "serviceName",
            "infNm",
            "dtstNm",
            "공공데이터명",
            "데이터명",
        ),
    )
    if not title:
        return None

    return {
        "id": _first_nullable_text(item, ("id", "datasetId", "dataId", "serviceKey", "infId", "dtstId")),
        "title": title,
        "description": _first_text(item, ("description", "desc", "summary", "contents", "infExp", "설명")),
        "provider": _first_text(item, ("provider", "organization", "orgName", "providerName", "기관명", "제공기관")),
        "category": _first_text(item, ("category", "categoryName", "classification", "분류", "분야")),
        "format": _first_text(item, ("format", "fileFormat", "dataFormat", "mediaType", "확장자")),
        "updated_at": _first_nullable_text(item, ("updated_at", "updatedAt", "modifiedDate", "updateDate", "수정일", "갱신일")),
        "url": _first_nullable_text(item, ("url", "link", "detailUrl", "apiUrl", "endpoint", "상세URL")),
        "raw": item,
    }


def normalize_dataset_search_response(payload: Any, query: str) -> DatasetSearchResult:
    """Normalize a raw portal search response into a stable API response."""
    items = [normalized for raw in _extract_items(payload) if (normalized := normalize_dataset_item(raw))]
    return DatasetSearchResult(status="success", query=query, items=items, message="")


def _build_search_url(base_url: str, keyword: str, page: int, per_page: int, api_key: str) -> str:
    base = base_url.rstrip("/")
    params = urlencode(
        {
            "keyword": keyword,
            "page": page,
            "perPage": per_page,
            "serviceKey": api_key,
        }
    )
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{params}"


def fetch_dataset_search(keyword: str, page: int = 1, per_page: int = 10) -> DatasetSearchResult:
    """Call the configured public-data search endpoint and return normalized results.

    Returns an error-shaped DatasetSearchResult instead of raising for missing config or
    provider/network failures so the route can send safe JSON without exposing keys.
    """
    api_key = _clean_string(os.getenv("PUBLIC_DATA_API_KEY"))
    if not api_key:
        return DatasetSearchResult(
            status="error",
            query=keyword,
            items=[],
            message="PUBLIC_DATA_API_KEY 설정이 필요합니다. 실제 키 값은 서버 환경 변수에만 저장해 주세요.",
        )

    base_url = _clean_string(os.getenv("PUBLIC_DATA_PORTAL_BASE_URL")) or DEFAULT_PUBLIC_DATA_PORTAL_BASE_URL
    url = _build_search_url(base_url, keyword, page, per_page, api_key)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Public-Data-MOTIR/1.0"})

    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - URL is operator-configured.
            raw_text = response.read().decode("utf-8")
        payload = json.loads(raw_text)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return DatasetSearchResult(
            status="error",
            query=keyword,
            items=[],
            message="공공데이터포털 검색 API 호출 또는 응답 해석에 실패했습니다. endpoint/key 설정을 확인해 주세요.",
        )

    return normalize_dataset_search_response(payload, keyword)
