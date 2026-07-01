"""FastAPI application for the Public Data MOTIR backend API."""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.data_visualizer import IntelligentVisualizerEngine
from backend.keyword_extractor import (
    KeywordExtractionResult,
    extract_keywords_with_providers,
)
from backend.public_data_portal import (
    RESOURCE_PREVIEW_TIMEOUT_SECONDS,
    fetch_dataset_detail,
    check_data_go_kr_connectivity,
    fetch_dataset_search,
    fetch_resource_preview,
    infer_resource_format,
    normalize_dataset_detail,
    sanitize_url_for_response,
    _decode_public_data_bytes,
    _extract_tabular_json,
    validate_resource_url,
)


ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx", ".xls"}
UPLOAD_VISUALIZE_MAX_BYTES = 10 * 1024 * 1024
LOCALHOST_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
APP_NAME = "Public Data MOTIR API"
APP_ENV = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "local"))


def parse_allowed_origins(value: str | None, default_origins: list[str] | None = None) -> tuple[list[str], bool]:
    """Parse comma-separated CORS origins from ALLOWED_ORIGINS.

    Returns (origins, allow_credentials). Localhost origins remain enabled by
    default. A wildcard is honored only when explicitly configured and disables
    credentials because browsers reject wildcard+credentials CORS.
    """
    origins = list(default_origins or LOCALHOST_ORIGINS)
    raw_items = [item.strip() for item in (value or "").split(",") if item.strip()]

    if "*" in raw_items:
        return ["*"], False

    for origin in raw_items:
        normalized = origin.rstrip("/")
        if normalized and normalized not in origins:
            origins.append(normalized)

    return origins, True


CORS_ALLOW_ORIGINS, CORS_ALLOW_CREDENTIALS = parse_allowed_origins(os.getenv("ALLOWED_ORIGINS"))

app = FastAPI(title=APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


class KeywordRequest(BaseModel):
    """Request body for keyword extraction."""

    prompt: str = Field(..., examples=["서울시 빈집 문제를 분석하고 싶어"])


class DatasetSearchRequest(BaseModel):
    """Request body for public-data dataset search."""

    keyword: str = Field(..., examples=["서울 빈집"])
    page: int = Field(1, ge=1, le=100, examples=[1])
    per_page: int = Field(10, ge=1, le=50, examples=[10])


class DatasetResourcePreviewRequest(BaseModel):
    """Request body for selected public-data resource preview."""

    resource: dict[str, Any] = Field(..., examples=[{"name": "파일/API 이름", "format": "CSV", "url": "https://example.test/data.csv"}])
    max_rows: int = Field(10, ge=1, le=20, examples=[10])


class DatasetResourceVisualizeRequest(BaseModel):
    """Request body for explicit selected-resource visualization."""

    resource: dict[str, Any] = Field(..., examples=[{"name": "파일/API 이름", "format": "CSV", "url": "https://example.test/data.csv"}])
    query: str = Field("", examples=["사용자 프롬프트"])
    core_keyword: str = Field("", examples=["키워드"])


class DatasetOpenApiRequest(BaseModel):
    """Request body for backend-mediated data.go.kr OpenAPI preview/visualization."""

    dataset_id: str | None = Field(None, examples=["dataset-id-or-null"])
    resource: dict[str, Any] = Field(..., examples=[{"name": "OpenAPI", "format": "JSON", "url": "https://api.odcloud.kr/api/...", "type": "openapi"}])
    limit: int = Field(100, ge=1, le=100, examples=[100])
    query: str = Field("", examples=["사용자 프롬프트"])
    core_keyword: str = Field("", examples=["키워드"])

class DatasetDetailRequest(BaseModel):
    """Request body for public-data dataset detail lookup."""

    dataset_id: str | None = Field(None, examples=["dataset-id-or-null"])
    url: str | None = Field(None, examples=["https://www.data.go.kr/..."])
    raw: dict[str, Any] | None = Field(None, examples=[{}])


def _safe_error(status_code: int, message: str, detail: str | None = None, reason_code: str | None = None) -> HTTPException:
    """Create a JSON API error without exposing secrets or provider internals."""
    payload: dict[str, str] = {"status": "error", "message": message}
    if detail:
        payload["detail"] = detail
    if reason_code:
        payload["reason_code"] = reason_code
    return HTTPException(status_code=status_code, detail=payload)


def _to_jsonable(value: Any) -> Any:
    """Convert pandas/numpy scalar values returned by the visualizer into JSON-safe data."""
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            return value
    return value



RESOURCE_VISUALIZE_MAX_BYTES = 5 * 1024 * 1024
RESOURCE_VISUALIZE_SUPPORTED_FORMATS = {"CSV", "TSV", "JSON", "XLS", "XLSX"}


OPENAPI_DEFAULT_LIMIT = 100
OPENAPI_SERVICE_KEY_ENV = "DATA_GO_KR_SERVICE_KEY"


def _is_openapi_resource(resource: dict[str, Any]) -> bool:
    text = " ".join(str(resource.get(key, "")) for key in ("type", "format", "name", "description", "url")).lower()
    return bool(resource.get("is_openapi") or resource.get("is_api") or "openapi" in text or "api" in text)


def _service_key() -> str:
    return os.getenv(OPENAPI_SERVICE_KEY_ENV, "").strip()


def _is_supported_openapi_endpoint(url: str) -> bool:
    """Return whether an OpenAPI candidate URL is safe and likely auto-callable."""
    parts = urlsplit(str(url or "").strip())
    host = parts.netloc.lower()
    path = parts.path.lower()
    if not parts.scheme or not host:
        return False
    if host.endswith("data.go.kr") and ("api" in path or "openapi" in path):
        return True
    if host.endswith("odcloud.kr") and path.startswith("/api/"):
        return True
    if "servicekey" in parts.query.lower() and ("api" in path or "openapi" in path):
        return True
    return False


def _append_openapi_params(url: str, service_key: str, limit: int) -> str:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    lowered = {key.lower() for key in params}
    if "servicekey" not in lowered:
        params["serviceKey"] = service_key
    if "page" not in lowered:
        params["page"] = "1"
    if "pageNo" not in params and "pageno" not in lowered:
        params["pageNo"] = "1"
    if "perpage" not in lowered and "numofrows" not in lowered:
        params["perPage"] = str(limit)
        params["numOfRows"] = str(limit)
    if "returntype" not in lowered and "type" not in lowered:
        params["returnType"] = "json"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params, doseq=True), parts.fragment))


def _normalize_openapi_records(payload: Any) -> list[dict[str, Any]]:
    records = _extract_tabular_json(payload)
    normalized: list[dict[str, Any]] = []
    for row in records:
        if isinstance(row, dict):
            flat = {str(k): v for k, v in row.items() if isinstance(v, (str, int, float, bool, type(None)))}
            if flat:
                normalized.append(flat)
    return normalized


def _records_to_table(records: list[dict[str, Any]], limit: int) -> tuple[list[str], list[dict[str, Any]]]:
    rows = records[:limit]
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns, rows


def _fetch_openapi_rows(resource: dict[str, Any], limit: int) -> dict[str, Any]:
    if not _is_openapi_resource(resource):
        raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "OpenAPI 리소스로 표시된 후보만 backend OpenAPI 경로에서 처리합니다.", reason_code="OPENAPI_UNSUPPORTED_RESOURCE")
    url = str(resource.get("url") or "").strip()
    if not url:
        raise _safe_error(status.HTTP_400_BAD_REQUEST, "OpenAPI resource.url이 필요합니다.", reason_code="OPENAPI_URL_REQUIRED")
    if not _is_supported_openapi_endpoint(url):
        raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "이 리소스는 OpenAPI 후보로 감지되었지만 자동 호출 가능한 endpoint 형식이 아닙니다. 직접 업로드 또는 데모 흐름을 사용해 주세요.", reason_code="OPENAPI_ENDPOINT_UNSUPPORTED")
    key = _service_key()
    if not key:
        raise _safe_error(status.HTTP_503_SERVICE_UNAVAILABLE, "OpenAPI 호출에는 backend 환경변수 serviceKey가 필요합니다. 현재는 직접 업로드 또는 데모 흐름으로 진행할 수 있습니다.", OPENAPI_SERVICE_KEY_ENV, "OPENAPI_SERVICE_KEY_MISSING")
    try:
        safe_url = validate_resource_url({"url": url, "format": resource.get("format") or "JSON"})
        request_url = _append_openapi_params(safe_url, key, limit)
        req = Request(request_url, headers={"Accept": "application/json, application/xml;q=0.6, */*;q=0.2", "User-Agent": "Public-Data-MOTIR/1.0"})
        with urlopen(req, timeout=RESOURCE_PREVIEW_TIMEOUT_SECONDS) as response:  # noqa: S310 - validate_resource_url constrains unsafe hosts.
            final_url = response.geturl() if hasattr(response, "geturl") else request_url
            validate_resource_url({"url": final_url, "format": resource.get("format") or "JSON"})
            content_type = response.headers.get("Content-Type", "") if getattr(response, "headers", None) else ""
            raw = response.read(RESOURCE_VISUALIZE_MAX_BYTES + 1)
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise _safe_error(status.HTTP_403_FORBIDDEN, "공공데이터포털 활용신청 또는 인증키 확인이 필요합니다.", str(exc.code), "OPENAPI_AUTH_REQUIRED") from None
        raise _safe_error(status.HTTP_502_BAD_GATEWAY, "공공데이터포털 OpenAPI 호출이 실패했습니다. 직접 업로드 또는 오프라인 데모 흐름으로 계속할 수 있습니다.", str(exc.code), "OPENAPI_FETCH_FAILED") from None
    except (TimeoutError, URLError, OSError, ValueError):
        raise _safe_error(status.HTTP_502_BAD_GATEWAY, "공공데이터포털 OpenAPI 호출이 실패했습니다. 직접 업로드 또는 오프라인 데모 흐름으로 계속할 수 있습니다.", reason_code="OPENAPI_FETCH_FAILED") from None
    if len(raw) > RESOURCE_VISUALIZE_MAX_BYTES:
        raise _safe_error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "OpenAPI 응답이 너무 큽니다. 일부 행만 요청하거나 직접 업로드 샘플링을 사용해 주세요.", reason_code="OPENAPI_RESPONSE_TOO_LARGE")
    if "xml" in content_type.lower() or str(resource.get("format", "")).upper() == "XML":
        raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "XML OpenAPI 범용 정규화는 후속 PR에서 지원합니다. 현재는 JSON OpenAPI 또는 직접 업로드를 사용해 주세요.", reason_code="OPENAPI_XML_UNSUPPORTED")
    try:
        payload = json.loads(_decode_public_data_bytes(raw))
        records = _normalize_openapi_records(payload)
    except (json.JSONDecodeError, UnicodeError, ValueError):
        raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "OpenAPI JSON 응답을 표 형태로 변환할 수 없습니다.", reason_code="OPENAPI_PARSE_FAILED") from None
    columns, rows = _records_to_table(records, limit)
    if not rows or not columns:
        raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "OpenAPI 응답에서 미리보기 가능한 행을 찾지 못했습니다.", reason_code="OPENAPI_NO_ROWS")
    return {"status": "success", "source": "openapi", "is_sampled": True, "sample_rows": len(rows), "columns": columns, "rows": rows, "message": "OpenAPI에서 일부 행을 가져와 미리보기합니다.", "metadata": {"source": "openapi", "resource_format": resource.get("format") or "JSON", "sample_rows": len(rows), "source_url": sanitize_url_for_response(url)}}


def _openapi_rows_to_csv_bytes(columns: list[str], rows: list[dict[str, Any]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in columns})
    return out.getvalue().encode("utf-8-sig")


def _read_remote_resource_bytes(resource: dict[str, Any]) -> tuple[bytes, str, str, str, bool]:
    """Fetch an explicitly selected remote resource with bounded bytes and SSRF checks."""
    url = validate_resource_url(resource)
    request = Request(url, headers={"Accept": "text/csv, text/tab-separated-values, application/json, */*", "User-Agent": "Public-Data-MOTIR/1.0"})
    try:
        with urlopen(request, timeout=RESOURCE_PREVIEW_TIMEOUT_SECONDS) as response:  # noqa: S310 - validate_resource_url and redirect host checks protect SSRF-prone targets.
            final_url = response.geturl() if hasattr(response, "geturl") else url
            validate_resource_url({"url": final_url})
            content_type = response.headers.get("Content-Type", "") if getattr(response, "headers", None) else ""
            fmt = infer_resource_format({**resource, "url": final_url}, content_type)
            raw = response.read(RESOURCE_VISUALIZE_MAX_BYTES + 1)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("RESOURCE_"):
            reason, _, detail = msg.partition(":")
            raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, detail.strip() or "선택한 리소스를 자동 처리할 수 없습니다.", reason_code=reason) from None
        raise
    except HTTPError as exc:
        raise _safe_error(status.HTTP_502_BAD_GATEWAY, "resource URL 호출이 HTTP 오류를 반환했습니다.", str(exc.code), "RESOURCE_FETCH_HTTP_ERROR") from None
    except TimeoutError:
        raise _safe_error(status.HTTP_504_GATEWAY_TIMEOUT, "resource URL 호출 시간이 초과되었습니다.", reason_code="RESOURCE_FETCH_TIMEOUT") from None
    except (URLError, OSError):
        raise _safe_error(status.HTTP_502_BAD_GATEWAY, "resource URL 호출에 실패했습니다. URL, timeout 또는 접근 권한을 확인해 주세요.", reason_code="RESOURCE_FETCH_NETWORK_ERROR") from None

    truncated = len(raw) > RESOURCE_VISUALIZE_MAX_BYTES
    if truncated:
        raise _safe_error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "원격 리소스가 허용된 크기보다 큽니다.", f"최대 {RESOURCE_VISUALIZE_MAX_BYTES} bytes까지만 분석합니다.", "RESOURCE_TOO_LARGE")
    return raw, fmt, content_type, sanitize_url_for_response(final_url), truncated


def _json_records_to_csv_bytes(raw_bytes: bytes) -> bytes:
    payload = json.loads(_decode_public_data_bytes(raw_bytes))
    records = _extract_tabular_json(payload)
    if not records:
        raise ValueError("RESOURCE_JSON_NOT_TABULAR: JSON을 표 형태로 변환할 수 없습니다.")
    headers = []
    for row in records:
        for key in row:
            if key not in headers and isinstance(row.get(key), (str, int, float, bool, type(None))):
                headers.append(str(key))
    if not headers:
        raise ValueError("RESOURCE_JSON_NOT_TABULAR: JSON에서 CSV로 변환할 열을 찾지 못했습니다.")
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in records:
        writer.writerow({key: row.get(key, "") for key in headers})
    out.seek(0)
    return out.getvalue().encode("utf-8-sig")


def _visualize_temp_file(temp_path: str, query: str, core_keyword: str) -> dict[str, Any]:
    visualizer = IntelligentVisualizerEngine()
    result = visualizer.process(temp_path, query=query.strip(), core_keyword=core_keyword.strip())
    if not result:
        raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "업로드한 데이터에 행(Row) 정보가 없거나, 분류/비교 기준으로 삼을 만한 유효한 항목을 찾지 못해 시각화할 수 없습니다.")
    return _to_jsonable(result)

@app.get("/api/health")
def health() -> dict[str, str]:
    """Return a lightweight API health check without external network calls."""
    return {"status": "ok", "app": APP_NAME, "environment": APP_ENV}


@app.post("/api/keywords")
def extract_keywords(request: KeywordRequest) -> dict[str, Any]:
    """Extract public-data-oriented keywords from a user prompt."""
    prompt = request.prompt.strip()
    if not prompt:
        raise _safe_error(
            status.HTTP_400_BAD_REQUEST,
            "prompt는 비어 있을 수 없습니다.",
        )

    source, result, reason_codes = extract_keywords_with_providers(prompt)

    if source == "fallback" and reason_codes and reason_codes[-1] == "AI_KEYWORD_PROVIDER_UNAVAILABLE":
        raise _safe_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "키워드 추출을 사용할 수 없습니다.",
            "OPENAI_API_KEY 또는 GOOGLE_API_KEY 설정을 확인한 뒤 다시 시도해 주세요.",
        )

    if isinstance(result, KeywordExtractionResult):
        body = result.model_dump()
        return {
            "status": "success",
            "source": source,
            "topic": body["expanded_query"],
            "is_fallback": source == "fallback",
            "reason_codes": reason_codes,
            **body,
        }

    topic = getattr(result, "Topic", None)
    if not topic:
        fallback_result = KeywordExtractionResult(
            keywords=[prompt],
            expanded_query=prompt,
            fallback_reason="GEMINI_KEYWORD_API_FAILED",
        )
        return {
            "status": "success",
            "source": "fallback",
            "topic": prompt,
            "is_fallback": True,
            "reason_codes": [*reason_codes, "GEMINI_KEYWORD_API_FAILED"],
            **fallback_result.model_dump(),
        }

    keywords = [item for item in str(topic).split() if item]
    return {
        "status": "success",
        "source": "gemini",
        "topic": str(topic),
        "keywords": keywords,
        "expanded_query": str(topic),
        "intent": "public_data_search",
        "domain": "general",
        "region": "",
        "confidence": 0.7,
        "fallback_reason": "",
        "is_fallback": False,
        "reason_codes": reason_codes,
    }


@app.get("/api/diagnostics/data-portal")
def diagnose_data_portal(query: str = "서울 부동산 가격") -> dict[str, Any]:
    """Run an explicit, fixed-endpoint live data.go.kr connectivity diagnostic."""
    return check_data_go_kr_connectivity(query).to_dict()


@app.post("/api/datasets/search")
def search_datasets(request: DatasetSearchRequest) -> dict[str, Any]:
    """Search public-data dataset candidates by keyword."""
    keyword = request.keyword.strip()
    if not keyword:
        raise _safe_error(
            status.HTTP_400_BAD_REQUEST,
            "keyword는 비어 있을 수 없습니다.",
        )

    result = fetch_dataset_search(keyword, page=request.page, per_page=request.per_page)
    payload = result.to_dict()
    if result.status != "success":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=payload)

    return payload


def _looks_like_http_url(value: Any) -> bool:
    text = str(value).strip().lower() if isinstance(value, (str, int, float)) else ""
    return text.startswith("http://") or text.startswith("https://")


def _extract_dataset_identifier(request: DatasetDetailRequest) -> str:
    if isinstance(request.url, str) and request.url.strip():
        return request.url.strip()

    raw = request.raw if isinstance(request.raw, dict) else {}
    for key in ("detailUrl", "url", "link"):
        value = raw.get(key)
        if _looks_like_http_url(value):
            return str(value).strip()

    for value in raw.values():
        if _looks_like_http_url(value):
            return str(value).strip()

    if isinstance(request.dataset_id, str) and request.dataset_id.strip() and _looks_like_http_url(request.dataset_id):
        return request.dataset_id.strip()
    return ""


@app.post("/api/datasets/resource/preview")
def preview_dataset_resource(request: DatasetResourcePreviewRequest) -> dict[str, Any]:
    """Return a small, bounded preview for a user-selected resource URL."""
    resource = request.resource if isinstance(request.resource, dict) else {}
    if not resource.get("url"):
        raise _safe_error(status.HTTP_400_BAD_REQUEST, "resource.url이 필요합니다.")

    try:
        result = fetch_resource_preview(resource, max_rows=request.max_rows)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("RESOURCE_"):
            reason, _, detail = msg.partition(":")
            raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, detail.strip() or "선택한 리소스를 미리보기할 수 없습니다.", reason_code=reason) from None
        raise _safe_error(status.HTTP_400_BAD_REQUEST, str(exc)) from None

    payload = result.to_dict()
    if result.status != "success":
        code = status.HTTP_422_UNPROCESSABLE_ENTITY if payload.get("reason_code") in {"RESOURCE_UNSUPPORTED_PORTAL_PAGE", "RESOURCE_URL_NOT_DIRECT_DATA", "RESOURCE_UNSUPPORTED_FORMAT"} else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=code, detail=payload)
    return payload



@app.post("/api/datasets/resource/visualize")
def visualize_dataset_resource(request: DatasetResourceVisualizeRequest) -> dict[str, Any]:
    """Safely fetch and visualize a user-confirmed remote CSV/TSV/JSON resource."""
    resource = request.resource if isinstance(request.resource, dict) else {}
    if not resource.get("url"):
        raise _safe_error(status.HTTP_400_BAD_REQUEST, "resource.url이 필요합니다.")

    temp_path: str | None = None
    try:
        raw_bytes, fmt, content_type, source_url, _ = _read_remote_resource_bytes(resource)
        if fmt not in RESOURCE_VISUALIZE_SUPPORTED_FORMATS:
            raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "CSV/TSV/JSON/XLS/XLSX 리소스만 자동 시각화를 지원합니다.", reason_code="RESOURCE_UNSUPPORTED_FORMAT")

        suffix = ".tsv" if fmt == "TSV" else ".csv"
        if fmt == "XLSX":
            suffix = ".xlsx"
        elif fmt == "XLS":
            suffix = ".xls"
        data_bytes = raw_bytes
        if fmt == "TSV":
            text = _decode_public_data_bytes(raw_bytes)
            rows = csv.reader(text.splitlines(), delimiter="	")
            temp_text = io.StringIO(newline="")
            writer = csv.writer(temp_text)
            writer.writerows(rows)
            temp_text.seek(0)
            data_bytes = temp_text.getvalue().encode("utf-8-sig")
            suffix = ".csv"
        elif fmt == "JSON":
            try:
                data_bytes = _json_records_to_csv_bytes(raw_bytes)
            except (ValueError, json.JSONDecodeError, UnicodeError) as exc:
                msg = str(exc)
                reason = msg.split(":", 1)[0] if msg.startswith("RESOURCE_") else "RESOURCE_PARSE_ERROR"
                raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, msg.split(":", 1)[-1].strip() if msg.startswith("RESOURCE_") else msg, reason_code=reason) from None

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            temp_file.write(data_bytes)

        result = _visualize_temp_file(temp_path, request.query, request.core_keyword)
        result.setdefault("metadata", {})
        if isinstance(result["metadata"], dict):
            result["metadata"].update({"resource_format": fmt, "content_type": content_type, "bytes_read": len(raw_bytes), "source_url": source_url})
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("RESOURCE_"):
            reason, _, detail = msg.partition(":")
            raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, detail.strip() or "선택한 리소스를 시각화할 수 없습니다.", reason_code=reason) from None
        raise _safe_error(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    except Exception:
        raise _safe_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "리소스 시각화 처리 중 오류가 발생했습니다.") from None
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass



@app.post("/api/datasets/openapi/preview")
def preview_openapi_resource(request: DatasetOpenApiRequest) -> dict[str, Any]:
    """Fetch a small OpenAPI sample through the backend serviceKey boundary."""
    return _fetch_openapi_rows(request.resource if isinstance(request.resource, dict) else {}, request.limit)


@app.post("/api/datasets/openapi/visualize")
def visualize_openapi_resource(request: DatasetOpenApiRequest) -> dict[str, Any]:
    """Fetch a bounded OpenAPI sample, normalize it to CSV, then reuse the visualizer."""
    preview = _fetch_openapi_rows(request.resource if isinstance(request.resource, dict) else {}, request.limit)
    temp_path: str | None = None
    try:
        data_bytes = _openapi_rows_to_csv_bytes(preview["columns"], preview["rows"])
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
            temp_path = temp_file.name
            temp_file.write(data_bytes)
        result = _visualize_temp_file(temp_path, request.query, request.core_keyword)
        result.setdefault("metadata", {})
        if isinstance(result["metadata"], dict):
            result["metadata"].update(preview.get("metadata", {}))
            result["metadata"].update({"source": "openapi", "is_sampled": True, "sample_rows": preview.get("sample_rows", 0)})
        result["source"] = "openapi"
        result["is_sampled"] = True
        result["sample_rows"] = preview.get("sample_rows", 0)
        return result
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass

@app.post("/api/datasets/detail")
def get_dataset_detail(request: DatasetDetailRequest) -> dict[str, Any]:
    """Return normalized metadata and resource link candidates for a selected dataset."""
    identifier = _extract_dataset_identifier(request)
    if not identifier:
        raise _safe_error(
            status.HTTP_400_BAD_REQUEST,
            "dataset_id 또는 url이 필요합니다. raw에 식별 가능한 id/url이 있어도 사용할 수 있습니다.",
        )

    result = fetch_dataset_detail(identifier)
    payload = result.to_dict()
    if result.status == "success":
        return payload

    if isinstance(request.raw, dict) and request.raw:
        fallback = normalize_dataset_detail(request.raw).to_dict()
        fallback["message"] = payload.get("message") or "상세 페이지 호출에 실패해 검색 결과 metadata를 표시합니다."
        return fallback

    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=payload)


@app.post("/api/visualize")
async def visualize_data(
    file: UploadFile = File(...),
    query: str = Form(""),
    core_keyword: str = Form(""),
    is_sampled: str = Form("false"),
    sample_rows: int = Form(0),
) -> dict[str, Any]:
    """Analyze an uploaded CSV/Excel file and return chart-ready JSON data."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise _safe_error(
            status.HTTP_400_BAD_REQUEST,
            "지원하지 않는 파일 형식입니다.",
            ".csv, .xlsx, .xls 파일만 업로드할 수 있습니다.",
        )

    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            bytes_written = 0
            while chunk := await file.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > UPLOAD_VISUALIZE_MAX_BYTES:
                    raise _safe_error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "파일이 너무 큽니다. CSV는 frontend에서 일부 행만 샘플링하거나 더 작은 파일을 사용해 주세요.", f"최대 {UPLOAD_VISUALIZE_MAX_BYTES} bytes", "UPLOAD_TOO_LARGE")
                temp_file.write(chunk)

        result = _visualize_temp_file(temp_path, query, core_keyword)
        if str(is_sampled).lower() == "true":
            result["is_sampled"] = True
            result["sample_rows"] = sample_rows
            result.setdefault("metadata", {})
            if isinstance(result["metadata"], dict):
                result["metadata"].update({"source": "upload_sample", "is_sampled": True, "sample_rows": sample_rows})
        return result
    except HTTPException:
        raise
    except Exception:
        raise _safe_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "데이터 시각화 처리 중 오류가 발생했습니다.",
        ) from None
    finally:
        await file.close()
        if temp_path:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass
