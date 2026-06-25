"""FastAPI application for the Public Data MOTIR backend API."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.data_visualizer import IntelligentVisualizerEngine
from backend.keyword_extractor import analyze_project_idea


ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx", ".xls"}
LOCALHOST_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app = FastAPI(title="Public Data MOTIR API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCALHOST_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class KeywordRequest(BaseModel):
    """Request body for keyword extraction."""

    prompt: str = Field(..., examples=["서울시 빈집 문제를 분석하고 싶어"])


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


@app.get("/api/health")
def health() -> dict[str, str]:
    """Return a lightweight API health check."""
    return {"status": "ok"}


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

        visualizer = IntelligentVisualizerEngine()
        result = visualizer.process(temp_path, query=query.strip(), core_keyword=core_keyword.strip())
        if not result:
            raise _safe_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "업로드한 파일에서 시각화 가능한 데이터를 찾지 못했습니다.",
            )
        return _to_jsonable(result)
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
