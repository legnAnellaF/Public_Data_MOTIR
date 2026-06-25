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
class DatasetDetailResult:
    """Normalized dataset detail response used by the API route."""

    status: str
    dataset: dict[str, Any] | None
    resources: list[dict[str, Any]]
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dataset": self.dataset,
            "resources": self.resources,
            "message": self.message,
        }


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



def _first_value(source: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _looks_like_url(value: Any) -> bool:
    text = _clean_string(value).lower()
    return text.startswith("http://") or text.startswith("https://")


def _infer_resource_format(resource: dict[str, Any]) -> str:
    explicit = _first_text(resource, ("format", "fileFormat", "dataFormat", "mediaType", "type", "확장자"))
    if explicit:
        return explicit.upper()

    url = _clean_string(_first_value(resource, ("url", "downloadUrl", "apiUrl", "endpoint", "link", "다운로드URL", "APIURL")))
    lowered = url.lower().split("?")[0]
    for suffix, label in ((".csv", "CSV"), (".xlsx", "XLSX"), (".xls", "XLS"), (".json", "JSON"), (".xml", "XML")):
        if lowered.endswith(suffix):
            return label
    return "API" if "api" in lowered else "unknown"


def _iter_resource_candidates(raw: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for key in ("resources", "resource", "files", "file", "items", "apis", "api", "다운로드", "파일"):
        value = raw.get(key)
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            nested = _extract_items(value)
            if nested:
                candidates.extend(item for item in nested if isinstance(item, dict))
            else:
                candidates.append(value)

    direct_url = _first_value(raw, ("downloadUrl", "download_url", "fileUrl", "apiUrl", "endpoint", "url", "link"))
    if _looks_like_url(direct_url):
        candidates.append(
            {
                "name": _first_text(raw, ("title", "name", "datasetName", "dataName", "serviceName", "공공데이터명")) or "데이터셋 링크",
                "url": direct_url,
                "description": _first_text(raw, ("description", "desc", "summary", "contents", "infExp", "설명")),
                "format": _first_text(raw, ("format", "fileFormat", "dataFormat", "mediaType", "확장자")),
            }
        )
    return candidates


def extract_resource_links(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract normalized download/API link candidates without downloading them."""
    if not isinstance(raw, dict):
        return []

    resources: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in _iter_resource_candidates(raw):
        url = _first_nullable_text(
            candidate,
            ("url", "downloadUrl", "download_url", "fileUrl", "apiUrl", "endpoint", "link", "다운로드URL", "APIURL"),
        )
        name = _first_text(candidate, ("name", "title", "resourceName", "fileName", "apiName", "서비스명", "파일명")) or "리소스 후보"
        fmt = _infer_resource_format(candidate)
        description = _first_text(candidate, ("description", "desc", "summary", "contents", "설명"))
        lower_blob = " ".join(_clean_string(candidate.get(key)).lower() for key in candidate)
        is_api = fmt.upper() == "API" or "api" in lower_blob or "openapi" in lower_blob
        is_downloadable = bool(url) and not is_api
        key = (name, url or "")
        if key in seen:
            continue
        seen.add(key)
        resources.append(
            {
                "name": name,
                "format": fmt,
                "url": url,
                "description": description,
                "is_downloadable": is_downloadable,
                "is_api": is_api,
            }
        )
    return resources


def normalize_dataset_detail(raw: dict[str, Any]) -> DatasetDetailResult:
    """Normalize raw detail/search-item payload into stable metadata and resource candidates."""
    source = raw if isinstance(raw, dict) else {}
    dataset = normalize_dataset_item(source) or {
        "id": _first_nullable_text(source, ("id", "datasetId", "dataId", "serviceKey", "infId", "dtstId")),
        "title": _first_text(source, ("title", "name", "datasetName", "dataName", "serviceName", "공공데이터명")) or "제목 없는 데이터셋",
        "description": _first_text(source, ("description", "desc", "summary", "contents", "infExp", "설명")),
        "provider": _first_text(source, ("provider", "organization", "orgName", "providerName", "기관명", "제공기관")),
        "category": _first_text(source, ("category", "categoryName", "classification", "분류", "분야")),
        "format": _first_text(source, ("format", "fileFormat", "dataFormat", "mediaType", "확장자")),
        "updated_at": _first_nullable_text(source, ("updated_at", "updatedAt", "modifiedDate", "updateDate", "수정일", "갱신일")),
        "url": _first_nullable_text(source, ("url", "link", "detailUrl", "apiUrl", "endpoint", "상세URL")),
        "raw": source,
    }
    dataset.pop("raw", None)
    return DatasetDetailResult(status="success", dataset=dataset, resources=extract_resource_links(source), message="")


def _build_detail_url(base_url: str, dataset_id_or_url: str, api_key: str) -> str:
    # TODO: Confirm the production 공공데이터포털 detail endpoint/contract.
    # If a full detail URL is supplied, call it as configured by the selected search item.
    if _looks_like_url(dataset_id_or_url):
        separator = "&" if "?" in dataset_id_or_url else "?"
        return f"{dataset_id_or_url}{separator}{urlencode({'serviceKey': api_key})}"
    base = base_url.rstrip("/")
    params = urlencode({"datasetId": dataset_id_or_url, "serviceKey": api_key})
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{params}"


def fetch_dataset_detail(dataset_id_or_url: str) -> DatasetDetailResult:
    """Fetch and normalize dataset detail from configured portal endpoint.

    The official detail endpoint is intentionally not hard-coded. Until deployment
    config points PUBLIC_DATA_PORTAL_BASE_URL at a confirmed detail-capable endpoint,
    routes may pass the selected raw search item to normalize_dataset_detail instead.
    """
    api_key = _clean_string(os.getenv("PUBLIC_DATA_API_KEY"))
    if not api_key:
        return DatasetDetailResult(
            status="error",
            dataset=None,
            resources=[],
            message="PUBLIC_DATA_API_KEY 설정이 필요합니다. 실제 키 값은 서버 환경 변수에만 저장해 주세요.",
        )
    base_url = _clean_string(os.getenv("PUBLIC_DATA_PORTAL_BASE_URL"))
    if not base_url:
        return DatasetDetailResult(
            status="error",
            dataset=None,
            resources=[],
            message="PUBLIC_DATA_PORTAL_BASE_URL 설정이 필요합니다. 상세 endpoint가 확정되면 서버 환경 변수로 지정해 주세요.",
        )

    request = Request(_build_detail_url(base_url, dataset_id_or_url, api_key), headers={"Accept": "application/json", "User-Agent": "Public-Data-MOTIR/1.0"})
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - URL is operator-configured.
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return DatasetDetailResult(status="error", dataset=None, resources=[], message="공공데이터포털 상세 API 호출 또는 응답 해석에 실패했습니다. endpoint/key 설정을 확인해 주세요.")

    items = _extract_items(payload)
    detail_raw = items[0] if items and isinstance(items[0], dict) else payload
    return normalize_dataset_detail(detail_raw if isinstance(detail_raw, dict) else {})


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
