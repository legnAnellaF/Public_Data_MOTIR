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
from urllib.request import Request, urlopen

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.data_visualizer import IntelligentVisualizerEngine
from backend.keyword_extractor import analyze_project_idea
from backend.public_data_portal import (
    RESOURCE_PREVIEW_TIMEOUT_SECONDS,
    fetch_dataset_detail,
    check_data_go_kr_connectivity,
    fetch_dataset_search,
    fetch_resource_preview,
    infer_resource_format,
    normalize_dataset_detail,
    sanitize_url_for_response,
    validate_resource_url,
)


ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx", ".xls"}
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

class DatasetDetailRequest(BaseModel):
    """Request body for public-data dataset detail lookup."""

    dataset_id: str | None = Field(None, examples=["dataset-id-or-null"])
    url: str | None = Field(None, examples=["https://www.data.go.kr/..."])
    raw: dict[str, Any] | None = Field(None, examples=[{}])


def _safe_error(status_code: int, message: str, detail: str | None = None) -> HTTPException:
    """Create a JSON API error without exposing secrets or provider internals."""
    payload: dict[str, str] = {"status": "error", "message": message}
    if detail:
        payload["detail"] = detail
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
RESOURCE_VISUALIZE_SUPPORTED_FORMATS = {"CSV", "TSV", "JSON"}


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
    except ValueError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError):
        raise _safe_error(status.HTTP_502_BAD_GATEWAY, "resource URL 호출에 실패했습니다. URL, timeout 또는 접근 권한을 확인해 주세요.") from None

    truncated = len(raw) > RESOURCE_VISUALIZE_MAX_BYTES
    if truncated:
        raise _safe_error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "원격 리소스가 허용된 크기보다 큽니다.", f"최대 {RESOURCE_VISUALIZE_MAX_BYTES} bytes까지만 분석합니다.")
    return raw, fmt, content_type, sanitize_url_for_response(final_url), truncated


def _json_records_to_csv_bytes(raw_bytes: bytes) -> bytes:
    payload = json.loads(raw_bytes.decode("utf-8-sig", errors="replace"))
    if isinstance(payload, dict):
        for key in ("data", "items", "records", "result", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                payload = value
                break
    if not isinstance(payload, list) or not payload or not all(isinstance(row, dict) for row in payload):
        raise ValueError("JSON을 표 형태로 변환할 수 없습니다. 객체 배열 또는 data/items/records 배열만 지원합니다.")
    headers = []
    for row in payload:
        for key in row:
            if key not in headers and isinstance(row.get(key), (str, int, float, bool, type(None))):
                headers.append(str(key))
    if not headers:
        raise ValueError("JSON에서 CSV로 변환할 열을 찾지 못했습니다.")
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in payload:
        writer.writerow({key: row.get(key, "") for key in headers})
    out.seek(0)
    return out.getvalue().encode("utf-8-sig")


def _visualize_temp_file(temp_path: str, query: str, core_keyword: str) -> dict[str, Any]:
    visualizer = IntelligentVisualizerEngine()
    result = visualizer.process(temp_path, query=query.strip(), core_keyword=core_keyword.strip())
    if not result:
        raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "업로드한 파일에서 시각화 가능한 데이터를 찾지 못했습니다.")
    return _to_jsonable(result)

@app.get("/api/health")
def health() -> dict[str, str]:
    """Return a lightweight API health check without external network calls."""
    return {"status": "ok", "app": APP_NAME, "environment": APP_ENV}


@app.post("/api/keywords")
def extract_keywords(request: KeywordRequest) -> dict[str, str]:
    """Extract public-data-oriented keywords from a user prompt."""
    prompt = request.prompt.strip()
    if not prompt:
        raise _safe_error(
            status.HTTP_400_BAD_REQUEST,
            "prompt는 비어 있을 수 없습니다.",
        )

    try:
        result = analyze_project_idea(prompt)
    except ValueError:
        raise _safe_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "키워드 추출을 사용할 수 없습니다.",
            "GOOGLE_API_KEY 설정을 확인한 뒤 다시 시도해 주세요.",
        ) from None
    except Exception:
        raise _safe_error(
            status.HTTP_502_BAD_GATEWAY,
            "키워드 추출 중 외부 AI 서비스 호출에 실패했습니다.",
            "잠시 후 다시 시도해 주세요.",
        ) from None

    topic = getattr(result, "Topic", None)
    if not topic:
        raise _safe_error(
            status.HTTP_502_BAD_GATEWAY,
            "키워드 추출 결과 형식이 올바르지 않습니다.",
        )

    return {"status": "success", "topic": str(topic)}


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
        raise _safe_error(status.HTTP_400_BAD_REQUEST, str(exc)) from None

    payload = result.to_dict()
    if result.status != "success":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=payload)
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
        if fmt in {"XLS", "XLSX"}:
            raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "원격 Excel 자동 분석은 아직 지원하지 않으며 파일 업로드를 사용하세요.")
        if fmt not in RESOURCE_VISUALIZE_SUPPORTED_FORMATS:
            raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "CSV/TSV/JSON 리소스만 자동 시각화를 지원합니다.")

        suffix = ".tsv" if fmt == "TSV" else ".csv"
        data_bytes = raw_bytes
        if fmt == "TSV":
            text = raw_bytes.decode("utf-8-sig", errors="replace")
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
                raise _safe_error(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None

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
        raise _safe_error(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    except Exception:
        raise _safe_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "리소스 시각화 처리 중 오류가 발생했습니다.") from None
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
            while chunk := await file.read(1024 * 1024):
                temp_file.write(chunk)

        return _visualize_temp_file(temp_path, query, core_keyword)
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
