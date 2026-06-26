import json
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

import backend.app as app_module
import backend.public_data_portal as portal
from backend.app import app


client = TestClient(app)

SEARCH_HTML = """
<html><body>
<nav>로그인 사이트맵 데이터찾기</nav>
<div class="result-list">
  <div class="result-card">
    <a href="/tcs/dss/selectDataSetList.do">데이터찾기</a>
    <p>navigation generic</p>
  </div>
  <div class="result-card">
    <a href="/tcs/dss/selectApiDataDetailView.do?publicDataPk=15000001">서울시 부동산 실거래가 정보</a>
    <span>서울특별시</span><span>CSV</span><p>서울 부동산 가격 거래 데이터</p>
  </div>
</div>
</body></html>
"""

DETAIL_HTML = """
<html><body>
<h1>서울시 부동산 실거래가 정보</h1>
<span>제공기관 서울특별시</span><span>CSV</span>
<a href="https://example.com/data.csv?serviceKey=abc">CSV 다운로드</a>
<button onclick="location.href='https://example.com/from-onclick.json'">JSON API</button>
<div data-url="https://example.com/from-data.tsv" data-format="TSV">TSV 파일</div>
</body></html>
"""

CSV_BYTES = b"region,count\nSeoul,10\nBusan,7\n"
CP949_BYTES = "지역,건수\n서울,10\n부산,7\n".encode("cp949")
NESTED_JSON = json.dumps({"response": {"body": {"items": [{"region": "Seoul", "count": 10}, {"region": "Busan", "count": 7}]}}}).encode()
NON_TABULAR_JSON = json.dumps({"response": {"body": {"total": 2}}}).encode()


class FakeHeaders(dict):
    def get_content_charset(self):
        return self.get("charset")


class FakeResponse:
    def __init__(self, body, url="https://example.com/data.csv", content_type="text/csv", status=200):
        self.body = body
        self.url = url
        self.status = status
        self.code = status
        self.headers = FakeHeaders({"Content-Type": content_type})

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        if args:
            return self.body[: args[0]]
        return self.body

    def geturl(self):
        return self.url


def fake_urlopen_factory(routes):
    def fake_urlopen(request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        for key, response in routes.items():
            if key in url:
                if isinstance(response, Exception):
                    raise response
                return response
        return FakeResponse(CSV_BYTES, url=url, content_type="text/csv")
    return fake_urlopen


def patch_urlopen(monkeypatch, routes):
    fake = fake_urlopen_factory(routes)
    monkeypatch.setattr(portal, "urlopen", fake)
    monkeypatch.setattr(app_module, "urlopen", fake)


def test_offline_search_filters_generic_and_scores(monkeypatch):
    patch_urlopen(monkeypatch, {"selectDataSetList": FakeResponse(SEARCH_HTML.encode(), url="https://www.data.go.kr/tcs/dss/selectDataSetList.do", content_type="text/html")})
    response = client.post("/api/datasets/search", json={"keyword": "서울 부동산 가격", "page": 1, "per_page": 10})
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    assert all(item["title"] != "데이터찾기" for item in payload["items"])
    assert payload["items"][0]["score"] > 0
    assert payload["items"][0]["match_reasons"]


def test_offline_detail_extracts_href_onclick_and_data_urls(monkeypatch):
    patch_urlopen(monkeypatch, {"selectApiDataDetailView": FakeResponse(DETAIL_HTML.encode(), url="https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do?publicDataPk=15000001", content_type="text/html")})
    response = client.post("/api/datasets/detail", json={"url": "https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do?publicDataPk=15000001"})
    assert response.status_code == 200
    urls = [item.get("url", "") for item in response.json()["resources"]]
    assert any("data.csv" in url for url in urls)
    assert any("from-onclick.json" in url for url in urls)
    assert any("from-data.tsv" in url for url in urls)


@pytest.mark.parametrize("url,body,ctype,fmt", [
    ("https://example.com/data.csv?serviceKey=abc", CSV_BYTES, "text/csv", "CSV"),
    ("https://example.com/cp949.csv", CP949_BYTES, "text/csv", "CSV"),
    ("https://example.com/nested.json", NESTED_JSON, "application/json", "JSON"),
])
def test_resource_preview_success_offline(monkeypatch, url, body, ctype, fmt):
    patch_urlopen(monkeypatch, {url: FakeResponse(body, url=url, content_type=ctype)})
    response = client.post("/api/datasets/resource/preview", json={"resource": {"name": "r", "format": fmt, "url": url}, "max_rows": 5})
    assert response.status_code == 200
    payload = response.json()
    assert payload["preview"]["kind"] == "table"
    assert payload["metadata"]["bytes_read"] > 0
    assert "abc" not in payload["metadata"].get("source_url", "")
    if "serviceKey" in url:
        assert "REDACTED" in payload["metadata"]["source_url"]


def test_resource_preview_non_tabular_json_reason(monkeypatch):
    url = "https://example.com/not-table.json"
    patch_urlopen(monkeypatch, {url: FakeResponse(NON_TABULAR_JSON, url=url, content_type="application/json")})
    response = client.post("/api/datasets/resource/preview", json={"resource": {"format": "JSON", "url": url}})
    assert response.status_code == 502
    assert response.json()["detail"]["reason_code"] == "RESOURCE_JSON_NOT_TABULAR"


def test_resource_visualize_csv_and_nested_json(monkeypatch):
    for url, body, fmt, ctype in [("https://example.com/data.csv", CSV_BYTES, "CSV", "text/csv"), ("https://example.com/data.json", NESTED_JSON, "JSON", "application/json")]:
        patch_urlopen(monkeypatch, {url: FakeResponse(body, url=url, content_type=ctype)})
        response = client.post("/api/datasets/resource/visualize", json={"resource": {"format": fmt, "url": url}, "query": "지역", "core_keyword": "지역"})
        assert response.status_code == 200
        assert response.json()["metadata"]["resource_format"] == fmt


def test_resource_visualize_unsupported_format_reason(monkeypatch):
    url = "https://example.com/file.xlsx"
    patch_urlopen(monkeypatch, {url: FakeResponse(b"excel", url=url, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    response = client.post("/api/datasets/resource/visualize", json={"resource": {"format": "XLSX", "url": url}})
    assert response.status_code == 422
    assert response.json()["detail"]["reason_code"] == "RESOURCE_UNSUPPORTED_FORMAT"


def test_resource_security_errors(monkeypatch):
    blocked = client.post("/api/datasets/resource/preview", json={"resource": {"url": "http://127.0.0.1/data.csv", "format": "CSV"}})
    assert blocked.status_code == 400

    url = "https://example.com/redirect.csv"
    patch_urlopen(monkeypatch, {url: FakeResponse(CSV_BYTES, url="http://127.0.0.1/private.csv", content_type="text/csv")})
    redirected = client.post("/api/datasets/resource/preview", json={"resource": {"url": url, "format": "CSV"}})
    assert redirected.status_code == 502
    assert redirected.json()["detail"]["reason_code"] == "RESOURCE_REDIRECT_BLOCKED"

    too_large = b"a,b\n" + b"1,2\n" * ((app_module.RESOURCE_VISUALIZE_MAX_BYTES // 4) + 2)
    big_url = "https://example.com/big.csv"
    patch_urlopen(monkeypatch, {big_url: FakeResponse(too_large, url=big_url, content_type="text/csv")})
    large = client.post("/api/datasets/resource/visualize", json={"resource": {"url": big_url, "format": "CSV"}})
    assert large.status_code == 413
    assert large.json()["detail"]["reason_code"] == "RESOURCE_TOO_LARGE"
