"""Public Data Portal dataset search/detail/resource helpers.

This module talks to the public data.go.kr HTML pages for dataset search and
detail lookup, then normalizes the scraped metadata into frontend-friendly JSON.
It intentionally avoids requiring API keys for search/detail because the public
portal list/detail pages are browseable, while resource preview/visualization
still fetch only user-selected URLs with SSRF and size protections.
"""

from __future__ import annotations

import csv
import ipaddress
import json
import logging
import os
import re
import socket
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

DATA_GO_KR_ORIGIN = "https://www.data.go.kr"
DATA_GO_KR_SEARCH_URL = f"{DATA_GO_KR_ORIGIN}/tcs/dss/selectDataSetList.do"
DEFAULT_PUBLIC_DATA_PORTAL_BASE_URL = DATA_GO_KR_SEARCH_URL
DATA_GO_KR_TIMEOUT_SECONDS = 10
DATA_GO_KR_DIAGNOSTIC_TIMEOUT_SECONDS = 5

logger = logging.getLogger(__name__)


RESOURCE_PREVIEW_MAX_BYTES = 256 * 1024
RESOURCE_PREVIEW_TIMEOUT_SECONDS = 8
RESOURCE_PREVIEW_DEFAULT_ROWS = 10
RESOURCE_PREVIEW_MAX_ROWS = 20
_RESOURCE_PREVIEW_SAFE_FIELDS = ("name", "format", "url", "description", "is_downloadable", "is_api")
_SENSITIVE_QUERY_KEYS = {"key", "apikey", "api_key", "servicekey", "service_key", "token", "secret", "password"}


@dataclass(frozen=True)
class ResourcePreviewResult:
    """Safe, bounded preview response for a selected resource URL."""

    status: str
    resource: dict[str, Any]
    preview: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "resource": self.resource,
            "preview": self.preview,
            "metadata": self.metadata or {},
            "message": self.message,
        }


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
    reason_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "query": self.query,
            "items": self.items,
            "message": self.message,
        }
        if self.reason_code:
            payload["reason_code"] = self.reason_code
        return payload


@dataclass(frozen=True)
class DataPortalDiagnosticResult:
    """Safe data.go.kr outbound connectivity diagnostic response."""

    status: str
    portal: str
    search_url: str
    http_status: int | None
    elapsed_ms: int
    candidate_count: int
    first_candidate: dict[str, Any] | None = None
    message: str = ""
    reason_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "portal": self.portal,
            "search_url": self.search_url,
            "http_status": self.http_status,
            "elapsed_ms": self.elapsed_ms,
            "candidate_count": self.candidate_count,
            "first_candidate": self.first_candidate,
            "message": self.message,
        }
        if self.reason_code:
            payload["reason_code"] = self.reason_code
        return payload


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



class _DataGoKrHTMLParser(HTMLParser):
    """Small dependency-free HTML parser that keeps enough structure for scraping."""

    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: dict[str, Any] = {"tag": "document", "attrs": {}, "children": [], "text": "", "parent": None}
        self.stack: list[dict[str, Any]] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = {"tag": tag.lower(), "attrs": {k.lower(): v or "" for k, v in attrs}, "children": [], "text": "", "parent": self.stack[-1]}
        self.stack[-1]["children"].append(node)
        if tag.lower() not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.stack[-1]["text"] += data


def _parse_html(html: str) -> dict[str, Any]:
    parser = _DataGoKrHTMLParser()
    parser.feed(html)
    return parser.root


def _iter_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [node]
    for child in node.get("children", []):
        nodes.extend(_iter_nodes(child))
    return nodes


def _node_text(node: dict[str, Any]) -> str:
    parts = [node.get("text", "")]
    for child in node.get("children", []):
        parts.append(_node_text(child))
    return re.sub(r"\s+", " ", unescape(" ".join(parts))).strip()


def _node_links(node: dict[str, Any]) -> list[dict[str, str]]:
    links = []
    for child in _iter_nodes(node):
        if child.get("tag") == "a" and child.get("attrs", {}).get("href"):
            href = child["attrs"]["href"].strip()
            links.append({"href": urljoin(DATA_GO_KR_ORIGIN, href), "text": _node_text(child), "title": child.get("attrs", {}).get("title", "")})
    return links


_CURRENT_DETAIL_PATH_RE = re.compile(r"^/data/\d+/(?:fileData|apiData|standardData)\.do$", re.IGNORECASE)


def _is_current_data_go_kr_detail_url(url: str) -> bool:
    parsed = urlsplit(url)
    return _CURRENT_DETAIL_PATH_RE.match(parsed.path or "") is not None


def _pick_detail_link(node: dict[str, Any]) -> str:
    links = _node_links(node)
    for link in links:
        href = link["href"]
        if _is_current_data_go_kr_detail_url(href):
            return href
    for link in links:
        href = link["href"]
        blob = f"{href} {link.get('text','')} {link.get('title','')}"
        if any(token in blob for token in ("selectDataSet", "selectFileData", "selectApiData", "dtst", "publicDataPk", "dataSetSn")):
            return href
    return links[0]["href"] if links else ""


def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        m = re.search(rf"{re.escape(label)}\s*[:：]?\s*([^|·•\n]+?)(?=\s+(?:제공기관|분류체계|수정일|갱신일|파일데이터명|오픈API명|공공데이터명|확장자|키워드|다운로드)|$)", text)
        if m:
            return m.group(1).strip(" -_/|·•")
    return ""


def parse_data_go_kr_search_html(html: str, query: str) -> DatasetSearchResult:
    root = _parse_html(html)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    item_class_re = re.compile(r"(?:^|[-_\s])(item|row|card|dataset|result)(?:[-_\s]|$)", re.IGNORECASE)
    for node in _iter_nodes(root):
        tag = node.get("tag")
        cls = node.get("attrs", {}).get("class", "")
        class_tokens = {token.lower() for token in re.split(r"\s+", cls.strip()) if token}
        if "result-list" in class_tokens or "data-list" in class_tokens:
            continue
        if tag not in {"li", "tr"} and not item_class_re.search(cls):
            continue
        detail_url = _pick_detail_link(node)
        text = _node_text(node)
        if not detail_url or len(text) < 8:
            continue
        if "selectDataSetList" in detail_url:
            continue
        title = ""
        for link in _node_links(node):
            if link["href"] == detail_url and link.get("text"):
                title = link["text"]
                break
        title = title or _extract_labeled_value(text, ("파일데이터명", "오픈API명", "공공데이터명", "서비스명")) or text[:80]
        data_type = "FILE" if "파일데이터" in text or "FILE" in detail_url.upper() else ("API" if "오픈API" in text or "API" in detail_url.upper() else "UNKNOWN")
        key = detail_url or title
        if key in seen:
            continue
        seen.add(key)
        candidates.append({
            "id": _extract_labeled_value(detail_url, ("publicDataPk", "dataSetSn")) or None,
            "title": title.strip(),
            "description": text[:500],
            "provider": _extract_labeled_value(text, ("제공기관", "기관명")),
            "category": _extract_labeled_value(text, ("분류체계", "분류")),
            "format": _extract_labeled_value(text, ("확장자", "파일형식", "포맷")) or data_type,
            "updated_at": _extract_labeled_value(text, ("수정일", "갱신일", "등록일")) or None,
            "url": detail_url,
            "detail_url": detail_url,
            "data_type": data_type,
            "keywords": [kw for kw in re.split(r"\s+", query) if kw],
            "raw": {"url": detail_url, "detailUrl": detail_url, "title": title, "description": text, "provider": _extract_labeled_value(text, ("제공기관", "기관명")), "format": _extract_labeled_value(text, ("확장자", "파일형식", "포맷")) or data_type, "data_type": data_type},
        })
        if len(candidates) >= 20:
            break
    return DatasetSearchResult(status="success", query=query, items=candidates, message="" if candidates else "검색 결과가 없거나 data.go.kr HTML 구조를 해석하지 못했습니다.")


def parse_data_go_kr_detail_html(html: str, detail_url: str = "") -> DatasetDetailResult:
    root = _parse_html(html)
    page_text = _node_text(root)
    declared_format = _extract_labeled_value(page_text, ("확장자", "제공형태", "파일형식", "포맷"))
    h_texts = [_node_text(n) for n in _iter_nodes(root) if n.get("tag") in {"h1", "h2", "h3"} and _node_text(n)]
    title = h_texts[0] if h_texts else _extract_labeled_value(page_text, ("파일데이터명", "오픈API명", "공공데이터명")) or "공공데이터 상세"
    resources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in _node_links(root):
        href = link["href"]
        blob = f"{href} {link.get('text','')} {link.get('title','')}".lower()
        if not any(token in blob for token in ("download", "file", ".csv", ".json", ".xls", "api", "get", "excel")):
            continue
        if href in seen or "javascript:" in href.lower():
            continue
        seen.add(href)
        fmt = _infer_resource_format({"url": href, "name": link.get("text", ""), "description": f"{link.get('title', '')} {page_text[:300]}", "format": declared_format})
        resources.append({"name": link.get("text") or link.get("title") or "리소스 후보", "format": fmt, "url": href, "description": "data.go.kr 상세 페이지에서 추출한 링크입니다.", "is_downloadable": fmt != "API", "is_api": fmt == "API"})
    dataset = {"id": None, "title": title, "description": page_text[:1000], "provider": _extract_labeled_value(page_text, ("제공기관", "기관명")), "category": _extract_labeled_value(page_text, ("분류체계", "분류")), "format": declared_format, "updated_at": _extract_labeled_value(page_text, ("수정일", "갱신일", "등록일")) or None, "url": detail_url}
    msg = "" if resources else "상세 페이지는 찾았지만 다운로드 URL을 자동 추출하지 못했습니다. 상세 페이지에서 직접 다운로드가 필요합니다."
    return DatasetDetailResult(status="success", dataset=dataset, resources=resources, message=msg)



def _build_data_go_kr_search_url(keyword: str, page: int = 1, per_page: int = 10) -> str:
    params = {
        "dType": "TOTAL",
        "keyword": _clean_string(keyword),
        "detailKeyword": "",
        "publicDataPk": "",
        "recmSe": "",
        "detailText": "",
        "relatedKeyword": "",
        "commaNotInData": "",
        "commaAndData": "",
        "commaOrData": "",
        "must_not": "",
        "tabId": "",
        "dataSetCoreTf": "",
        "coreDataNm": "",
        "sort": "",
        "relRadio": "",
        "orgFullName": "",
        "orgFilter": "",
        "org": "",
        "orgSearch": "",
        "currentPage": page,
        "perPage": per_page,
        "brm": "",
        "instt": "",
        "svcType": "",
        "kwrdArray": "",
        "extsn": "",
        "coreDataNmArray": "",
        "operator": "OR",
        "pblonsipScopeCode": "",
    }
    return f"{DATA_GO_KR_SEARCH_URL}?{urlencode(params)}"


def _classify_portal_exception(exc: BaseException) -> tuple[str, int | None]:
    if isinstance(exc, HTTPError):
        return "DATA_PORTAL_HTTP_ERROR", exc.code
    if isinstance(exc, TimeoutError):
        return "DATA_PORTAL_TIMEOUT", None
    if isinstance(exc, URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
            return "DATA_PORTAL_TIMEOUT", None
        return "DATA_PORTAL_NETWORK_ERROR", None
    return "DATA_PORTAL_NETWORK_ERROR", None


def _read_text_url_with_status(url: str, timeout: int = DATA_GO_KR_TIMEOUT_SECONDS) -> tuple[str, int, str]:
    req = Request(url, headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": "Mozilla/5.0 Public-Data-MOTIR/1.0"})
    with urlopen(req, timeout=timeout) as response:  # noqa: S310 - fixed public portal search URL or pre-validated detail URL.
        final_url = response.geturl() if hasattr(response, "geturl") else url
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        status_code = getattr(response, "status", None) or getattr(response, "code", 200)
        return raw.decode(charset, errors="replace"), int(status_code), final_url

def _read_text_url(url: str) -> str:
    html, _status_code, _final_url = _read_text_url_with_status(url, DATA_GO_KR_TIMEOUT_SECONDS)
    return html


def validate_data_go_kr_detail_url(url: str) -> str:
    """Allow only HTTPS data.go.kr detail pages before fetching user-selected detail URLs."""
    cleaned = _clean_string(url)
    parsed = urlsplit(cleaned)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in {"www.data.go.kr", "data.go.kr"}:
        raise ValueError("data.go.kr HTTPS 상세 URL만 호출할 수 있습니다.")
    if not _is_safe_hostname(host):
        raise ValueError("안전하지 않은 상세 URL host입니다.")
    return cleaned


def _read_data_go_kr_detail_url(url: str) -> tuple[str, str]:
    safe_url = validate_data_go_kr_detail_url(url)
    req = Request(safe_url, headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": "Mozilla/5.0 Public-Data-MOTIR/1.0"})
    with urlopen(req, timeout=DATA_GO_KR_TIMEOUT_SECONDS) as response:  # noqa: S310 - URL and redirect target are constrained to data.go.kr HTTPS.
        final_url = response.geturl() if hasattr(response, "geturl") else safe_url
        validate_data_go_kr_detail_url(final_url)
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace"), final_url


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

    text_blob = " ".join(_clean_string(_first_value(resource, keys)) for keys in (("name", "title", "resourceName", "fileName", "apiName", "서비스명", "파일명"), ("description", "desc", "summary", "contents", "설명"), ("linkText", "text", "titleText")))
    for label in ("CSV", "TSV", "JSON", "XLSX", "XLS", "XML"):
        if re.search(rf"(?<![A-Z0-9]){label}(?![A-Z0-9])", text_blob.upper()):
            return label

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
    """Fetch and parse a data.go.kr detail page by absolute detail URL."""
    identifier = _clean_string(dataset_id_or_url)
    if not identifier:
        return DatasetDetailResult(status="error", dataset=None, resources=[], message="상세 URL이 필요합니다.")
    if not _looks_like_url(identifier):
        return DatasetDetailResult(status="error", dataset=None, resources=[], message="검색 결과의 data.go.kr 상세 URL이 필요합니다.")
    try:
        html, final_url = _read_data_go_kr_detail_url(identifier)
    except ValueError as exc:
        return DatasetDetailResult(status="error", dataset={"title": "공공데이터 상세", "url": sanitize_url_for_response(identifier)}, resources=[], message=str(exc))
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        reason_code, http_status = _classify_portal_exception(exc)
        logger.warning("data.go.kr detail failed url=%s reason=%s http_status=%s", sanitize_url_for_response(identifier), reason_code, http_status)
        return DatasetDetailResult(status="error", dataset={"title": "공공데이터 상세", "url": sanitize_url_for_response(identifier)}, resources=[], message="공공데이터포털 상세 페이지 호출에 실패했습니다.")
    return parse_data_go_kr_detail_html(html, sanitize_url_for_response(final_url))


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


def check_data_go_kr_connectivity(query: str = "서울 부동산 가격") -> DataPortalDiagnosticResult:
    """Run a bounded, fixed-endpoint data.go.kr search diagnostic without returning raw HTML."""
    keyword = _clean_string(query) or "서울 부동산 가격"
    url = _build_data_go_kr_search_url(keyword, page=1, per_page=5)
    safe_url = sanitize_url_for_response(url)
    started = time.perf_counter()
    try:
        html, http_status, final_url = _read_text_url_with_status(url, DATA_GO_KR_DIAGNOSTIC_TIMEOUT_SECONDS)
        safe_url = sanitize_url_for_response(final_url)
        parsed = parse_data_go_kr_search_html(html, keyword)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if not parsed.items:
            logger.warning("data.go.kr diagnostic parse empty url=%s reason=%s elapsed_ms=%s", safe_url, "DATA_PORTAL_PARSE_EMPTY", elapsed_ms)
            return DataPortalDiagnosticResult(
                status="error",
                portal="data.go.kr",
                search_url=safe_url,
                http_status=http_status,
                elapsed_ms=elapsed_ms,
                candidate_count=0,
                message="data.go.kr 검색 페이지는 응답했지만 후보를 해석하지 못했습니다.",
                reason_code="DATA_PORTAL_PARSE_EMPTY",
            )
        first = parsed.items[0]
        first_candidate = {key: first.get(key) for key in ("title", "provider", "format", "url")}
        logger.info("data.go.kr diagnostic success url=%s http_status=%s candidate_count=%s elapsed_ms=%s", safe_url, http_status, len(parsed.items), elapsed_ms)
        return DataPortalDiagnosticResult(
            status="success",
            portal="data.go.kr",
            search_url=safe_url,
            http_status=http_status,
            elapsed_ms=elapsed_ms,
            candidate_count=len(parsed.items),
            first_candidate=first_candidate,
            message="",
        )
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        reason_code, http_status = _classify_portal_exception(exc)
        logger.warning("data.go.kr diagnostic failed url=%s reason=%s http_status=%s elapsed_ms=%s", safe_url, reason_code, http_status, elapsed_ms)
        return DataPortalDiagnosticResult(
            status="error",
            portal="data.go.kr",
            search_url=safe_url,
            http_status=http_status,
            elapsed_ms=elapsed_ms,
            candidate_count=0,
            message="data.go.kr 검색 페이지 호출에 실패했습니다. 네트워크, 프록시, WAF 또는 포털 접근 상태를 확인해 주세요.",
            reason_code=reason_code,
        )
    except Exception:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.exception("data.go.kr diagnostic internal error url=%s elapsed_ms=%s", safe_url, elapsed_ms)
        return DataPortalDiagnosticResult(
            status="error",
            portal="data.go.kr",
            search_url=safe_url,
            http_status=None,
            elapsed_ms=elapsed_ms,
            candidate_count=0,
            message="data.go.kr 진단 처리 중 내부 오류가 발생했습니다.",
            reason_code="DATA_PORTAL_INTERNAL_ERROR",
        )


def fetch_dataset_search(keyword: str, page: int = 1, per_page: int = 10) -> DatasetSearchResult:
    """Fetch data.go.kr public HTML search results and normalize candidate cards."""
    keyword = _clean_string(keyword)
    url = _build_data_go_kr_search_url(keyword, page=page, per_page=per_page)
    safe_url = sanitize_url_for_response(url)
    started = time.perf_counter()
    try:
        html = _read_text_url(url)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        reason_code, http_status = _classify_portal_exception(exc)
        logger.warning("data.go.kr search failed url=%s reason=%s http_status=%s elapsed_ms=%s", safe_url, reason_code, http_status, elapsed_ms)
        return DatasetSearchResult(status="error", query=keyword, items=[], message="data.go.kr 검색 페이지 호출에 실패했습니다. 네트워크, 프록시 또는 포털 접근 상태를 확인해 주세요.", reason_code=reason_code)
    result = parse_data_go_kr_search_html(html, keyword)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if not result.items:
        logger.warning("data.go.kr search returned no parseable candidates url=%s reason=%s elapsed_ms=%s", safe_url, "DATA_PORTAL_PARSE_EMPTY", elapsed_ms)
        return DatasetSearchResult(status=result.status, query=result.query, items=result.items, message=result.message, reason_code="DATA_PORTAL_PARSE_EMPTY")
    return result

def sanitize_url_for_response(url: str) -> str:
    """Return URL safe for metadata/log-style responses by redacting sensitive query values."""
    parsed = urlsplit(_clean_string(url))
    if not parsed.scheme or not parsed.netloc:
        return _clean_string(url)
    safe_query = urlencode(
        [(key, "REDACTED" if key.lower() in _SENSITIVE_QUERY_KEYS else value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)]
    )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, safe_query, ""))


def _is_safe_hostname(hostname: str) -> bool:
    host = hostname.strip().strip("[]").lower()
    if not host or host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost") or host.endswith(".local"):
        return False

    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError:
            # DNS failure is treated as external fetch failure later; the syntactic host is not internal.
            return True
        addresses = []
        for info in infos:
            try:
                addresses.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                return False

    for address in addresses:
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            return False
    return True


def validate_resource_url(resource: dict[str, Any]) -> str:
    """Validate selected resource URL against SSRF-prone schemes and internal hosts."""
    url = _first_nullable_text(resource, ("url", "downloadUrl", "download_url", "fileUrl", "apiUrl", "endpoint", "link", "다운로드URL", "APIURL"))
    if not url:
        raise ValueError("resource.url이 필요합니다.")

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("http:// 또는 https:// URL만 미리보기할 수 있습니다.")
    if not parsed.hostname or not _is_safe_hostname(parsed.hostname):
        raise ValueError("localhost, private IP, 내부망 host의 resource URL은 미리보기할 수 없습니다.")
    return url


def infer_resource_format(resource: dict[str, Any], content_type: str = "") -> str:
    """Infer preview format from declared metadata, content-type, and URL extension."""
    declared = _infer_resource_format(resource).upper()
    if declared in {"CSV", "TSV", "JSON", "XLS", "XLSX"}:
        return declared

    lowered_type = content_type.lower()
    if "json" in lowered_type:
        return "JSON"
    if "tab-separated" in lowered_type or "tsv" in lowered_type:
        return "TSV"
    if "csv" in lowered_type or "text/plain" in lowered_type:
        return "CSV"

    url = _clean_string(resource.get("url"))
    path = urlsplit(url).path.lower()
    if path.endswith(".json"):
        return "JSON"
    if path.endswith(".tsv"):
        return "TSV"
    if path.endswith(".csv"):
        return "CSV"
    if path.endswith(".xlsx"):
        return "XLSX"
    if path.endswith(".xls"):
        return "XLS"
    return "UNKNOWN"


def _safe_resource_payload(resource: dict[str, Any]) -> dict[str, Any]:
    return {key: (sanitize_url_for_response(resource[key]) if key == "url" and resource.get(key) else resource.get(key)) for key in _RESOURCE_PREVIEW_SAFE_FIELDS if key in resource}


def _read_limited_response(response: Any, max_bytes: int) -> tuple[bytes, bool]:
    data = response.read(max_bytes + 1)
    return data[:max_bytes], len(data) > max_bytes


def normalize_resource_preview(resource: dict[str, Any], raw_bytes: bytes, fmt: str, max_rows: int, truncated: bool) -> dict[str, Any]:
    """Parse a bounded byte sample into a frontend-friendly preview payload."""
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    row_limit = max(1, min(max_rows, RESOURCE_PREVIEW_MAX_ROWS))

    if fmt in {"CSV", "TSV"}:
        delimiter = "\t" if fmt == "TSV" else ","
        sample = text.splitlines()[: row_limit + 2]
        rows = list(csv.reader(sample, delimiter=delimiter))
        if not rows:
            raise ValueError("미리보기할 행을 찾지 못했습니다.")
        headers = [str(value) for value in rows[0]]
        body_rows = [[str(value) for value in row] for row in rows[1 : row_limit + 1]]
        return {
            "kind": "table",
            "headers": headers,
            "rows": body_rows,
            "truncated": truncated or len(rows) > row_limit + 1,
            "message": f"처음 {len(body_rows)}행만 표시합니다.",
        }

    if fmt == "JSON":
        payload = json.loads(text)
        if isinstance(payload, list):
            snippet = payload[:row_limit]
            is_truncated = truncated or len(payload) > row_limit
        elif isinstance(payload, dict):
            snippet = dict(list(payload.items())[:row_limit])
            is_truncated = truncated or len(payload) > row_limit
        else:
            snippet = payload
            is_truncated = truncated
        return {
            "kind": "json",
            "data": snippet,
            "truncated": is_truncated,
            "message": "JSON top-level 일부만 표시합니다.",
        }

    if fmt in {"XLS", "XLSX"}:
        raise ValueError("원격 Excel 파일은 이번 단계에서 직접 파싱하지 않습니다. 파일을 내려받아 직접 업로드해 주세요.")
    raise ValueError("CSV/TSV/JSON 리소스만 미리보기를 지원합니다.")


def fetch_resource_preview(resource: dict[str, Any], max_bytes: int = RESOURCE_PREVIEW_MAX_BYTES, max_rows: int = RESOURCE_PREVIEW_DEFAULT_ROWS) -> ResourcePreviewResult:
    """Fetch a small bounded preview for a validated external CSV/TSV/JSON resource."""
    source = resource if isinstance(resource, dict) else {}
    safe_resource = _safe_resource_payload(source)
    url = validate_resource_url(source)
    request = Request(url, headers={"Accept": "text/csv, application/json, text/tab-separated-values, */*", "User-Agent": "Public-Data-MOTIR/1.0"})

    try:
        with urlopen(request, timeout=RESOURCE_PREVIEW_TIMEOUT_SECONDS) as response:  # noqa: S310 - URL is validated against internal hosts and unsafe schemes.
            final_url = response.geturl() if hasattr(response, "geturl") else url
            final_parsed = urlsplit(final_url)
            if final_parsed.hostname and not _is_safe_hostname(final_parsed.hostname):
                raise ValueError("redirect 대상 host가 안전하지 않습니다.")
            content_type = response.headers.get("Content-Type", "") if getattr(response, "headers", None) else ""
            fmt = infer_resource_format({**source, "url": final_url}, content_type)
            raw_bytes, truncated = _read_limited_response(response, max_bytes)
    except ValueError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError):
        return ResourcePreviewResult(status="error", resource=safe_resource, preview=None, metadata={}, message="resource URL 호출에 실패했습니다. URL, timeout 또는 접근 권한을 확인해 주세요.")

    try:
        preview = normalize_resource_preview(source, raw_bytes, fmt, max_rows, truncated)
    except (ValueError, json.JSONDecodeError, csv.Error, UnicodeError) as exc:
        return ResourcePreviewResult(status="error", resource=safe_resource, preview=None, metadata={"content_type": content_type, "bytes_read": len(raw_bytes), "source_url": sanitize_url_for_response(final_url)}, message=str(exc))

    return ResourcePreviewResult(
        status="success",
        resource=safe_resource,
        preview=preview,
        metadata={"content_type": content_type, "bytes_read": len(raw_bytes), "source_url": sanitize_url_for_response(final_url)},
        message="",
    )
