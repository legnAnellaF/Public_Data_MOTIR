#!/usr/bin/env python3
"""Smoke-check local API flow. Live data.go.kr call is opt-in."""
from __future__ import annotations
import argparse, pathlib, sys, requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "visualize_sample.csv"

def post_json(base, path, payload, timeout=30):
    r = requests.post(f"{base.rstrip('/')}{path}", json=payload, timeout=timeout)
    print(path, r.status_code)
    if r.status_code >= 400:
        print(r.text[:500])
        r.raise_for_status()
    return r.json()

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--live-data-go-kr", action="store_true")
    ap.add_argument("--query", default="서울 부동산 가격")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    health = requests.get(f"{base}/api/health", timeout=10)
    print("/api/health", health.status_code, health.text[:120])
    health.raise_for_status()
    with FIXTURE.open("rb") as fh:
        r = requests.post(f"{base}/api/visualize", files={"file": (FIXTURE.name, fh, "text/csv")}, data={"query": args.query}, timeout=30)
    print("/api/visualize", r.status_code)
    if r.status_code >= 400:
        print(r.text[:500]); r.raise_for_status()
    body = r.json()
    if not body.get("datasets"):
        raise RuntimeError("visualize returned no datasets")
    if args.live_data_go_kr:
        search = post_json(base, "/api/datasets/search", {"keyword": args.query, "page": 1, "per_page": 10}, timeout=30)
        if not search.get("items"):
            raise RuntimeError("live data.go.kr search returned no candidates")
        first = search["items"][0]
        if not (first.get("url") or first.get("detail_url")):
            raise RuntimeError("first candidate has no detail URL")
        print("live candidate:", first.get("title"), first.get("url") or first.get("detail_url"))
    else:
        print("skip live data.go.kr smoke (pass --live-data-go-kr to enable)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
