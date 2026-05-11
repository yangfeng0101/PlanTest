#!/usr/bin/env python3
"""Probe iOS realtime video source candidates through Appium XCUITest.

This is a local spike tool. It creates an isolated Appium session with a WDA
MJPEG port, samples the MJPEG stream, compares it with Appium screenshot
polling, and then deletes the session.
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
from pathlib import Path
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
            body = response.read().decode("utf-8", errors="replace")
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


def bool_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def default_prebuilt_wda_path() -> Path:
    return (
        Path.home()
        / ".appium"
        / "node_modules"
        / "appium-xcuitest-driver"
        / "node_modules"
        / "Build"
        / "Products"
        / "Debug-iphoneos"
        / "WebDriverAgentRunner-Runner.app"
    )


def resolve_prebuilt_wda_path(configured_path: str | None) -> str:
    candidate = Path(configured_path).expanduser() if configured_path else default_prebuilt_wda_path()
    if not candidate.exists():
        raise RuntimeError(
            "Prebuilt WDA app was not found at "
            f"{candidate}. Run one normal Appium/WDA build first, or pass --prebuilt-wda-path."
        )
    return str(candidate)


def append_trust_preinstall_hint(error: Exception, trust_preinstall_wda: bool) -> RuntimeError:
    detail = str(error)
    lower = detail.lower()
    trust_related = (
        "not been explicitly trusted" in lower
        or "invalid code signature" in lower
        or "xcodebuild failed with code 65" in lower
        or (trust_preinstall_wda and "failed on launching" in lower)
        or (trust_preinstall_wda and "not launchable" in lower)
    )
    if trust_related:
        if trust_preinstall_wda:
            hint = (
                "The probe used usePreinstalledWDA + prebuiltWDAPath, so Appium should leave the WDA runner installed "
                "even though iOS rejected the launch. Open iPhone Settings > General > VPN & Device Management, trust "
                "the developer certificate, and then rerun the probe without --trust-preinstall-wda."
            )
        else:
            hint = (
                "iOS rejected WDA before it could launch, and the normal Appium path usually uninstalls WDA after this "
                "failure. Rerun with --trust-preinstall-wda so the prebuilt WDA runner remains installed long enough "
                "to trust it in iPhone Settings > General > VPN & Device Management."
            )
        return RuntimeError(f"{hint} Original error: {detail}")
    return RuntimeError(detail)


def choose_device(agent_url: str | None, configured_udid: str | None) -> str:
    if configured_udid:
        return configured_udid
    if not agent_url:
        raise RuntimeError("Missing device id. Set IOS_DEVICE_ID or pass --device-id.")

    payload = request_json("GET", f"{agent_url.rstrip('/')}/devices", timeout=15)
    devices = payload.get("devices") if isinstance(payload, dict) else []
    if not isinstance(devices, list):
        raise RuntimeError("ios-agent /devices returned an invalid payload")

    for device in devices:
        if (
            isinstance(device, dict)
            and str(device.get("status", "")).lower() == "online"
            and bool(device.get("automation_ready"))
        ):
            return str(device["id"])

    raise RuntimeError("No online iOS device with automation_ready=true found")


def signing_caps(allow_default_signing: bool) -> tuple[dict[str, Any], dict[str, bool]]:
    caps: dict[str, Any] = {}
    configured = {
        "xcodeOrgId": False,
        "xcodeSigningId": False,
        "updatedWDABundleId": False,
        "allowProvisioningDeviceRegistration": False,
    }

    xcode_org_id = os.getenv("IOS_XCODE_ORG_ID", "").strip()
    xcode_signing_id = os.getenv("IOS_XCODE_SIGNING_ID", "").strip()
    wda_bundle_id = os.getenv("IOS_WDA_BUNDLE_ID", "").strip()
    if xcode_org_id:
        caps["appium:xcodeOrgId"] = xcode_org_id
        configured["xcodeOrgId"] = True
    if xcode_signing_id:
        caps["appium:xcodeSigningId"] = xcode_signing_id
        configured["xcodeSigningId"] = True
    if wda_bundle_id:
        caps["appium:updatedWDABundleId"] = wda_bundle_id
        configured["updatedWDABundleId"] = True
    if bool_env("IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION"):
        caps["appium:allowProvisioningDeviceRegistration"] = True
        configured["allowProvisioningDeviceRegistration"] = True

    missing = [
        name
        for name, ok in (
            ("IOS_XCODE_ORG_ID", configured["xcodeOrgId"]),
            ("IOS_XCODE_SIGNING_ID", configured["xcodeSigningId"]),
            ("IOS_WDA_BUNDLE_ID", configured["updatedWDABundleId"]),
        )
        if not ok
    ]
    if missing and not allow_default_signing:
        raise RuntimeError(
            "Missing WDA signing environment variables: "
            + ", ".join(missing)
            + ". Export the same signing values used by ios-agent, or pass --allow-default-wda-signing."
        )

    return caps, configured


def create_session(
    appium_host: str,
    device_id: str,
    mjpeg_port: int,
    request_timeout: float,
    extra_caps: dict[str, Any],
    trust_preinstall_wda: bool,
) -> str:
    caps: dict[str, Any] = {
        "platformName": "iOS",
        "appium:automationName": "XCUITest",
        "appium:udid": device_id,
        "appium:noReset": True,
        "appium:newCommandTimeout": 120,
        "appium:waitForQuiescence": False,
        "appium:mjpegServerPort": mjpeg_port,
        "appium:skipLogCapture": True,
    }
    caps.update(extra_caps)

    payload = {"capabilities": {"alwaysMatch": caps, "firstMatch": [{}]}}
    try:
        response = request_json("POST", f"{appium_host}/session", payload=payload, timeout=request_timeout)
    except Exception as exc:
        raise append_trust_preinstall_hint(exc, trust_preinstall_wda) from exc
    value = response.get("value") if isinstance(response, dict) else {}
    session_id = response.get("sessionId") if isinstance(response, dict) else None
    if isinstance(value, dict):
        session_id = value.get("sessionId") or session_id
    if not session_id:
        raise RuntimeError("Appium did not return a session id")
    return str(session_id)


def delete_session(appium_host: str, session_id: str, request_timeout: float) -> bool:
    try:
        request_json("DELETE", f"{appium_host}/session/{session_id}", timeout=request_timeout)
        return True
    except Exception:
        return False


def release_ios_agent_debug_session(agent_url: str | None, device_id: str, request_timeout: float) -> dict[str, Any]:
    if not agent_url:
        return {"attempted": False, "released": False, "reason": "ios-agent url not configured"}
    url = f"{agent_url.rstrip('/')}/devices/{urllib.parse.quote(device_id, safe='')}/debug-session"
    try:
        payload = request_json("DELETE", url, timeout=min(request_timeout, 15))
        return {
            "attempted": True,
            "released": bool(payload.get("released")),
        }
    except Exception as exc:
        return {
            "attempted": True,
            "released": False,
            "error": str(exc),
        }


def configure_mjpeg_settings(appium_host: str, session_id: str, args: argparse.Namespace) -> dict[str, Any]:
    settings = {
        "mjpegServerFramerate": args.mjpeg_framerate,
        "mjpegScalingFactor": args.mjpeg_scaling_factor,
        "mjpegServerScreenshotQuality": args.mjpeg_quality,
    }
    started_at = time.perf_counter()
    try:
        request_json(
            "POST",
            f"{appium_host}/session/{session_id}/appium/settings",
            payload={"settings": settings},
            timeout=args.request_timeout,
        )
        return {
            "ok": True,
            "duration_ms": round((time.perf_counter() - started_at) * 1000),
            "settings": settings,
        }
    except Exception as exc:
        return {
            "ok": False,
            "duration_ms": round((time.perf_counter() - started_at) * 1000),
            "settings": settings,
            "error": str(exc),
        }


def jpeg_size(frame: bytes) -> dict[str, Any]:
    index = 2
    while index + 9 < len(frame):
        if frame[index] != 0xFF:
            index += 1
            continue
        marker = frame[index + 1]
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height, width = struct.unpack(">HH", frame[index + 5 : index + 9])
            return {"width": width, "height": height, "format": "jpeg"}
        if marker in {0xD8, 0xD9}:
            index += 2
            continue
        segment_length = struct.unpack(">H", frame[index + 2 : index + 4])[0]
        if segment_length < 2:
            break
        index += 2 + segment_length
    return {"format": "jpeg"}


def png_size(image_base64: str) -> dict[str, Any]:
    try:
        image_bytes = base64.b64decode(image_base64[:120] + "===")
    except Exception:
        return {"encoded_bytes": len(image_base64)}
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") and len(image_bytes) >= 24:
        width, height = struct.unpack(">II", image_bytes[16:24])
        return {"encoded_bytes": len(image_base64), "width": width, "height": height, "format": "png"}
    return {"encoded_bytes": len(image_base64), "format": "unknown"}


def sample_mjpeg_stream(url: str, duration: float, connect_timeout: float) -> dict[str, Any]:
    started_at = time.perf_counter()
    deadline = started_at + duration
    frame_times: list[float] = []
    frame_sizes: list[int] = []
    first_frame: dict[str, Any] | None = None
    buffer = bytearray()
    error = ""

    request = urllib.request.Request(url, headers={"Accept": "multipart/x-mixed-replace,*/*"})
    try:
        with urllib.request.urlopen(request, timeout=connect_timeout) as response:
            content_type = response.headers.get("Content-Type")
            while time.perf_counter() < deadline:
                chunk = response.read(8192)
                if not chunk:
                    error = "MJPEG stream ended"
                    break
                buffer.extend(chunk)

                while True:
                    start = buffer.find(b"\xff\xd8")
                    if start < 0:
                        if len(buffer) > 1024 * 1024:
                            del buffer[:-2]
                        break
                    end = buffer.find(b"\xff\xd9", start + 2)
                    if end < 0:
                        if start > 0:
                            del buffer[:start]
                        break
                    end += 2
                    frame = bytes(buffer[start:end])
                    del buffer[:end]
                    now = time.perf_counter()
                    frame_times.append(now)
                    frame_sizes.append(len(frame))
                    if first_frame is None:
                        first_frame = {
                            "first_frame_ms": round((now - started_at) * 1000),
                            "frame_size_bytes": len(frame),
                            **jpeg_size(frame),
                        }
            stream_status = "measured" if frame_times else "no_frames"
    except Exception as exc:
        content_type = None
        stream_status = "failed"
        error = str(exc)

    elapsed = max(time.perf_counter() - started_at, 0.001)
    gaps_ms = [
        (frame_times[index] - frame_times[index - 1]) * 1000
        for index in range(1, len(frame_times))
    ]
    avg_fps = len(frame_times) / elapsed
    return {
        "status": stream_status,
        "url": url,
        "duration_seconds": round(elapsed, 3),
        "content_type": content_type,
        "frames": len(frame_times),
        "avg_fps": round(avg_fps, 2),
        "first_frame": first_frame,
        "frame_gap_ms": {
            "avg": round(statistics.mean(gaps_ms), 1) if gaps_ms else None,
            "p50": round(percentile(gaps_ms, 0.50), 1) if gaps_ms else None,
            "p95": round(percentile(gaps_ms, 0.95), 1) if gaps_ms else None,
        },
        "frame_size_bytes": {
            "avg": round(statistics.mean(frame_sizes), 1) if frame_sizes else None,
            "min": min(frame_sizes) if frame_sizes else None,
            "max": max(frame_sizes) if frame_sizes else None,
        },
        "error": error,
    }


def sample_appium_screenshots(appium_host: str, session_id: str, duration: float, request_timeout: float) -> dict[str, Any]:
    latencies_ms: list[float] = []
    failures: list[dict[str, Any]] = []
    screenshot: dict[str, Any] | None = None
    first_frame_ms: int | None = None
    samples = 0
    started_at = time.perf_counter()
    deadline = started_at + duration

    while time.perf_counter() < deadline:
        samples += 1
        sample_started_at = time.perf_counter()
        try:
            payload = request_json(
                "GET",
                f"{appium_host}/session/{session_id}/screenshot",
                timeout=request_timeout,
            )
            elapsed_ms = (time.perf_counter() - sample_started_at) * 1000
            latencies_ms.append(elapsed_ms)
            if first_frame_ms is None:
                first_frame_ms = round((time.perf_counter() - started_at) * 1000)
            value = payload.get("value") if isinstance(payload, dict) else None
            if screenshot is None and isinstance(value, str):
                screenshot = png_size(value)
        except Exception as exc:
            failures.append(
                {
                    "sample": samples,
                    "duration_ms": round((time.perf_counter() - sample_started_at) * 1000),
                    "error": str(exc),
                }
            )

    elapsed = max(time.perf_counter() - started_at, 0.001)
    return {
        "status": "measured",
        "duration_seconds": round(elapsed, 3),
        "samples": samples,
        "successes": len(latencies_ms),
        "failures": len(failures),
        "avg_fps": round(len(latencies_ms) / elapsed, 2),
        "first_frame_ms": first_frame_ms,
        "latency_ms": {
            "avg": round(statistics.mean(latencies_ms), 1) if latencies_ms else None,
            "p50": round(percentile(latencies_ms, 0.50), 1) if latencies_ms else None,
            "p95": round(percentile(latencies_ms, 0.95), 1) if latencies_ms else None,
        },
        "screenshot": screenshot,
        "sample_failures": failures[:5],
    }


def recommendation(mjpeg_result: dict[str, Any]) -> str:
    avg_fps = float(mjpeg_result.get("avg_fps") or 0)
    frame_gap = mjpeg_result.get("frame_gap_ms") if isinstance(mjpeg_result.get("frame_gap_ms"), dict) else {}
    p95_gap = frame_gap.get("p95")
    frames = int(mjpeg_result.get("frames") or 0)
    if frames > 0 and avg_fps >= 5 and isinstance(p95_gap, (int, float)) and p95_gap <= 500:
        return "wda_mjpeg_stream"
    return "mac_host_capture_spike"


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    appium_host = args.appium_host.rstrip("/")
    device_id = choose_device(args.ios_agent_url, args.device_id)
    mjpeg_url = f"http://{args.mjpeg_host}:{args.mjpeg_port}"
    session_id = ""
    session_deleted = False
    extra_caps, signing_configured = signing_caps(args.allow_default_wda_signing)
    ios_agent_release = {"attempted": False, "released": False}
    prebuilt_wda_path = ""
    if args.trust_preinstall_wda:
        prebuilt_wda_path = resolve_prebuilt_wda_path(args.prebuilt_wda_path)
        extra_caps["appium:usePreinstalledWDA"] = True
        extra_caps["appium:prebuiltWDAPath"] = prebuilt_wda_path

    try:
        if not args.skip_ios_agent_release:
            ios_agent_release = release_ios_agent_debug_session(args.ios_agent_url, device_id, args.request_timeout)
            if ios_agent_release.get("error"):
                raise RuntimeError(f"Unable to release ios-agent debug session before probe: {ios_agent_release['error']}")
        session_id = create_session(
            appium_host,
            device_id,
            args.mjpeg_port,
            args.request_timeout,
            extra_caps,
            args.trust_preinstall_wda,
        )
        settings_result = configure_mjpeg_settings(appium_host, session_id, args)
        if args.mjpeg_warmup_seconds > 0:
            time.sleep(args.mjpeg_warmup_seconds)
        mjpeg_result = sample_mjpeg_stream(mjpeg_url, args.duration, args.mjpeg_connect_timeout)
        screenshot_result = sample_appium_screenshots(
            appium_host,
            session_id,
            args.screenshot_duration,
            args.request_timeout,
        )
    finally:
        if session_id:
            session_deleted = delete_session(appium_host, session_id, args.request_timeout)

    chosen = recommendation(mjpeg_result)
    return {
        "device_id": device_id,
        "appium_host": appium_host,
        "mjpeg_port": args.mjpeg_port,
        "probe_session": {
            "created": bool(session_id),
            "deleted": session_deleted,
            "signing_caps_configured": signing_configured,
            "trust_preinstall_wda": bool(args.trust_preinstall_wda),
            "prebuilt_wda_path_configured": bool(prebuilt_wda_path),
            "ios_agent_debug_session_release": ios_agent_release,
        },
        "settings": settings_result,
        "candidate_summary": {
            "wda_mjpeg_stream": mjpeg_result,
            "appium_screenshot_polling": screenshot_result,
        },
        "recommendation": {
            "next_phase_source": chosen,
            "reason": (
                "WDA/MJPEG meets the Phase 3.2 threshold"
                if chosen == "wda_mjpeg_stream"
                else "WDA/MJPEG did not meet avg_fps>=5 and p95_frame_gap_ms<=500; validate Mac host capture next"
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe iOS WDA/MJPEG stream source")
    parser.add_argument("--appium-host", default=os.getenv("IOS_APPIUM_HOST", "http://127.0.0.1:4724"))
    parser.add_argument("--ios-agent-url", default=os.getenv("IOS_AGENT_URL", "http://127.0.0.1:8015"))
    parser.add_argument("--device-id", default=os.getenv("IOS_DEVICE_ID") or os.getenv("DEVICE_ID"))
    parser.add_argument("--mjpeg-host", default=os.getenv("IOS_WDA_MJPEG_HOST", "127.0.0.1"))
    parser.add_argument("--mjpeg-port", type=int, default=int(os.getenv("IOS_WDA_MJPEG_PORT", "9100")))
    parser.add_argument("--duration", type=float, default=float(os.getenv("IOS_STREAM_PROBE_SECONDS", "30")))
    parser.add_argument("--screenshot-duration", type=float, default=float(os.getenv("IOS_STREAM_SCREENSHOT_SECONDS", "10")))
    parser.add_argument("--request-timeout", type=float, default=float(os.getenv("IOS_STREAM_REQUEST_TIMEOUT", "90")))
    parser.add_argument("--mjpeg-connect-timeout", type=float, default=float(os.getenv("IOS_WDA_MJPEG_TIMEOUT", "10")))
    parser.add_argument("--mjpeg-framerate", type=int, default=int(os.getenv("IOS_WDA_MJPEG_FRAMERATE", "10")))
    parser.add_argument("--mjpeg-scaling-factor", type=float, default=float(os.getenv("IOS_WDA_MJPEG_SCALING_FACTOR", "50")))
    parser.add_argument("--mjpeg-quality", type=int, default=int(os.getenv("IOS_WDA_MJPEG_QUALITY", "40")))
    parser.add_argument("--mjpeg-warmup-seconds", type=float, default=float(os.getenv("IOS_WDA_MJPEG_WARMUP_SECONDS", "2")))
    parser.add_argument("--trust-preinstall-wda", action="store_true", default=bool_env("IOS_WDA_TRUST_PREINSTALL"))
    parser.add_argument("--prebuilt-wda-path", default=os.getenv("IOS_PREBUILT_WDA_PATH", ""))
    parser.add_argument("--allow-default-wda-signing", action="store_true")
    parser.add_argument("--skip-ios-agent-release", action="store_true")
    return parser.parse_args()


def main() -> int:
    try:
        result = run_probe(parse_args())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
