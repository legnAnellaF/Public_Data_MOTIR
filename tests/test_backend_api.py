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



def test_dataset_detail_missing_identifier_returns_400():
    response = client.post("/api/datasets/detail", json={"raw": {}})

    assert response.status_code == 400
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert "dataset_id" in body["message"]


def test_dataset_detail_without_api_key_returns_safe_error(monkeypatch):
    monkeypatch.delenv("PUBLIC_DATA_API_KEY", raising=False)
    monkeypatch.setenv("PUBLIC_DATA_PORTAL_BASE_URL", "https://example.test/detail")

    response = client.post("/api/datasets/detail", json={"dataset_id": "ds-1"})

    assert response.status_code == 503
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert body["resources"] == []
    assert "PUBLIC_DATA_API_KEY" in body["message"]
    assert "secret" not in str(body).lower()


def test_dataset_detail_without_base_url_returns_safe_error(monkeypatch):
    monkeypatch.setenv("PUBLIC_DATA_API_KEY", "test-key")
    monkeypatch.delenv("PUBLIC_DATA_PORTAL_BASE_URL", raising=False)

    response = client.post("/api/datasets/detail", json={"dataset_id": "ds-1"})

    assert response.status_code == 503
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert "PUBLIC_DATA_PORTAL_BASE_URL" in body["message"]
    assert "test-key" not in str(body)


def test_normalize_dataset_detail_fixture_extracts_resources():
    from backend.public_data_portal import normalize_dataset_detail

    payload = {
        "datasetId": "ds-1",
        "datasetName": "서울특별시 빈집 현황",
        "desc": "서울 지역 빈집 통계 데이터",
        "orgName": "서울특별시",
        "categoryName": "주택",
        "fileFormat": "CSV",
        "modifiedDate": "2025-12-31",
        "detailUrl": "https://example.test/datasets/ds-1",
        "resources": [
            {
                "name": "빈집 현황 CSV",
                "downloadUrl": "https://example.test/files/vacant.csv",
                "description": "CSV 다운로드 후보",
            },
            {
                "apiName": "빈집 현황 API",
                "apiUrl": "https://example.test/openapi/vacant",
                "format": "API",
            },
        ],
    }

    result = normalize_dataset_detail(payload)

    assert result.status == "success"
    assert result.dataset["id"] == "ds-1"
    assert result.dataset["title"] == "서울특별시 빈집 현황"
    assert result.resources[0]["format"] == "CSV"
    assert result.resources[0]["is_downloadable"] is True
    assert result.resources[1]["is_api"] is True


def test_dataset_detail_success_with_mocked_client(monkeypatch):
    from backend.public_data_portal import DatasetDetailResult

    def fake_fetch(identifier):
        assert identifier == "ds-1"
        return DatasetDetailResult(
            status="success",
            dataset={"id": "ds-1", "title": "서울 빈집", "description": "", "provider": "서울시", "category": "주택", "format": "CSV", "updated_at": None, "url": "https://example.test/ds-1"},
            resources=[{"name": "CSV", "format": "CSV", "url": "https://example.test/file.csv", "description": "", "is_downloadable": True, "is_api": False}],
        )

    monkeypatch.setattr("backend.app.fetch_dataset_detail", fake_fetch)

    response = client.post("/api/datasets/detail", json={"dataset_id": "ds-1"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["dataset"]["title"] == "서울 빈집"
    assert body["resources"][0]["is_downloadable"] is True


class FakePreviewResponse:
    def __init__(self, body, content_type="text/csv", url="https://example.test/data.csv"):
        self._body = body
        self.headers = {"Content-Type": content_type}
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size=-1):
        if size is None or size < 0:
            return self._body
        return self._body[:size]

    def geturl(self):
        return self._url


def test_resource_preview_missing_url_returns_400():
    response = client.post("/api/datasets/resource/preview", json={"resource": {"name": "no-url"}})

    assert response.status_code == 400
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert "resource.url" in body["message"]


def test_resource_preview_blocks_unsafe_urls():
    unsafe_urls = [
        "file:///tmp/data.csv",
        "http://localhost/data.csv",
        "http://127.0.0.1/data.csv",
        "http://10.0.0.1/data.csv",
        "http://169.254.169.254/latest/meta-data",
    ]

    for url in unsafe_urls:
        response = client.post("/api/datasets/resource/preview", json={"resource": {"name": "unsafe", "format": "CSV", "url": url}})
        assert response.status_code == 400
        assert response.json()["detail"]["status"] == "error"


def test_resource_preview_csv_success_with_mocked_client(monkeypatch):
    def fake_urlopen(request, timeout=0):
        assert timeout > 0
        return FakePreviewResponse(b"col1,col2\na,1\nb,2\n", "text/csv", "https://example.test/data.csv?serviceKey=SECRET")

    monkeypatch.setattr("backend.public_data_portal.urlopen", fake_urlopen)
    monkeypatch.setattr("backend.public_data_portal._is_safe_hostname", lambda hostname: True)

    response = client.post(
        "/api/datasets/resource/preview",
        json={"resource": {"name": "CSV", "format": "CSV", "url": "https://example.test/data.csv?serviceKey=SECRET"}, "max_rows": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["preview"]["kind"] == "table"
    assert body["preview"]["headers"] == ["col1", "col2"]
    assert body["preview"]["rows"] == [["a", "1"], ["b", "2"]]
    assert "SECRET" not in str(body)
    assert "REDACTED" in body["metadata"]["source_url"]


def test_resource_preview_json_success_with_mocked_client(monkeypatch):
    def fake_urlopen(request, timeout=0):
        return FakePreviewResponse(b'{"a": 1, "b": [2, 3]}', "application/json", "https://example.test/data.json")

    monkeypatch.setattr("backend.public_data_portal.urlopen", fake_urlopen)
    monkeypatch.setattr("backend.public_data_portal._is_safe_hostname", lambda hostname: True)

    response = client.post(
        "/api/datasets/resource/preview",
        json={"resource": {"name": "JSON", "format": "JSON", "url": "https://example.test/data.json"}, "max_rows": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["preview"]["kind"] == "json"
    assert body["preview"]["data"]["a"] == 1


def test_resource_preview_external_failure_returns_safe_error(monkeypatch):
    from urllib.error import URLError

    def fake_urlopen(request, timeout=0):
        raise URLError("boom SECRET")

    monkeypatch.setattr("backend.public_data_portal.urlopen", fake_urlopen)
    monkeypatch.setattr("backend.public_data_portal._is_safe_hostname", lambda hostname: True)

    response = client.post(
        "/api/datasets/resource/preview",
        json={"resource": {"name": "CSV", "format": "CSV", "url": "https://example.test/data.csv?api_key=SECRET"}},
    )

    assert response.status_code == 502
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert "SECRET" not in str(body)
    assert "호출에 실패" in body["message"]


def test_resource_visualize_missing_url_returns_400():
    response = client.post("/api/datasets/resource/visualize", json={"resource": {"name": "no-url"}})

    assert response.status_code == 400
    assert "resource.url" in response.json()["detail"]["message"]


def test_resource_visualize_blocks_unsafe_urls():
    response = client.post(
        "/api/datasets/resource/visualize",
        json={"resource": {"name": "unsafe", "format": "CSV", "url": "http://127.0.0.1/data.csv"}},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["status"] == "error"


def test_resource_visualize_remote_excel_returns_safe_error(monkeypatch):
    monkeypatch.setattr("backend.app.urlopen", lambda request, timeout=0: FakePreviewResponse(b"excel", "application/vnd.ms-excel", "https://example.test/data.xlsx"))
    monkeypatch.setattr("backend.public_data_portal._is_safe_hostname", lambda hostname: True)

    response = client.post(
        "/api/datasets/resource/visualize",
        json={"resource": {"name": "Excel", "format": "XLSX", "url": "https://example.test/data.xlsx"}},
    )

    assert response.status_code == 422
    assert "원격 Excel" in response.json()["detail"]["message"]


def test_resource_visualize_csv_success_with_mocked_client(monkeypatch):
    csv_body = (FIXTURES_DIR / "visualize_sample.csv").read_bytes()

    def fake_urlopen(request, timeout=0):
        assert timeout > 0
        return FakePreviewResponse(csv_body, "text/csv", "https://example.test/data.csv?serviceKey=SECRET")

    monkeypatch.setattr("backend.app.urlopen", fake_urlopen)
    monkeypatch.setattr("backend.public_data_portal._is_safe_hostname", lambda hostname: True)

    response = client.post(
        "/api/datasets/resource/visualize",
        json={"resource": {"name": "CSV", "format": "CSV", "url": "https://example.test/data.csv?serviceKey=SECRET"}, "query": "카페", "core_keyword": "상권"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["labels"]
    assert body["datasets"]
    assert body["metadata"]["bytes_read"] == len(csv_body)
    assert "SECRET" not in str(body)


def test_resource_visualize_json_success_with_mocked_client(monkeypatch):
    json_body = b'[{"region":"A","sales":10},{"region":"B","sales":20}]'

    monkeypatch.setattr("backend.app.urlopen", lambda request, timeout=0: FakePreviewResponse(json_body, "application/json", "https://example.test/data.json"))
    monkeypatch.setattr("backend.public_data_portal._is_safe_hostname", lambda hostname: True)

    response = client.post(
        "/api/datasets/resource/visualize",
        json={"resource": {"name": "JSON", "format": "JSON", "url": "https://example.test/data.json"}},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_resource_visualize_external_failure_returns_safe_error(monkeypatch):
    from urllib.error import URLError

    monkeypatch.setattr("backend.app.urlopen", lambda request, timeout=0: (_ for _ in ()).throw(URLError("boom SECRET")))
    monkeypatch.setattr("backend.public_data_portal._is_safe_hostname", lambda hostname: True)

    response = client.post(
        "/api/datasets/resource/visualize",
        json={"resource": {"name": "CSV", "format": "CSV", "url": "https://example.test/data.csv?api_key=SECRET"}},
    )

    assert response.status_code == 502
    body = response.json()["detail"]
    assert "SECRET" not in str(body)
    assert "호출에 실패" in body["message"]


def test_resource_visualize_temp_file_cleanup(monkeypatch):
    csv_body = (FIXTURES_DIR / "visualize_sample.csv").read_bytes()
    created_paths = []
    import backend.app as app_module
    original_named_temporary_file = app_module.tempfile.NamedTemporaryFile

    def tracking_named_temporary_file(*args, **kwargs):
        handle = original_named_temporary_file(*args, **kwargs)
        created_paths.append(handle.name)
        return handle

    monkeypatch.setattr("backend.app.urlopen", lambda request, timeout=0: FakePreviewResponse(csv_body, "text/csv", "https://example.test/data.csv"))
    monkeypatch.setattr("backend.public_data_portal._is_safe_hostname", lambda hostname: True)
    monkeypatch.setattr("backend.app.tempfile.NamedTemporaryFile", tracking_named_temporary_file)

    response = client.post(
        "/api/datasets/resource/visualize",
        json={"resource": {"name": "CSV", "format": "CSV", "url": "https://example.test/data.csv"}},
    )

    assert response.status_code == 200
    assert created_paths
    assert all(not Path(path).exists() for path in created_paths)
