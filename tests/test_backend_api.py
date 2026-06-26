from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import LOCALHOST_ORIGINS, app, parse_allowed_origins


FIXTURES_DIR = Path(__file__).parent / "fixtures"


client = TestClient(app)


def test_health_does_not_call_data_portal(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("health must not call data.go.kr")

    monkeypatch.setattr("backend.app.check_data_go_kr_connectivity", fail_if_called)

    response = client.get("/api/health")

    assert response.status_code == 200


def test_health():
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "Public Data MOTIR API"
    assert "environment" in body


def test_parse_allowed_origins_includes_localhost_and_env_origins():
    origins, allow_credentials = parse_allowed_origins("https://front.example, https://preview.example/")

    assert allow_credentials is True
    assert "http://localhost:5173" in origins
    assert "https://front.example" in origins
    assert "https://preview.example" in origins


def test_parse_allowed_origins_explicit_wildcard_disables_credentials():
    origins, allow_credentials = parse_allowed_origins("*")

    assert origins == ["*"]
    assert allow_credentials is False


def test_parse_allowed_origins_default_localhost_only():
    origins, allow_credentials = parse_allowed_origins("")

    assert origins == LOCALHOST_ORIGINS
    assert allow_credentials is True


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


def test_data_portal_diagnostics_success_with_mock(monkeypatch):
    from backend.public_data_portal import DataPortalDiagnosticResult

    def fake_check(query="서울 부동산 가격"):
        assert query == "서울 부동산 가격"
        return DataPortalDiagnosticResult(
            status="success",
            portal="data.go.kr",
            search_url="https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=서울+부동산+가격",
            http_status=200,
            elapsed_ms=12,
            candidate_count=1,
            first_candidate={"title": "서울 부동산", "provider": "서울시", "format": "CSV", "url": "https://www.data.go.kr/tcs/dss/selectFileDataDetailView.do?publicDataPk=1"},
            message="",
        )

    monkeypatch.setattr("backend.app.check_data_go_kr_connectivity", fake_check)

    response = client.get("/api/diagnostics/data-portal")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["portal"] == "data.go.kr"
    assert body["candidate_count"] == 1
    assert body["first_candidate"]["title"] == "서울 부동산"


def test_data_portal_diagnostics_network_failure_returns_safe_json(monkeypatch):
    def fail_urlopen(*args, **kwargs):
        raise OSError("network secret stack trace")

    monkeypatch.setattr("backend.public_data_portal.urlopen", fail_urlopen)

    response = client.get("/api/diagnostics/data-portal?query=서울+빈집")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["portal"] == "data.go.kr"
    assert body["candidate_count"] == 0
    assert body["reason_code"] == "DATA_PORTAL_NETWORK_ERROR"
    assert "network secret stack trace" not in str(body)


def test_dataset_search_network_failure_returns_safe_error(monkeypatch):
    def fail_urlopen(*args, **kwargs):
        raise OSError("network blocked")

    monkeypatch.setattr("backend.public_data_portal.urlopen", fail_urlopen)

    response = client.post("/api/datasets/search", json={"keyword": "서울 빈집"})

    assert response.status_code == 503
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert body["items"] == []
    assert "data.go.kr" in body["message"]
    assert body["reason_code"] == "DATA_PORTAL_NETWORK_ERROR"
    assert "network blocked" not in str(body)
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



def test_parse_data_go_kr_search_html_fixture_success():
    from backend.public_data_portal import parse_data_go_kr_search_html

    html = """
    <ul class="result-list">
      <li>
        <a href="/tcs/dss/selectFileDataDetailView.do?publicDataPk=15000001">서울특별시 부동산 실거래가 정보</a>
        <span>제공기관 서울특별시</span><span>분류체계 지역개발</span>
        <span>확장자 CSV</span><span>수정일 2026-01-02</span>
        <p>서울 부동산 가격 파일데이터입니다.</p>
      </li>
    </ul>
    """

    result = parse_data_go_kr_search_html(html, "서울 부동산 가격")

    assert result.status == "success"
    assert result.items
    assert result.items[0]["title"] == "서울특별시 부동산 실거래가 정보"
    assert result.items[0]["provider"] == "서울특별시"
    assert result.items[0]["format"] == "CSV"
    assert result.items[0]["url"].startswith("https://www.data.go.kr/")


def test_parse_data_go_kr_detail_html_fixture_success():
    from backend.public_data_portal import parse_data_go_kr_detail_html

    html = """
    <main>
      <h2>서울특별시 부동산 실거래가 정보</h2>
      <div>제공기관 서울특별시 분류체계 지역개발 확장자 CSV 수정일 2026-01-02</div>
      <a href="https://example.com/estate.csv">CSV 다운로드</a>
    </main>
    """

    result = parse_data_go_kr_detail_html(html, "https://www.data.go.kr/detail")

    assert result.status == "success"
    assert result.dataset["title"] == "서울특별시 부동산 실거래가 정보"
    assert result.resources[0]["url"] == "https://example.com/estate.csv"
    assert result.resources[0]["format"] == "CSV"


def test_parse_data_go_kr_detail_html_no_resource_fallback():
    from backend.public_data_portal import parse_data_go_kr_detail_html

    result = parse_data_go_kr_detail_html("<h2>광주 맛집 정보</h2><p>제공기관 광주광역시</p>", "https://www.data.go.kr/detail")

    assert result.status == "success"
    assert result.resources == []
    assert "직접 다운로드" in result.message


def test_dataset_detail_missing_identifier_returns_400():
    response = client.post("/api/datasets/detail", json={"raw": {}})

    assert response.status_code == 400
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert "dataset_id" in body["message"]


def test_dataset_detail_requires_detail_url_for_live_lookup():
    response = client.post("/api/datasets/detail", json={"dataset_id": "ds-1"})

    assert response.status_code == 400
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert "url" in body["message"]



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
        assert identifier == "https://www.data.go.kr/data/1/fileData.do"
        return DatasetDetailResult(
            status="success",
            dataset={"id": "ds-1", "title": "서울 빈집", "description": "", "provider": "서울시", "category": "주택", "format": "CSV", "updated_at": None, "url": "https://www.data.go.kr/data/1/fileData.do"},
            resources=[{"name": "CSV", "format": "CSV", "url": "https://example.test/file.csv", "description": "", "is_downloadable": True, "is_api": False}],
        )

    monkeypatch.setattr("backend.app.fetch_dataset_detail", fake_fetch)

    response = client.post("/api/datasets/detail", json={"dataset_id": "ds-1", "url": "https://www.data.go.kr/data/1/fileData.do"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["dataset"]["title"] == "서울 빈집"
    assert body["resources"][0]["is_downloadable"] is True



def test_dataset_detail_blocks_unsafe_detail_urls(monkeypatch):
    called = False

    def fake_urlopen(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("unsafe detail URL must not be fetched")

    monkeypatch.setattr("backend.public_data_portal.urlopen", fake_urlopen)
    for url in ("http://127.0.0.1/admin?token=SECRET", "http://169.254.169.254/latest/meta-data"):
        response = client.post("/api/datasets/detail", json={"url": url})
        assert response.status_code == 503
        body = response.json()["detail"]
        assert body["status"] == "error"
        assert "SECRET" not in str(body)
    assert called is False


def test_dataset_detail_allows_https_data_go_kr_detail_url(monkeypatch):
    from backend.public_data_portal import DatasetDetailResult

    def fake_fetch(identifier):
        assert identifier == "https://www.data.go.kr/data/123/fileData.do"
        return DatasetDetailResult(status="success", dataset={"title": "ok", "url": identifier}, resources=[])

    monkeypatch.setattr("backend.app.fetch_dataset_detail", fake_fetch)
    response = client.post("/api/datasets/detail", json={"url": "https://www.data.go.kr/data/123/fileData.do"})

    assert response.status_code == 200
    assert response.json()["dataset"]["url"] == "https://www.data.go.kr/data/123/fileData.do"


def test_dataset_detail_blocks_unsafe_redirect(monkeypatch):
    from backend.public_data_portal import fetch_dataset_detail

    monkeypatch.setattr("backend.public_data_portal._is_safe_hostname", lambda hostname: True)
    monkeypatch.setattr("backend.public_data_portal.urlopen", lambda request, timeout=0: FakePreviewResponse(b"<h2>bad</h2>", "text/html", "http://127.0.0.1/private"))

    result = fetch_dataset_detail("https://www.data.go.kr/data/123/fileData.do")

    assert result.status == "error"
    assert result.resources == []


def test_dataset_detail_prefers_request_url_over_dataset_id(monkeypatch):
    from backend.public_data_portal import DatasetDetailResult

    def fake_fetch(identifier):
        assert identifier == "https://www.data.go.kr/data/123/apiData.do"
        return DatasetDetailResult(status="success", dataset={"title": "url wins"}, resources=[])

    monkeypatch.setattr("backend.app.fetch_dataset_detail", fake_fetch)
    response = client.post("/api/datasets/detail", json={"dataset_id": "ds-1", "url": "https://www.data.go.kr/data/123/apiData.do"})

    assert response.status_code == 200
    assert response.json()["dataset"]["title"] == "url wins"


def test_parse_current_detail_links_before_shortcuts():
    from backend.public_data_portal import parse_data_go_kr_search_html

    html = """
    <ul class="result-list">
      <li class="result-item">
        <a href="/download/123">바로 다운로드</a>
        <a href="/data/123/fileData.do">서울 파일데이터</a>
        <span>제공기관 서울특별시</span><span>확장자 CSV</span>
      </li>
      <li class="result-item">
        <a href="https://www.data.go.kr/data/456/apiData.do">부산 오픈API</a>
        <a href="/preview/456">미리보기</a>
        <span>제공기관 부산광역시</span>
      </li>
    </ul>
    """

    result = parse_data_go_kr_search_html(html, "데이터")

    assert result.items[0]["url"] == "https://www.data.go.kr/data/123/fileData.do"
    assert result.items[1]["url"] == "https://www.data.go.kr/data/456/apiData.do"


def test_parse_search_does_not_treat_result_list_container_as_item():
    from backend.public_data_portal import parse_data_go_kr_search_html

    html = """
    <ul class="result-list">
      <li class="result-item">
        <a href="/data/111/fileData.do">첫 번째 데이터</a>
        <span>제공기관 첫기관</span><span>분류체계 교통</span><p>첫 설명입니다.</p>
      </li>
      <li class="result-item">
        <a href="/data/222/fileData.do">두 번째 데이터</a>
        <span>제공기관 둘기관</span><span>분류체계 보건</span><p>둘 설명입니다.</p>
      </li>
    </ul>
    """

    result = parse_data_go_kr_search_html(html, "테스트")

    assert len(result.items) == 2
    assert result.items[0]["title"] == "첫 번째 데이터"
    assert result.items[0]["provider"] == "첫기관"
    assert "두 번째 데이터" not in result.items[0]["description"]


def test_detail_extensionless_download_preserves_declared_format():
    from backend.public_data_portal import parse_data_go_kr_detail_html

    html = """
    <main>
      <h2>서울 CSV 데이터</h2>
      <div>제공기관 서울특별시 제공형태 CSV 수정일 2026-01-02</div>
      <a href="https://www.data.go.kr/download/123" title="파일 다운로드">다운로드</a>
    </main>
    """

    result = parse_data_go_kr_detail_html(html, "https://www.data.go.kr/data/123/fileData.do")

    assert result.dataset["format"] == "CSV"
    assert result.resources[0]["format"] == "CSV"


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
