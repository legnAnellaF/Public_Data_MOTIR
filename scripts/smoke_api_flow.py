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


def post_json(base: str, path: str, payload: dict, timeout: int = 30) -> dict:
    url = f"{base}{path}"
    response = request_or_explain("POST", url, json=payload, timeout=timeout)
    print(f"{path} -> HTTP {response.status_code}")
    if response.status_code >= 400:
        print(response.text[:500])
        response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check Public Data MOTIR backend without external live calls by default.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", type=validate_base_url, help="Backend API base URL, e.g. http://127.0.0.1:8000")
    parser.add_argument("--live-data-go-kr", action="store_true", help="Opt in to live data.go.kr dataset search.")
    parser.add_argument("--query", default="서울 부동산 가격")
    args = parser.parse_args()
    base = args.base_url

    print(f"Backend API base URL: {base}")
    health = request_or_explain("GET", f"{base}/api/health", timeout=10)
    print(f"/api/health -> HTTP {health.status_code} {health.text[:200]}")
    health.raise_for_status()
    health_body = health.json()
    if health_body.get("status") != "ok":
        raise RuntimeError(f"/api/health returned unexpected payload: {health_body}")
    print(f"Health OK: {health_body.get('app', 'unknown app')} ({health_body.get('environment', 'unknown environment')})")

    with FIXTURE.open("rb") as fh:
        response = request_or_explain(
            "POST",
            f"{base}/api/visualize",
            files={"file": (FIXTURE.name, fh, "text/csv")},
            data={"query": args.query},
            timeout=30,
        )
    print(f"/api/visualize -> HTTP {response.status_code}")
    if response.status_code >= 400:
        print(response.text[:500])
        response.raise_for_status()
    body = response.json()
    if not body.get("datasets"):
        raise RuntimeError("visualize returned no datasets")

    if args.live_data_go_kr:
        diagnostics = get_json(base, f"/api/diagnostics/data-portal?query={requests.utils.quote(args.query)}", timeout=15)
        print(
            "diagnostics:",
            diagnostics.get("status"),
            "http_status=", diagnostics.get("http_status"),
            "reason_code=", diagnostics.get("reason_code"),
            "candidate_count=", diagnostics.get("candidate_count"),
        )
        first_diag = diagnostics.get("first_candidate") or {}
        if first_diag.get("title") or first_diag.get("url"):
            print("diagnostics first candidate:", first_diag.get("title"), first_diag.get("url"))

        search = post_json(base, "/api/datasets/search", {"keyword": args.query, "page": 1, "per_page": 10}, timeout=30)
        if not search.get("items"):
            raise RuntimeError(f"live data.go.kr search returned no candidates (reason_code={search.get('reason_code')})")
        first = search["items"][0]
        if not (first.get("url") or first.get("detail_url")):
            raise RuntimeError("first candidate has no detail URL")
        print("live candidate:", first.get("title"), first.get("url") or first.get("detail_url"), "reason_code=", search.get("reason_code"))
    else:
        print("skip live data.go.kr smoke (pass --live-data-go-kr to enable)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
