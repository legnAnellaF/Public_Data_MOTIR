#!/usr/bin/env python3
"""Smoke-check local API flow. Live data.go.kr call is opt-in."""
from __future__ import annotations

import argparse
import pathlib
import sys
from urllib.parse import urlparse

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "visualize_sample.csv"


def validate_base_url(value: str) -> str:
    base = (value or "").strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError(
            "--base-url must be an absolute http(s) URL, for example http://127.0.0.1:8000"
        )
    return base


def request_or_explain(method: str, url: str, **kwargs) -> requests.Response:
    try:
        return requests.request(method, url, **kwargs)
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Cannot connect to backend API at {url}. Check --base-url, backend deployment status, and CORS/reverse-proxy routing. Original error: {exc}"
        ) from exc


def get_json(base: str, path: str, timeout: int = 30) -> dict:
    url = f"{base}{path}"
    response = request_or_explain("GET", url, timeout=timeout)
    print(f"{path} -> HTTP {response.status_code}")
    if response.status_code >= 400:
        print(response.text[:500])
        response.raise_for_status()
    return response.json()


def post_json_response(base: str, path: str, payload: dict, timeout: int = 30) -> requests.Response:
    url = f"{base}{path}"
    response = request_or_explain("POST", url, json=payload, timeout=timeout)
    print(f"{path} -> HTTP {response.status_code}")
    return response

def post_json(base: str, path: str, payload: dict, timeout: int = 30) -> dict:
    response = post_json_response(base, path, payload, timeout=timeout)
    if response.status_code >= 400:
        print(response.text[:500])
        response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check Public Data MOTIR backend without external live calls by default.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", type=validate_base_url, help="Backend API base URL, e.g. http://127.0.0.1:8000")
    parser.add_argument("--live-data-go-kr", action="store_true", help="Opt in to live data.go.kr dataset search.")
    parser.add_argument("--query", action="append", default=[], help="Query for keyword/live checks. Can be repeated.")
    args = parser.parse_args()
    base = args.base_url
    queries = args.query or ["서울 부동산 가격"]
    primary_query = queries[0]
    summary: list[tuple[str, str, str]] = []

    print(f"Backend API base URL: {base}")
    health = request_or_explain("GET", f"{base}/api/health", timeout=10)
    print(f"/api/health -> HTTP {health.status_code} {health.text[:200]}")
    health.raise_for_status()
    health_body = health.json()
    if health_body.get("status") != "ok":
        raise RuntimeError(f"/api/health returned unexpected payload: {health_body}")
    print(f"Health OK: {health_body.get('app', 'unknown app')} ({health_body.get('environment', 'unknown environment')})")
    summary.append(("PASS", "health", "/api/health OK"))

    with FIXTURE.open("rb") as fh:
        response = request_or_explain(
            "POST",
            f"{base}/api/visualize",
            files={"file": (FIXTURE.name, fh, "text/csv")},
            data={"query": primary_query},
            timeout=30,
        )
    print(f"/api/visualize -> HTTP {response.status_code}")
    if response.status_code >= 400:
        print(response.text[:500])
        response.raise_for_status()
    body = response.json()
    if not body.get("datasets"):
        raise RuntimeError("visualize returned no datasets")
    summary.append(("PASS", "local visualize", "/api/visualize returned datasets"))

    keyword_response = post_json_response(base, "/api/keywords", {"prompt": primary_query}, timeout=20)
    if keyword_response.status_code == 503:
        print("/api/keywords -> 503 (frontend fallback expected when GOOGLE_API_KEY is not configured)")
        summary.append(("WARN", "keyword unavailable", "frontend fallback expected"))
    elif keyword_response.status_code >= 500:
        print(keyword_response.text[:500])
        keyword_response.raise_for_status()
    elif keyword_response.status_code >= 400:
        print(f"/api/keywords returned non-fatal client error: {keyword_response.text[:300]}")
    else:
        print("/api/keywords OK")
        summary.append(("PASS", "keyword", "/api/keywords OK"))

    if args.live_data_go_kr:
        external_failure = False
        for query in queries:
            print(f"\nLive data.go.kr query: {query}")
            try:
                diagnostics = get_json(base, f"/api/diagnostics/data-portal?query={requests.utils.quote(query)}", timeout=15)
                print(
                    "diagnostics:",
                    diagnostics.get("status"),
                    "http_status=", diagnostics.get("http_status"),
                    "reason_code=", diagnostics.get("reason_code"),
                    "candidate_count=", diagnostics.get("candidate_count"),
                )
                if diagnostics.get("status") != "success":
                    reason = diagnostics.get("reason_code") or "DATA_PORTAL_DIAGNOSTIC_FAILED"
                    external_failure = reason in {"DATA_PORTAL_NETWORK_ERROR", "DATA_PORTAL_TIMEOUT", "DATA_PORTAL_HTTP_ERROR"}
                    summary.append(("WARN" if external_failure else "FAIL", f"live diagnostics {query}", reason))
                    continue

                search = post_json(base, "/api/datasets/search", {"keyword": query, "page": 1, "per_page": 10}, timeout=30)
                items = search.get("items") or []
                print(f"search candidates={len(items)} reason_code={search.get('reason_code')}")
                if not items:
                    summary.append(("FAIL", f"live search {query}", f"no candidates reason_code={search.get('reason_code')}"))
                    continue
                candidates = [item for item in items[:5] if item.get("url") or item.get("detail_url")]
                if not candidates:
                    summary.append(("FAIL", f"live detail {query}", "top candidates have no detail URL"))
                    continue
                first = candidates[0]
                detail_url = first.get("url") or first.get("detail_url")
                print("live candidate:", first.get("title"), detail_url)
                detail = post_json(base, "/api/datasets/detail", {"dataset_id": first.get("id"), "url": detail_url, "raw": first.get("raw") or first}, timeout=30)
                resources = detail.get("resources") or []
                supported = [r for r in resources if r.get("is_previewable") or r.get("is_visualizable")]
                print(f"detail resources={len(resources)} previewable_or_visualizable={len(supported)}")
                if not supported:
                    summary.append(("WARN", f"live resource {query}", "detail succeeded but no previewable/visualizable resource; treated as skip"))
                    continue
                selected = supported[0]
                preview_resp = post_json_response(base, "/api/datasets/resource/preview", {"resource": selected, "max_rows": 5}, timeout=20)
                preview_json = preview_resp.json() if preview_resp.content else {}
                reason = preview_json.get("reason_code") or (preview_json.get("detail") or {}).get("reason_code")
                print("preview status=", preview_resp.status_code, "reason_code=", reason)
                if preview_resp.status_code >= 400:
                    summary.append(("WARN", f"live preview {query}", f"preview unavailable reason_code={reason}"))
                    continue
                if selected.get("is_visualizable"):
                    viz_resp = post_json_response(base, "/api/datasets/resource/visualize", {"resource": selected, "query": query, "core_keyword": query}, timeout=40)
                    viz_json = viz_resp.json() if viz_resp.content else {}
                    reason = viz_json.get("reason_code") or (viz_json.get("detail") or {}).get("reason_code")
                    print("visualize status=", viz_resp.status_code, "reason_code=", reason)
                    if viz_resp.status_code >= 400:
                        summary.append(("FAIL", f"live visualize {query}", f"reason_code={reason}"))
                    else:
                        summary.append(("PASS", f"live flow {query}", "diagnostics/search/detail/preview/visualize checked"))
                else:
                    summary.append(("WARN", f"live visualize {query}", "preview passed but resource is not visualizable; treated as skip"))
            except RuntimeError as exc:
                text = str(exc)
                is_external = "Cannot connect" in text or "timed out" in text.lower()
                summary.append(("WARN" if is_external else "FAIL", f"live flow {query}", "external connectivity issue" if is_external else text[:160]))
        if external_failure:
            print("Live failures look like external connectivity/WAF issues, not necessarily code failures.")
    else:
        print("skip live data.go.kr smoke (pass --live-data-go-kr to enable)")
        summary.append(("SKIP", "live data.go.kr", "explicit --live-data-go-kr not provided"))

    print("\n검증 요약")
    for status_label, name, message in summary:
        print(f"{status_label} {name}: {message}")
    if any(item[0] == "FAIL" for item in summary):
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
