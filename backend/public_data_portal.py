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
DATA_GO_KR_TIMEOUT_SECONDS = 8
DATA_GO_KR_RETRY_TIMEOUT_SECONDS = 5
DATA_GO_KR_RETRY_BACKOFF_SECONDS = 0.35
DATA_GO_KR_DIAGNOSTIC_TIMEOUT_SECONDS = 5

logger = logging.getLogger(__name__)


RESOURCE_PREVIEW_MAX_BYTES = 256 * 1024
RESOURCE_PREVIEW_TIMEOUT_SECONDS = 8
RESOURCE_PREVIEW_DEFAULT_ROWS = 10
RESOURCE_PREVIEW_MAX_ROWS = 20
_RESOURCE_PREVIEW_SAFE_FIELDS = ("name", "format", "url", "description", "is_downloadable", "is_api", "is_previewable", "is_visualizable", "unsupported_reason", "source_hint")
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
        payload = {
            "status": self.status,
            "resource": self.resource,
            "preview": self.preview,
            "metadata": self.metadata or {},
            "message": self.message,
        }
        reason_code = (self.metadata or {}).get("reason_code")
        if reason_code:
            payload["reason_code"] = reason_code
        return payload


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
    source: str = "data_go_kr_live"
    is_offline_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        first = self.items[0] if self.items else None
        payload = {
            "status": self.status,
            "query": self.query,
            "items": self.items,
            "message": self.message,
            "source": self.source,
            "is_offline_fallback": self.is_offline_fallback,
            "portal": "data.go.kr",
            "candidate_count": len(self.items),
            "first_candidate": {key: first.get(key) for key in ("title", "provider", "format", "url")} if isinstance(first, dict) else None,
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


_OFFLINE_FALLBACK_SEARCH_TOPICS: tuple[dict[str, Any], ...] = (
    {
        "title": "서울특별시 부동산 실거래가 정보",
        "description": "서울 지역 부동산 매매 실거래가 확인을 위한 데모-safe data.go.kr 후보입니다. 포털 상세 페이지에서 실제 파일/API 리소스를 확인하세요.",
        "provider": "서울특별시",
        "category": "지역개발 - 부동산",
        "url": "https://www.data.go.kr/data/15052419/fileData.do",
        "keywords": ("서울", "집값", "부동산", "실거래가", "아파트", "매매"),
        "score": 96,
        "match_reasons": ("offline_fallback", "topic:부동산,실거래가"),
    },
    {
        "title": "국토교통부 실거래가 정보",
        "description": "전국 주택/아파트 실거래가 흐름을 확인하는 데모 후보입니다. live 검색 장애 시 후보 선택 흐름을 유지하기 위한 항목입니다.",
        "provider": "국토교통부",
        "category": "지역개발 - 부동산",
        "url": "https://www.data.go.kr/data/15057511/fileData.do",
        "keywords": ("집값", "부동산", "실거래가", "아파트", "주택"),
        "score": 92,
        "match_reasons": ("offline_fallback", "topic:부동산,실거래가"),
    },
    {
        "title": "서울특별시 전월세 실거래가 정보",
        "description": "서울 전월세 실거래가 확인을 위한 데모 후보입니다. 직접 preview 가능한 리소스가 아니라 상세 확인 단계로 연결됩니다.",
        "provider": "서울특별시",
        "category": "지역개발 - 부동산",
        "url": "https://www.data.go.kr/data/15052420/fileData.do",
        "keywords": ("서울", "전월세", "부동산", "실거래가", "임대차"),
        "score": 88,
        "match_reasons": ("offline_fallback", "topic:전월세,실거래가"),
    },
    {
        "title": "한국부동산원 공동주택 가격지수",
        "description": "공동주택 가격지수 분석 흐름을 시연하기 위한 데모 후보입니다.",
        "provider": "한국부동산원",
        "category": "지역개발 - 부동산",
        "url": "https://www.data.go.kr/data/15057936/fileData.do",
        "keywords": ("집값", "부동산", "공동주택", "가격지수", "아파트"),
        "score": 82,
        "match_reasons": ("offline_fallback", "topic:부동산,가격지수"),
    },
    {
        "title": "전국개별주택가격정보표준데이터",
        "description": "개별주택가격 표준데이터 확인 흐름을 위한 데모 후보입니다.",
        "provider": "행정안전부",
        "category": "지역개발 - 부동산",
        "url": "https://www.data.go.kr/data/15004407/standard.do",
        "keywords": ("주택", "가격", "부동산", "표준데이터", "공시가격"),
        "score": 78,
        "match_reasons": ("offline_fallback", "topic:주택가격,표준데이터"),
    },
    {
        "title": "서울특별시 대기환경정보",
        "description": "서울 미세먼지/대기환경 시연용 데모 후보입니다.",
        "provider": "서울특별시",
        "category": "환경 - 대기",
        "url": "https://www.data.go.kr/data/15089266/fileData.do",
        "keywords": ("서울", "미세먼지", "대기", "환경"),
        "score": 74,
        "match_reasons": ("offline_fallback", "topic:미세먼지,대기환경"),
    },
)


def build_offline_fallback_dataset_search(keyword: str, reason_code: str, per_page: int = 10) -> DatasetSearchResult:
    """Return deterministic demo-safe search candidates for transient portal failures."""
    query = expand_public_data_keyword(keyword)
    query_tokens = set(re.findall(r"[0-9A-Za-z가-힣]+", query))
    ranked: list[dict[str, Any]] = []
    for index, template in enumerate(_OFFLINE_FALLBACK_SEARCH_TOPICS):
        item_keywords = set(template["keywords"])
        overlap = len(query_tokens & item_keywords)
        score = int(template["score"]) + overlap * 20 - index
        ranked.append({
            "id": None,
            "title": template["title"],
            "description": template["description"],
            "provider": template["provider"],
            "category": template["category"],
            "format": "FILE",
            "updated_at": None,
            "url": template["url"],
            "detail_url": template["url"],
            "data_type": "FILE",
            "keywords": list(template["keywords"]),
            "score": score,
            "match_reasons": list(template["match_reasons"]),
            "is_offline_fallback": True,
        })
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return DatasetSearchResult(
        status="success",
        query=query,
        items=ranked[: max(1, per_page)],
        message="data.go.kr live 검색이 불안정해 데모 후보로 계속 진행합니다.",
        reason_code=reason_code,
        source="offline_fallback",
        is_offline_fallback=True,
    )


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


_CURRENT_DETAIL_PATH_RE = re.compile(r"^/data/\d+/(?:fileData|apiData|standardData|linkedData)\.do$", re.IGNORECASE)
_PORTAL_PAGE_REASON_CODE = "RESOURCE_UNSUPPORTED_PORTAL_PAGE"


def is_data_go_kr_portal_page_url(url: str) -> bool:
    """Return True when a URL is a data.go.kr page, not a direct data resource."""
    parsed = urlsplit(_clean_string(url))
    host = (parsed.hostname or "").lower()
    if host not in {"www.data.go.kr", "data.go.kr"}:
        return False
    path = (parsed.path or "/").lower()
    if path in {"", "/"}:
        return True
    portal_markers = (
        "/data/",
        "/tcs/dss/",
        "/catalog/",
        "/ugs/",
        "/bbs/",
        "/cmm/",
        "/policy",
        "/info",
    )
    return path.endswith(".do") or any(path.startswith(marker) for marker in portal_markers)


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
        m = re.search(rf"{re.escape(label)}\s*[:：]?\s*([^|·•\n]+?)(?=\s+(?:제공기관|기관명|분류체계|분류|수정일|갱신일|등록일|파일데이터명|오픈API명|공공데이터명|확장자|제공형태|파일형식|포맷|키워드|다운로드)|$)", text)
        if m:
            return m.group(1).strip(" -_/|·•")
    return ""

_GENERIC_TITLES = {"데이터찾기", "목록", "상세보기", "다운로드", "활용신청", "로그인", "회원가입", "공유", "인쇄", "이전", "다음", "더보기", "미리보기"}
_VISUAL_FORMATS = {"FILE", "CSV", "TSV", "JSON", "XLSX", "XLS", "XML"}

REAL_ESTATE_SYNONYMS = ("부동산", "실거래가", "아파트", "전월세", "주택", "주택가격")
REGION_ONLY_TOKENS = {"서울", "서울시", "서울특별시", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "경기도", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"}

def expand_public_data_keyword(keyword: str) -> str:
    """Apply small deterministic public-data search synonyms used when AI keywords are unavailable."""
    text = re.sub(r"\s+", " ", _clean_string(keyword))
    if not text:
        return ""
    if "집값" in text:
        additions = [term for term in ("부동산", "실거래가", "아파트", "전월세", "주택 가격") if term not in text]
        return f"{text} {' '.join(additions[:2])}".strip()
    return text

def _query_tokens(query: str) -> list[str]:
    expanded = expand_public_data_keyword(query)
    return [t.lower() for t in re.split(r"\s+", expanded) if len(t.strip()) > 1]

def _is_generic_title(title: str) -> bool:
    cleaned = re.sub(r"\s+", "", _clean_string(title))
    return not cleaned or len(cleaned) < 3 or cleaned in _GENERIC_TITLES

def _candidate_score(item: dict[str, Any], tokens: list[str]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    fields = {"title": 12, "provider": 5, "category": 4, "description": 2}
    for field, weight in fields.items():
        text = _clean_string(item.get(field)).lower()
        matches = [token for token in tokens if token in text]
        if matches:
            score += weight * len(matches)
            reasons.append(f"{field}:{','.join(matches[:3])}")
    if _is_current_data_go_kr_detail_url(_clean_string(item.get("detail_url") or item.get("url"))):
        score += 20
        reasons.append("current_detail_url")
    fmt = _clean_string(item.get("format")).upper()
    dtype = _clean_string(item.get("data_type")).upper()
    if any(label in fmt for label in _VISUAL_FORMATS) or dtype == "FILE":
        score += 8
        reasons.append("visualizable_format")
    if dtype == "API":
        score += 3
        reasons.append("api_candidate")
    blob = " ".join(_clean_string(item.get(field)).lower() for field in ("title", "category", "description", "provider"))
    real_estate_matches = [term for term in REAL_ESTATE_SYNONYMS if term in blob]
    query_has_real_estate = any(token in {"집값", "부동산", "실거래가", "아파트", "전월세", "주택", "가격"} for token in tokens)
    if query_has_real_estate and real_estate_matches:
        score += 18 + 4 * len(real_estate_matches)
        reasons.append(f"topic:{','.join(real_estate_matches[:3])}")
    elif query_has_real_estate and tokens and all(token in REGION_ONLY_TOKENS for token in tokens if token in blob):
        score -= 10
        reasons.append("region_only_penalty")
    return score, reasons

def _dedupe_keys(item: dict[str, Any]) -> set[str]:
    keys = set()
    for value in (item.get("detail_url"), item.get("url")):
        if value:
            keys.add(f"url:{urlsplit(str(value)).path}?{urlsplit(str(value)).query}")
    title_provider = f"tp:{_clean_string(item.get('title')).lower()}|{_clean_string(item.get('provider')).lower()}"
    if title_provider != "tp:|":
        keys.add(title_provider)
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    for key in ("publicDataPk", "dataSetSn", "public_data_pk", "datasetId", "id"):
        if raw.get(key):
            keys.add(f"id:{raw[key]}")
    return keys


def parse_data_go_kr_search_html(html: str, query: str) -> DatasetSearchResult:
    root = _parse_html(html)
    candidates: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    tokens = _query_tokens(query)
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
        if not detail_url or len(text) < 8 or "selectDataSetList" in detail_url:
            continue
        title = ""
        for link in _node_links(node):
            if link["href"] == detail_url and link.get("text") and not _is_generic_title(link["text"]):
                title = link["text"]
                break
        title = title or _extract_labeled_value(text, ("파일데이터명", "오픈API명", "공공데이터명", "서비스명")) or text[:80]
        if _is_generic_title(title):
            continue
        data_type = "FILE" if "파일데이터" in text or "fileData" in detail_url else ("API" if "오픈API" in text or "apiData" in detail_url else ("STANDARD" if "standardData" in detail_url else "UNKNOWN"))
        fmt = _extract_labeled_value(text, ("확장자", "파일형식", "포맷", "제공형태")) or data_type
        item = {
            "_order": len(candidates),
            "id": None,
            "title": title.strip(),
            "description": text[:500],
            "provider": _extract_labeled_value(text, ("제공기관", "기관명")),
            "category": _extract_labeled_value(text, ("분류체계", "분류")),
            "format": fmt,
            "updated_at": _extract_labeled_value(text, ("수정일", "갱신일", "등록일")) or None,
            "url": detail_url,
            "detail_url": detail_url,
            "data_type": data_type,
            "keywords": tokens,
            "raw": {"url": detail_url, "detailUrl": detail_url, "title": title, "description": text, "provider": _extract_labeled_value(text, ("제공기관", "기관명")), "format": fmt, "data_type": data_type},
        }
        score, reasons = _candidate_score(item, tokens)
        item["score"] = score
        item["match_reasons"] = reasons
        keys = _dedupe_keys(item)
        if keys & seen_keys:
            continue
        seen_keys.update(keys)
        candidates.append(item)
    candidates.sort(key=lambda item: (-int(item.get("score") or 0), int(item.get("_order") or 0)))
    for item in candidates:
        item.pop("_order", None)
    candidates = candidates[:20]
    return DatasetSearchResult(status="success", query=query, items=candidates, message="" if candidates else "검색 결과가 없거나 data.go.kr HTML 구조를 해석하지 못했습니다.")


_RESOURCE_HINT_TOKENS = ("download", "file", "csv", "json", "excel", "xls", "api", "get", "openapi", "파일", "다운로드", "미리보기")
_STATIC_EXTENSIONS = (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2")

def _extract_urls_from_text(text: str, base_url: str = DATA_GO_KR_ORIGIN) -> list[str]:
    values: list[str] = []
    for raw in re.findall(r"https?://[^\s'\")<>]+|/[A-Za-z0-9_./?=&%:-]+", text or ""):
        cleaned = raw.strip("'\") ,;")
        if cleaned.startswith("/") or cleaned.startswith("http"):
            values.append(urljoin(base_url, cleaned))
    return values

def _looks_like_resource_url(url: str, context: str = "") -> bool:
    if is_data_go_kr_portal_page_url(url):
        return False
    parsed = urlsplit(url)
    lowered = f"{parsed.path}?{parsed.query} {context}".lower()
    if parsed.scheme not in {"http", "https"}:
        return False
    if any(parsed.path.lower().endswith(ext) for ext in _STATIC_EXTENSIONS):
        return False
    if any(token in lowered for token in _RESOURCE_HINT_TOKENS):
        return True
    return any(parsed.path.lower().endswith(ext) for ext in (".csv", ".tsv", ".json", ".xls", ".xlsx", ".xml"))

def _resource_support(fmt: str, is_api: bool, url: str, context: str = "") -> dict[str, Any]:
    upper = _clean_string(fmt).upper()
    if is_data_go_kr_portal_page_url(url):
        return {"is_previewable": False, "is_visualizable": False, "unsupported_reason": "공공데이터포털 상세/목록 페이지 URL은 직접 데이터 리소스가 아닙니다. 상세 페이지에서 실제 파일/API 리소스를 선택해 주세요.", "reason_code": _PORTAL_PAGE_REASON_CODE, "requires_api_key": False}
    requires_key = bool(re.search(r"servicekey|apikey|api_key|인증키|활용신청", f"{url} {context}", re.IGNORECASE))
    is_openapi = is_api or upper in {"API", "XML"} or "openapi" in f"{url} {context}".lower()
    previewable = upper in {"CSV", "TSV", "JSON"} and not requires_key and not is_openapi
    visualizable = previewable
    reason = ""
    if is_openapi:
        reason = "OpenAPI 후보입니다. serviceKey는 frontend에 입력하지 않고 backend 환경변수로만 호출합니다."
    elif requires_key:
        reason = "API key가 필요한 리소스일 수 있어 자동 미리보기/시각화가 제한됩니다. 상세 페이지에서 확인하세요."
    elif upper in {"XLS", "XLSX"}:
        reason = "원격 Excel은 자동 분석하지 않으며 내려받은 뒤 직접 업로드하세요."
    elif upper not in {"CSV", "TSV", "JSON"}:
        reason = "CSV/TSV/JSON 리소스만 자동 미리보기/시각화를 지원합니다."
    return {"is_previewable": previewable, "is_visualizable": visualizable, "unsupported_reason": reason, "reason_code": "" if previewable else ("OPENAPI_BACKEND_REQUIRED" if is_openapi else ("RESOURCE_UNSUPPORTED_FORMAT" if reason else "")), "requires_api_key": requires_key, "is_openapi": is_openapi}

def _normalize_format_label(fmt: str) -> str:
    upper = _clean_string(fmt).upper()
    for label in ("CSV", "TSV", "JSON", "XLSX", "XLS", "XML", "API"):
        if label in upper:
            return label
    return upper or "UNKNOWN"

def _make_resource(name: str, fmt: str, url: str, description: str, is_api: bool, source_hint: str, context: str = "") -> dict[str, Any]:
    fmt = _normalize_format_label(fmt)
    support = _resource_support(fmt, is_api, url, context)
    return {
        "name": name or "리소스 후보",
        "format": fmt or "UNKNOWN",
        "url": url,
        "description": description,
        "is_downloadable": bool(url) and not is_api,
        "is_api": is_api,
        "is_previewable": support["is_previewable"],
        "is_visualizable": support["is_visualizable"],
        "unsupported_reason": support["unsupported_reason"],
        "reason_code": support.get("reason_code", ""),
        "is_openapi": support.get("is_openapi", False),
        "requires_service_key": bool(support.get("is_openapi", False)),
        "type": "openapi" if support.get("is_openapi", False) else ("api" if is_api else "file"),
        "source_hint": source_hint,
    }
def parse_data_go_kr_detail_html(html: str, detail_url: str = "") -> DatasetDetailResult:
    root = _parse_html(html)
    page_text = _node_text(root)
    declared_format = _extract_labeled_value(page_text, ("확장자", "제공형태", "파일형식", "포맷"))
    h_texts = [_node_text(n) for n in _iter_nodes(root) if n.get("tag") in {"h1", "h2", "h3"} and _node_text(n)]
    title = h_texts[0] if h_texts else _extract_labeled_value(page_text, ("파일데이터명", "오픈API명", "공공데이터명")) or "공공데이터 상세"
    resources: list[dict[str, Any]] = []
    seen: set[str] = set()

    for node in _iter_nodes(root):
        attrs = node.get("attrs", {}) if isinstance(node.get("attrs"), dict) else {}
        node_text = _node_text(node)
        attr_blob = " ".join(str(v) for v in attrs.values())
        context = f"{node_text} {attr_blob} {page_text[:300]}"
        urls: list[tuple[str, str]] = []
        href = attrs.get("href", "")
        if href and not href.lower().startswith("javascript:"):
            urls.append((urljoin(detail_url or DATA_GO_KR_ORIGIN, href), "href"))
        for key, value in attrs.items():
            if key.startswith("data-") or key in {"onclick", "value"}:
                for extracted in _extract_urls_from_text(str(value), detail_url or DATA_GO_KR_ORIGIN):
                    urls.append((extracted, key))
        if not any(token in context.lower() for token in _RESOURCE_HINT_TOKENS):
            continue
        for url, source_hint in urls:
            if sanitize_url_for_response(url) == sanitize_url_for_response(detail_url) or "recommendDataYn=Y" in url:
                continue
            if not _looks_like_resource_url(url, context):
                continue
            safe_key = sanitize_url_for_response(url)
            if safe_key in seen:
                continue
            seen.add(safe_key)
            fmt = _infer_resource_format({"url": url, "name": node_text, "description": context, "format": declared_format})
            is_api = fmt.upper() == "API" or "api" in context.lower() or "openapi" in context.lower()
            resources.append(_make_resource(node_text or attrs.get("title", "") or "리소스 후보", fmt, url, "data.go.kr 상세 페이지에서 추출한 링크입니다.", is_api, source_hint, context))

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


def _with_bounded_retry(operation, *args, **kwargs):
    """Run a portal fetch once, then retry once after a short backoff for transient timeouts/network hiccups."""
    last_exc: BaseException | None = None
    for attempt, timeout in enumerate((DATA_GO_KR_TIMEOUT_SECONDS, DATA_GO_KR_RETRY_TIMEOUT_SECONDS), start=1):
        try:
            return operation(*args, timeout=timeout, **kwargs)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            reason_code, _ = _classify_portal_exception(exc)
            if attempt >= 2 or reason_code == "DATA_PORTAL_HTTP_ERROR":
                break
            time.sleep(DATA_GO_KR_RETRY_BACKOFF_SECONDS)
    assert last_exc is not None
    raise last_exc

def _read_text_url(url: str) -> str:
    html, _status_code, _final_url = _with_bounded_retry(_read_text_url_with_status, url)
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


def _read_data_go_kr_detail_url_once(url: str, timeout: int = DATA_GO_KR_TIMEOUT_SECONDS) -> tuple[str, str]:
    safe_url = validate_data_go_kr_detail_url(url)
    req = Request(safe_url, headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": "Mozilla/5.0 Public-Data-MOTIR/1.0"})
    with urlopen(req, timeout=timeout) as response:  # noqa: S310 - URL and redirect target are constrained to data.go.kr HTTPS.
        final_url = response.geturl() if hasattr(response, "geturl") else safe_url
        validate_data_go_kr_detail_url(final_url)
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace"), final_url


def _read_data_go_kr_detail_url(url: str) -> tuple[str, str]:
    return _with_bounded_retry(_read_data_go_kr_detail_url_once, url)


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
        if url and is_data_go_kr_portal_page_url(url):
            support = _resource_support(fmt, is_api, url, description)
            is_downloadable = False
        else:
            support = _resource_support(fmt, is_api, url or "", description)
        resources.append(
            {
                "name": name,
                "format": fmt,
                "url": url,
                "description": description,
                "is_downloadable": is_downloadable and not is_data_go_kr_portal_page_url(url or ""),
                "is_api": is_api,
                "is_previewable": support["is_previewable"],
                "is_visualizable": support["is_visualizable"],
                "unsupported_reason": support["unsupported_reason"],
                "reason_code": support.get("reason_code", ""),
                "is_openapi": support.get("is_openapi", False),
                "requires_service_key": bool(support.get("is_openapi", False)),
                "type": "openapi" if support.get("is_openapi", False) else ("api" if is_api else "file"),
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
    keyword = expand_public_data_keyword(keyword)
    url = _build_data_go_kr_search_url(keyword, page=page, per_page=per_page)
    safe_url = sanitize_url_for_response(url)
    started = time.perf_counter()
    try:
        html = _read_text_url(url)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        reason_code, http_status = _classify_portal_exception(exc)
        logger.warning("data.go.kr search failed url=%s reason=%s http_status=%s elapsed_ms=%s", safe_url, reason_code, http_status, elapsed_ms)
        if reason_code in {"DATA_PORTAL_TIMEOUT", "DATA_PORTAL_NETWORK_ERROR"}:
            return build_offline_fallback_dataset_search(keyword, reason_code, per_page=per_page)
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
    if is_data_go_kr_portal_page_url(url):
        raise ValueError(f"{_PORTAL_PAGE_REASON_CODE}: 공공데이터포털 상세 페이지 URL은 직접 미리보기할 수 없습니다. 상세 페이지에서 실제 파일/API 리소스를 선택해 주세요.")
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


def _decode_public_data_bytes(raw_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8-sig", errors="replace")


def _sniff_delimiter(sample: str, fmt: str) -> str:
    if fmt == "TSV":
        return "\t"
    try:
        return csv.Sniffer().sniff(sample[:4096], delimiters=",\t;|").delimiter
    except csv.Error:
        return ","


def _extract_tabular_json(payload: Any) -> list[dict[str, Any]] | None:
    if isinstance(payload, list) and all(isinstance(row, dict) for row in payload):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "items", "records", "result", "results"):
            value = payload.get(key)
            if isinstance(value, list) and all(isinstance(row, dict) for row in value):
                return value
        response = payload.get("response")
        if isinstance(response, dict):
            body = response.get("body")
            nested = _extract_tabular_json(body if body is not None else response)
            if nested is not None:
                return nested
    return None


def normalize_resource_preview(resource: dict[str, Any], raw_bytes: bytes, fmt: str, max_rows: int, truncated: bool) -> dict[str, Any]:
    """Parse a bounded byte sample into a frontend-friendly preview payload."""
    text = _decode_public_data_bytes(raw_bytes)
    row_limit = max(1, min(max_rows, RESOURCE_PREVIEW_MAX_ROWS))

    if fmt in {"CSV", "TSV"}:
        delimiter = _sniff_delimiter(text, fmt)
        sample = text.splitlines()[: row_limit + 2]
        rows = list(csv.reader(sample, delimiter=delimiter))
        if not rows or not any(any(str(cell).strip() for cell in row) for row in rows):
            raise ValueError("RESOURCE_EMPTY: 미리보기할 행을 찾지 못했습니다.")
        headers = [str(value) for value in rows[0]]
        body_rows = [[str(value) for value in row] for row in rows[1 : row_limit + 1]]
        return {"kind": "table", "headers": headers, "rows": body_rows, "truncated": truncated or len(rows) > row_limit + 1, "delimiter": delimiter, "message": f"처음 {len(body_rows)}행만 표시합니다."}

    if fmt == "JSON":
        payload = json.loads(text)
        records = _extract_tabular_json(payload)
        if records is None:
            raise ValueError("RESOURCE_JSON_NOT_TABULAR: JSON을 표 형태로 변환할 수 없습니다.")
        headers: list[str] = []
        for row in records:
            for key, value in row.items():
                if key not in headers and isinstance(value, (str, int, float, bool, type(None))):
                    headers.append(str(key))
        if not headers:
            raise ValueError("RESOURCE_JSON_NOT_TABULAR: JSON에서 표시 가능한 열을 찾지 못했습니다.")
        return {"kind": "table", "headers": headers, "rows": [[str(row.get(key, "")) for key in headers] for row in records[:row_limit]], "truncated": truncated or len(records) > row_limit, "message": f"JSON 객체 배열에서 처음 {min(len(records), row_limit)}행만 표시합니다."}

    if fmt in {"XLS", "XLSX"}:
        raise ValueError("RESOURCE_UNSUPPORTED_FORMAT: 원격 Excel 파일은 이번 단계에서 직접 파싱하지 않습니다. 파일을 내려받아 직접 업로드해 주세요.")
    raise ValueError("RESOURCE_UNSUPPORTED_FORMAT: CSV/TSV/JSON 리소스만 미리보기를 지원합니다.")

def fetch_resource_preview(resource: dict[str, Any], max_bytes: int = RESOURCE_PREVIEW_MAX_BYTES, max_rows: int = RESOURCE_PREVIEW_DEFAULT_ROWS) -> ResourcePreviewResult:
    """Fetch a small bounded preview for a validated external CSV/TSV/JSON resource."""
    source = resource if isinstance(resource, dict) else {}
    safe_resource = _safe_resource_payload(source)
    url = validate_resource_url(source)
    request = Request(url, headers={"Accept": "text/csv, application/json, text/tab-separated-values, */*", "User-Agent": "Public-Data-MOTIR/1.0"})

    try:
        with urlopen(request, timeout=RESOURCE_PREVIEW_TIMEOUT_SECONDS) as response:  # noqa: S310 - URL is validated against internal hosts and unsafe schemes.
            final_url = response.geturl() if hasattr(response, "geturl") else url
            try:
                validate_resource_url({"url": final_url})
            except ValueError as exc:
                return ResourcePreviewResult(status="error", resource=safe_resource, preview=None, metadata={"reason_code": "RESOURCE_REDIRECT_BLOCKED", "source_url": sanitize_url_for_response(final_url)}, message=str(exc))
            content_type = response.headers.get("Content-Type", "") if getattr(response, "headers", None) else ""
            fmt = infer_resource_format({**source, "url": final_url}, content_type)
            raw_bytes, truncated = _read_limited_response(response, max_bytes)
    except ValueError:
        raise
    except HTTPError as exc:
        return ResourcePreviewResult(status="error", resource=safe_resource, preview=None, metadata={"reason_code": "RESOURCE_FETCH_HTTP_ERROR", "http_status": exc.code}, message="resource URL 호출이 HTTP 오류를 반환했습니다.")
    except TimeoutError:
        return ResourcePreviewResult(status="error", resource=safe_resource, preview=None, metadata={"reason_code": "RESOURCE_FETCH_TIMEOUT"}, message="resource URL 호출 시간이 초과되었습니다.")
    except (URLError, OSError):
        return ResourcePreviewResult(status="error", resource=safe_resource, preview=None, metadata={"reason_code": "RESOURCE_FETCH_NETWORK_ERROR"}, message="resource URL 호출에 실패했습니다. URL, timeout 또는 접근 권한을 확인해 주세요.")

    try:
        preview = normalize_resource_preview(source, raw_bytes, fmt, max_rows, truncated)
    except (ValueError, json.JSONDecodeError, csv.Error, UnicodeError) as exc:
        message = str(exc)
        reason = message.split(":", 1)[0] if message.startswith("RESOURCE_") else "RESOURCE_PARSE_ERROR"
        return ResourcePreviewResult(status="error", resource=safe_resource, preview=None, metadata={"content_type": content_type, "bytes_read": len(raw_bytes), "source_url": sanitize_url_for_response(final_url), "reason_code": reason}, message=message.split(":", 1)[-1].strip() if message.startswith("RESOURCE_") else message)

    return ResourcePreviewResult(
        status="success",
        resource=safe_resource,
        preview=preview,
        metadata={"content_type": content_type, "bytes_read": len(raw_bytes), "source_url": sanitize_url_for_response(final_url)},
        message="",
    )
