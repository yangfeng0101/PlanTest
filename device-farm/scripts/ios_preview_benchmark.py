#!/usr/bin/env python3
"""Benchmark iOS static preview candidates through ios-agent.

The script intentionally talks to the Mac-side ios-agent HTTP API instead of
Appium directly, so it measures the same path used by the Device Farm UI.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import statistics
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def request_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: float = 90.0) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc}") from exc
    return json.loads(body) if body else {}


def percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percent
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def choose_device(agent_url: str, configured_udid: str | None) -> str:
    if configured_udid:
        return configured_udid

    payload = request_json("GET", f"{agent_url}/devices")
    devices = payload.get("devices") if isinstance(payload, dict) else []
    if not isinstance(devices, list):
        raise RuntimeError("ios-agent /devices returned an invalid payload")

    online_devices = [
        device
        for device in devices
        if isinstance(device, dict)
        and str(device.get("status", "")).lower() == "online"
        and bool(device.get("automation_ready"))
    ]
    if not online_devices:
        raise RuntimeError("No online iOS device with automation_ready=true found")

    return str(online_devices[0]["id"])


def decode_image_size(image_base64: str) -> dict[str, Any]:
    try:
        image_bytes = base64.b64decode(image_base64[:120] + "===")
    except Exception:
        return {"encoded_bytes": len(image_base64)}
    size: dict[str, Any] = {"encoded_bytes": len(image_base64), "header": image_bytes[:8].hex()}
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") and len(image_bytes) >= 24:
        width, height = struct.unpack(">II", image_bytes[16:24])
        size.update({"width": width, "height": height, "format": "png"})
        return size
    return {
        **size,
        "format": "unknown",
    }


def probe_mjpeg(url: str | None, timeout: float) -> dict[str, Any]:
    if not url:
        return {"status": "not_configured"}

    started_at = time.perf_counter()
    request = urllib.request.Request(url, headers={"Accept": "multipart/x-mixed-replace,*/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            chunk = response.read(4096)
            content_type = response.headers.get("Content-Type")
        return {
            "status": "reachable",
            "first_read_ms": round((time.perf_counter() - started_at) * 1000),
            "bytes_read": len(chunk),
            "content_type": content_type,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "first_read_ms": round((time.perf_counter() - started_at) * 1000),
            "error": str(exc),
        }


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    agent_url = args.agent_url.rstrip("/")
    device_id = choose_device(agent_url, args.device_id)
    screenshot_url = f"{agent_url}/devices/{urllib.parse.quote(device_id, safe='')}/screenshot"
    source_url = f"{agent_url}/devices/{urllib.parse.quote(device_id, safe='')}/source"
    debug_session_url = f"{agent_url}/devices/{urllib.parse.quote(device_id, safe='')}/debug-session"

    health = request_json("GET", f"{agent_url}/health", timeout=10)
    if not args.keep_session:
        request_json("DELETE", debug_session_url, timeout=10)

    source_started_at = time.perf_counter()
    source_result: dict[str, Any]
    try:
        source_payload = request_json("GET", source_url, timeout=args.request_timeout)
        source_result = {
            "ok": True,
            "duration_ms": round((time.perf_counter() - source_started_at) * 1000),
            "source_length": len(str(source_payload.get("source", ""))),
            "session_reused": bool(source_payload.get("session_reused")),
        }
    except Exception as exc:
        source_result = {
            "ok": False,
            "duration_ms": round((time.perf_counter() - source_started_at) * 1000),
            "error": str(exc),
        }

    latencies_ms: list[float] = []
    failures: list[dict[str, Any]] = []
    first_frame_ms: int | None = None
    screenshot_size: dict[str, Any] | None = None
    screen: dict[str, Any] | None = None
    session_rebuilt_count = 0
    new_session_count = 0
    samples = 0
    benchmark_started_at = time.perf_counter()
    deadline = benchmark_started_at + args.duration

    while time.perf_counter() < deadline:
        samples += 1
        started_at = time.perf_counter()
        try:
            payload = request_json("GET", screenshot_url, timeout=args.request_timeout)
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            latencies_ms.append(elapsed_ms)
            if first_frame_ms is None:
                first_frame_ms = round((time.perf_counter() - benchmark_started_at) * 1000)
            if screenshot_size is None and isinstance(payload.get("image"), str):
                screenshot_size = decode_image_size(str(payload["image"]))
            if isinstance(payload.get("screen"), dict):
                screen = payload["screen"]
            if bool(payload.get("session_rebuilt")):
                session_rebuilt_count += 1
            if not bool(payload.get("session_reused")):
                new_session_count += 1
        except Exception as exc:
            failures.append(
                {
                    "sample": samples,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000),
                    "error": str(exc),
                }
            )
        if args.sleep > 0:
            time.sleep(args.sleep)

    elapsed_seconds = max(time.perf_counter() - benchmark_started_at, 0.001)
    if not args.keep_session:
        request_json("DELETE", debug_session_url, timeout=10)

    successes = len(latencies_ms)
    avg_fps = successes / elapsed_seconds
    appium_summary = {
        "status": "measured",
        "samples": samples,
        "successes": successes,
        "failures": len(failures),
        "avg_fps": round(avg_fps, 2),
        "first_frame_ms": first_frame_ms,
        "latency_ms": {
            "avg": round(statistics.mean(latencies_ms), 1) if latencies_ms else None,
            "p50": round(percentile(latencies_ms, 0.50), 1) if latencies_ms else None,
            "p95": round(percentile(latencies_ms, 0.95), 1) if latencies_ms else None,
        },
        "screen": screen,
        "screenshot": screenshot_size,
        "session_rebuilt_count": session_rebuilt_count,
        "new_session_count": new_session_count,
        "sample_failures": failures[:5],
    }

    return {
        "agent_url": agent_url,
        "device_id": device_id,
        "duration_seconds": args.duration,
        "health_ready": bool(health.get("ready")),
        "source_probe": source_result,
        "candidate_summary": {
            "appium_screenshot_polling": appium_summary,
            "wda_mjpeg_or_direct_stream": probe_mjpeg(args.mjpeg_url, args.mjpeg_timeout),
        },
        "phase3_note": (
            "Use these metrics to decide whether Appium screenshot polling is sufficient for Phase 3, "
            "or whether WDA/MJPEG or a Mac-side capture path is required."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark iOS static preview through ios-agent")
    parser.add_argument("--agent-url", default=os.getenv("IOS_AGENT_URL", "http://127.0.0.1:8015"))
    parser.add_argument("--device-id", default=os.getenv("IOS_DEVICE_ID") or os.getenv("DEVICE_ID"))
    parser.add_argument("--duration", type=float, default=float(os.getenv("IOS_PREVIEW_BENCHMARK_SECONDS", "30")))
    parser.add_argument("--sleep", type=float, default=float(os.getenv("IOS_PREVIEW_BENCHMARK_SLEEP", "0")))
    parser.add_argument("--request-timeout", type=float, default=float(os.getenv("IOS_PREVIEW_REQUEST_TIMEOUT", "90")))
    parser.add_argument("--mjpeg-url", default=os.getenv("IOS_WDA_MJPEG_URL"))
    parser.add_argument("--mjpeg-timeout", type=float, default=float(os.getenv("IOS_WDA_MJPEG_TIMEOUT", "5")))
    parser.add_argument("--keep-session", action="store_true", help="Do not delete the ios-agent debug session before/after")
    return parser.parse_args()


def main() -> int:
    try:
        result = run_benchmark(parse_args())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
