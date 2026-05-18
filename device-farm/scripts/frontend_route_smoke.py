#!/usr/bin/env python3
"""Smoke test the built frontend routes and lazy-loaded assets.

Usage:
  python3 device-farm/scripts/frontend_route_smoke.py
  python3 device-farm/scripts/frontend_route_smoke.py --skip-build
"""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import subprocess
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"
DEFAULT_ROUTES = [
    "/",
    "/login",
    "/devices",
    "/devices/regression-check",
    "/screen?deviceId=regression-check",
    "/scripts",
    "/monitoring",
    "/reports",
    "/reports/trend",
    "/parallel",
    "/admin/users",
    "/alerts",
]


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value for key, value in attrs if value}
        for key in ("src", "href"):
            value = attr_map.get(key)
            if value and value.startswith("/assets/"):
                self.assets.append(value)


def run(cmd: list[str], cwd: Path) -> None:
    print(f"+ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def request(url: str, timeout: float = 5.0, method: str = "GET") -> tuple[int, str, bytes]:
    req = Request(url, method=method)
    with urlopen(req, timeout=timeout) as response:
        return response.status, response.headers.get("content-type", ""), response.read()


def wait_for_server(
    base_url: str,
    timeout_seconds: float,
    process: subprocess.Popen[bytes],
) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        if process.poll() is not None:
            output = process.stdout.read().decode("utf-8", errors="ignore") if process.stdout else ""
            raise RuntimeError(f"frontend preview exited early with code {process.returncode}: {output}")
        try:
            status, _, _ = request(base_url, timeout=1.0)
            if status == 200:
                return
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"frontend preview did not become ready: {last_error}")


def start_preview(host: str, port: int) -> subprocess.Popen[bytes]:
    cmd = ["npm", "run", "preview", "--", "--host", host, "--port", str(port), "--strictPort"]
    print(f"+ {' '.join(cmd)}")
    return subprocess.Popen(
        cmd,
        cwd=FRONTEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def stop_preview(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def check_routes(base_url: str, routes: list[str]) -> None:
    for route in routes:
        url = urljoin(base_url, route)
        status, content_type, body = request(url)
        text = body.decode("utf-8", errors="ignore")
        if status != 200 or "text/html" not in content_type or '<div id="root"></div>' not in text:
            raise RuntimeError(f"route check failed: {route} status={status} content_type={content_type}")
        print(f"route ok: {route}")


def check_assets(base_url: str) -> None:
    status, _, body = request(base_url)
    if status != 200:
        raise RuntimeError(f"index request failed: status={status}")
    parser = AssetParser()
    parser.feed(body.decode("utf-8", errors="ignore"))

    asset_paths = {asset for asset in parser.assets}
    dist_assets = sorted(path for path in (DIST_DIR / "assets").glob("*") if path.is_file())
    asset_paths.update(f"/assets/{path.name}" for path in dist_assets)

    if not asset_paths:
        raise RuntimeError("no frontend assets found")

    for asset in sorted(asset_paths):
        url = urljoin(base_url, asset)
        status, content_type, _ = request(url, method="HEAD")
        if status != 200:
            raise RuntimeError(f"asset check failed: {asset} status={status}")
        print(f"asset ok: {asset} ({content_type})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test frontend production routes and assets")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--startup-timeout", type=float, default=15.0)
    parser.add_argument("--route", action="append", dest="routes", help="Route to check; may be repeated")
    args = parser.parse_args()

    if not args.skip_build:
        run(["npm", "run", "build"], cwd=FRONTEND_DIR)

    routes = args.routes or DEFAULT_ROUTES
    base_url = f"http://{args.host}:{args.port}"
    process = start_preview(args.host, args.port)
    try:
        wait_for_server(base_url, args.startup_timeout, process)
        check_routes(base_url, routes)
        check_assets(base_url)
    finally:
        stop_preview(process)

    print("frontend route smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
