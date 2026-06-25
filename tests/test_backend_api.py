from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app


FIXTURES_DIR = Path(__file__).parent / "fixtures"


client = TestClient(app)


def test_health():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_keywords_without_google_api_key_returns_safe_error(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    response = client.post("/api/keywords", json={"prompt": "서울시 빈집 문제를 분석하고 싶어"})

    assert response.status_code == 503
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert "GOOGLE_API_KEY" in body["detail"]
    assert "AIza" not in str(body)


def test_visualize_csv_success():
    csv_content = (FIXTURES_DIR / "visualize_sample.csv").read_bytes()

    response = client.post(
        "/api/visualize",
        data={"query": "카페 창업 상권 분석", "core_keyword": "상권"},
        files={"file": ("sample.csv", BytesIO(csv_content), "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["chart_type"] in {"bar", "line", "pie"}
    assert body["labels"]
    assert body["datasets"]
    assert body["table_data"]["headers"]


def test_visualize_unsupported_extension_returns_400():
    response = client.post(
        "/api/visualize",
        data={"query": "카페 창업 상권 분석", "core_keyword": "상권"},
        files={"file": ("sample.txt", BytesIO(b"not,csv\n1,2\n"), "text/plain")},
    )

    assert response.status_code == 400
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert "지원하지 않는 파일 형식" in body["message"]


def test_visualize_empty_file_returns_safe_error():
    response = client.post(
        "/api/visualize",
        data={"query": "카페 창업 상권 분석", "core_keyword": "상권"},
        files={"file": ("empty.csv", BytesIO(b""), "text/csv")},
    )

    assert response.status_code == 422
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert "시각화 가능한 데이터" in body["message"]


def test_visualize_non_numeric_csv_returns_safe_error():
    csv_content = "지역,메모\n서울,좋음\n부산,보통\n".encode("utf-8-sig")

    response = client.post(
        "/api/visualize",
        data={"query": "카페 창업 상권 분석", "core_keyword": "상권"},
        files={"file": ("text_only.csv", BytesIO(csv_content), "text/csv")},
    )

    assert response.status_code == 422
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert "시각화 가능한 데이터" in body["message"]


def test_dataset_search_empty_keyword_returns_400():
    response = client.post("/api/datasets/search", json={"keyword": "   "})

    assert response.status_code == 400
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert "keyword" in body["message"]


def test_dataset_search_without_api_key_returns_safe_error(monkeypatch):
    monkeypatch.delenv("PUBLIC_DATA_API_KEY", raising=False)

    response = client.post("/api/datasets/search", json={"keyword": "서울 빈집"})

    assert response.status_code == 503
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert body["items"] == []
    assert "PUBLIC_DATA_API_KEY" in body["message"]
    assert "secret" not in str(body).lower()


def test_normalize_public_data_portal_response_fixture():
    from backend.public_data_portal import normalize_dataset_search_response

    payload = {
        "data": [
            {
                "datasetId": "ds-1",
                "datasetName": "서울특별시 빈집 현황",
                "desc": "서울 지역 빈집 통계 데이터",
                "orgName": "서울특별시",
                "categoryName": "주택",
                "fileFormat": "CSV",
                "modifiedDate": "2025-12-31",
                "detailUrl": "https://example.test/datasets/ds-1",
            }
        ]
    }

    result = normalize_dataset_search_response(payload, "서울 빈집")

    assert result.status == "success"
    assert result.query == "서울 빈집"
    assert result.items[0]["id"] == "ds-1"
    assert result.items[0]["title"] == "서울특별시 빈집 현황"
    assert result.items[0]["provider"] == "서울특별시"
    assert result.items[0]["format"] == "CSV"
    assert result.items[0]["raw"]["datasetId"] == "ds-1"


def test_dataset_search_success_with_mocked_client(monkeypatch):
    from backend.public_data_portal import DatasetSearchResult

    def fake_fetch(keyword, page=1, per_page=10):
        assert keyword == "서울 빈집"
        assert page == 2
        assert per_page == 5
        return DatasetSearchResult(
            status="success",
            query=keyword,
            items=[{"id": "1", "title": "서울 빈집", "description": "", "provider": "서울시", "category": "", "format": "CSV", "updated_at": None, "url": None, "raw": {}}],
        )

    monkeypatch.setattr("backend.app.fetch_dataset_search", fake_fetch)

    response = client.post("/api/datasets/search", json={"keyword": "서울 빈집", "page": 2, "per_page": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["query"] == "서울 빈집"
    assert body["items"][0]["title"] == "서울 빈집"
