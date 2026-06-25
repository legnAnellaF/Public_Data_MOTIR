from io import BytesIO

from fastapi.testclient import TestClient

from backend.app import app


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
    csv_content = "지역,매출,점포수\n서울,1000,10\n부산,700,7\n대구,500,5\n".encode("utf-8-sig")

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
