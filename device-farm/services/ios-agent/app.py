import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


APPIUM_HOST = os.getenv("IOS_APPIUM_HOST", "http://127.0.0.1:4724").rstrip("/")
COMMAND_TIMEOUT = float(os.getenv("IOS_AGENT_COMMAND_TIMEOUT", "20"))
DEBUG_SESSION_TTL_SECONDS = int(os.getenv("IOS_AGENT_DEBUG_SESSION_TTL_SECONDS", "300"))
AUTOMATION_READY_UDIDS = {
    udid.strip()
    for udid in os.getenv("IOS_AGENT_AUTOMATION_READY_UDIDS", "").split(",")
    if udid.strip()
}

app = FastAPI(title="Device Farm iOS Agent", version="0.1.0")
debug_sessions: dict[str, dict[str, Any]] = {}
debug_session_locks: dict[str, asyncio.Lock] = {}
debug_command_locks: dict[str, asyncio.Lock] = {}


class TapRequest(BaseModel):
    x: float = Field(..., ge=0)
    y: float = Field(..., ge=0)


class TextRequest(BaseModel):
    text: str = Field(..., min_length=1)


class SwipeRequest(BaseModel):
    startX: float = Field(..., ge=0)
    startY: float = Field(..., ge=0)
    endX: float = Field(..., ge=0)
    endY: float = Field(..., ge=0)
    durationMs: int = Field(500, ge=50, le=5000)


class LongPressRequest(BaseModel):
    x: float = Field(..., ge=0)
    y: float = Field(..., ge=0)
    durationMs: int = Field(800, ge=100, le=5000)


def python_executable() -> str:
    configured = os.getenv("IOS_AGENT_PYTHON")
    if configured:
        return configured

    virtual_env = os.getenv("VIRTUAL_ENV")
    if virtual_env:
        candidate = Path(virtual_env) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if candidate.exists():
            return str(candidate)

    candidate = Path(sys.prefix) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if candidate.exists():
        return str(candidate)

    local_venv = Path(__file__).resolve().parent / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if local_venv.exists():
        return str(local_venv)

    return sys.executable


async def run_pymobiledevice3_json(*args: str) -> Any:
    process = await asyncio.create_subprocess_exec(
        python_executable(),
        "-m",
        "pymobiledevice3",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=COMMAND_TIMEOUT)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise RuntimeError(f"pymobiledevice3 timed out: {' '.join(args)}") from exc

    if process.returncode != 0:
        detail = stderr.decode(errors="replace").strip() or stdout.decode(errors="replace").strip()
        raise RuntimeError(detail or f"pymobiledevice3 failed: {' '.join(args)}")

    output = stdout.decode(errors="replace").strip()
    if not output:
        return None
    return json.loads(output)


async def appium_status() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{APPIUM_HOST}/status")
        response.raise_for_status()
        payload = response.json()
        value = payload.get("value") if isinstance(payload, dict) else {}
        ready = bool(value.get("ready", True)) if isinstance(value, dict) else True
        return {
            "ready": ready,
            "reachable": True,
            "host": APPIUM_HOST,
            "raw": payload,
        }
    except Exception as exc:
        return {
            "ready": False,
            "reachable": False,
            "host": APPIUM_HOST,
            "error": str(exc),
        }


def env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def ios_debug_capabilities(udid: str) -> dict[str, Any]:
    caps: dict[str, Any] = {
        "platformName": "iOS",
        "appium:automationName": "XCUITest",
        "appium:udid": udid,
        "appium:deviceName": udid,
        "appium:noReset": True,
        "appium:newCommandTimeout": DEBUG_SESSION_TTL_SECONDS,
        "appium:waitForQuiescence": False,
        "appium:skipLogCapture": True,
    }

    xcode_org_id = os.getenv("IOS_XCODE_ORG_ID", "").strip()
    xcode_signing_id = os.getenv("IOS_XCODE_SIGNING_ID", "").strip()
    wda_bundle_id = os.getenv("IOS_WDA_BUNDLE_ID", "").strip()
    if xcode_org_id:
        caps["appium:xcodeOrgId"] = xcode_org_id
    if xcode_signing_id:
        caps["appium:xcodeSigningId"] = xcode_signing_id
    if wda_bundle_id:
        caps["appium:updatedWDABundleId"] = wda_bundle_id
    if env_bool("IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION"):
        caps["appium:allowProvisioningDeviceRegistration"] = True

    return caps


def sanitize_appium_error(detail: str) -> str:
    sanitized = detail or ""
    try:
        payload = json.loads(sanitized)
        value = payload.get("value") if isinstance(payload, dict) else {}
        message = value.get("message") if isinstance(value, dict) else None
        if message:
            sanitized = str(message)
    except Exception:
        pass

    for env_name in ("IOS_XCODE_ORG_ID", "IOS_XCODE_SIGNING_ID", "IOS_WDA_BUNDLE_ID"):
        value = os.getenv(env_name, "").strip()
        if value:
            sanitized = sanitized.replace(value, "<configured>")

    lower = sanitized.lower()
    if "not been explicitly trusted" in lower or "invalid code signature" in lower:
        return f"WDA 启动被 iPhone 安全策略拒绝：请在手机“设置 > 通用 > VPN 与设备管理”信任当前开发者证书后重试。原始错误：{sanitized}"
    if "xcodebuild failed with code 65" in lower:
        return f"WDA 启动失败：xcodebuild 返回 65，通常是 Xcode 签名、证书信任或 WDA 构建配置问题。原始错误：{sanitized}"
    return sanitized


def debug_session_lock(udid: str) -> asyncio.Lock:
    lock = debug_session_locks.get(udid)
    if lock is None:
        lock = asyncio.Lock()
        debug_session_locks[udid] = lock
    return lock


def debug_command_lock(udid: str) -> asyncio.Lock:
    lock = debug_command_locks.get(udid)
    if lock is None:
        lock = asyncio.Lock()
        debug_command_locks[udid] = lock
    return lock


async def connected_udids() -> set[str]:
    payload = await run_pymobiledevice3_json("usbmux", "list")
    udids: set[str] = set()
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            udid = item.get("UniqueDeviceID") or item.get("Identifier") or item.get("SerialNumber") or item.get("UDID")
            if udid:
                udids.add(str(udid))
    return udids


async def ensure_debug_allowed(udid: str) -> None:
    try:
        udids = await connected_udids()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to list connected iOS devices: {exc}") from exc

    if udid not in udids:
        raise HTTPException(status_code=404, detail="iOS device is not connected or trusted")
    if udid not in AUTOMATION_READY_UDIDS:
        raise HTTPException(status_code=409, detail="iOS device WDA/Appium automation has not been verified")

    status = await appium_status()
    if not bool(status["ready"] and status["reachable"]):
        raise HTTPException(status_code=503, detail="Appium XCUITest service is not ready")


def is_stale_session(session: dict[str, Any]) -> bool:
    last_used_at = float(session.get("last_used_at") or 0)
    return time.time() - last_used_at > DEBUG_SESSION_TTL_SECONDS


async def delete_appium_session(session_id: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=COMMAND_TIMEOUT) as client:
            await client.delete(f"{APPIUM_HOST}/session/{session_id}")
    except Exception:
        pass


async def create_appium_session(udid: str) -> str:
    payload = {"capabilities": {"alwaysMatch": ios_debug_capabilities(udid), "firstMatch": [{}]}}
    try:
        async with httpx.AsyncClient(timeout=COMMAND_TIMEOUT) as client:
            response = await client.post(f"{APPIUM_HOST}/session", json=payload)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Unable to reach Appium XCUITest service: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=sanitize_appium_error(response.text))

    data = response.json()
    value = data.get("value") if isinstance(data, dict) else {}
    session_id = data.get("sessionId") if isinstance(data, dict) else None
    if isinstance(value, dict):
        session_id = value.get("sessionId") or session_id
    if not session_id:
        raise HTTPException(status_code=502, detail="Appium did not return a session id")
    return str(session_id)


async def get_debug_session(udid: str) -> tuple[str, bool]:
    await ensure_debug_allowed(udid)
    async with debug_session_lock(udid):
        cached = debug_sessions.get(udid)
        if cached and not is_stale_session(cached):
            cached["last_used_at"] = time.time()
            return str(cached["session_id"]), True

        if cached:
            await delete_appium_session(str(cached["session_id"]))
            debug_sessions.pop(udid, None)

        session_id = await create_appium_session(udid)
        debug_sessions[udid] = {
            "session_id": session_id,
            "created_at": time.time(),
            "last_used_at": time.time(),
        }
        return session_id, False


def is_invalid_session_response(response: httpx.Response) -> bool:
    if response.status_code == 404:
        return True
    try:
        payload = response.json()
    except Exception:
        return False
    value = payload.get("value") if isinstance(payload, dict) else {}
    error = value.get("error") if isinstance(value, dict) else ""
    return str(error).lower() in {"invalid session id", "no such driver"}


async def appium_session_request(
    udid: str,
    method: str,
    endpoint: str,
    payload: Optional[dict[str, Any]] = None,
) -> tuple[Any, bool]:
    async with debug_command_lock(udid):
        return await _appium_session_request(udid, method, endpoint, payload)


async def _appium_session_request(
    udid: str,
    method: str,
    endpoint: str,
    payload: Optional[dict[str, Any]] = None,
) -> tuple[Any, bool]:
    session_id, reused = await get_debug_session(udid)
    async with httpx.AsyncClient(timeout=COMMAND_TIMEOUT) as client:
        response = await client.request(
            method,
            f"{APPIUM_HOST}/session/{session_id}/{endpoint.lstrip('/')}",
            json=payload,
        )

    if is_invalid_session_response(response):
        async with debug_session_lock(udid):
            debug_sessions.pop(udid, None)
        session_id, _ = await get_debug_session(udid)
        async with httpx.AsyncClient(timeout=COMMAND_TIMEOUT) as client:
            response = await client.request(
                method,
                f"{APPIUM_HOST}/session/{session_id}/{endpoint.lstrip('/')}",
                json=payload,
            )
        reused = False

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=sanitize_appium_error(response.text))

    data = response.json()
    value = data.get("value") if isinstance(data, dict) else None
    return value, reused


async def appium_session_get(udid: str, endpoint: str) -> tuple[Any, bool]:
    return await appium_session_request(udid, "GET", endpoint)


async def appium_session_post(udid: str, endpoint: str, payload: dict[str, Any]) -> tuple[Any, bool]:
    return await appium_session_request(udid, "POST", endpoint, payload)


def screen_from_window_rect(value: Any) -> Optional[dict[str, int]]:
    if not isinstance(value, dict):
        return None
    width = int_or_default(value.get("width"), 0)
    height = int_or_default(value.get("height"), 0)
    if width <= 0 or height <= 0:
        return None
    return {"width": width, "height": height}


async def appium_screen(udid: str) -> Optional[dict[str, int]]:
    try:
        value, _ = await appium_session_get(udid, "window/rect")
        return screen_from_window_rect(value)
    except Exception:
        return None


def tap_actions_payload(x: float, y: float) -> dict[str, Any]:
    point_x = round(x)
    point_y = round(y)
    return {
        "actions": [
            {
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {"type": "pointerMove", "duration": 0, "x": point_x, "y": point_y, "origin": "viewport"},
                    {"type": "pointerDown", "button": 0},
                    {"type": "pause", "duration": 100},
                    {"type": "pointerUp", "button": 0},
                ],
            }
        ]
    }


def swipe_actions_payload(start_x: float, start_y: float, end_x: float, end_y: float, duration_ms: int) -> dict[str, Any]:
    return {
        "actions": [
            {
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {
                        "type": "pointerMove",
                        "duration": 0,
                        "x": round(start_x),
                        "y": round(start_y),
                        "origin": "viewport",
                    },
                    {"type": "pointerDown", "button": 0},
                    {"type": "pause", "duration": 80},
                    {
                        "type": "pointerMove",
                        "duration": int(duration_ms),
                        "x": round(end_x),
                        "y": round(end_y),
                        "origin": "viewport",
                    },
                    {"type": "pointerUp", "button": 0},
                ],
            }
        ]
    }


def long_press_actions_payload(x: float, y: float, duration_ms: int) -> dict[str, Any]:
    return {
        "actions": [
            {
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {"type": "pointerMove", "duration": 0, "x": round(x), "y": round(y), "origin": "viewport"},
                    {"type": "pointerDown", "button": 0},
                    {"type": "pause", "duration": int(duration_ms)},
                    {"type": "pointerUp", "button": 0},
                ],
            }
        ]
    }


async def release_pointer_actions(udid: str) -> None:
    try:
        await appium_session_post(udid, "actions", {"actions": []})
    except HTTPException:
        pass


def element_id_from_active_element(value: Any) -> Optional[str]:
    if not isinstance(value, dict):
        return None
    for key in ("element-6066-11e4-a52e-4f735466cecf", "ELEMENT"):
        element_id = value.get(key)
        if element_id:
            return str(element_id)
    return None


def text_value_payload(text: str) -> dict[str, Any]:
    return {"text": text, "value": list(text)}


def is_no_active_element_error(detail: Any) -> bool:
    text = str(detail or "").lower()
    return any(
        token in text
        for token in (
            "unable to find an element",
            "no such element",
            "active element",
        )
    )


async def active_element_id(udid: str) -> tuple[str, bool]:
    try:
        value, reused = await appium_session_get(udid, "element/active")
    except HTTPException as exc:
        if is_no_active_element_error(exc.detail):
            raise HTTPException(status_code=409, detail="No active iOS input element. Tap an input field first.") from exc
        raise

    element_id = element_id_from_active_element(value)
    if not element_id:
        raise HTTPException(status_code=409, detail="No active iOS input element. Tap an input field first.")
    return element_id, reused


def screen_resolution(product_type: str) -> str:
    resolutions = {
        "iPhone14,2": "1170x2532",
        "iPhone14,3": "1284x2778",
        "iPhone15,2": "1179x2556",
        "iPhone15,3": "1290x2796",
        "iPhone16,1": "1179x2556",
        "iPhone16,2": "1320x2868",
        "iPad13,1": "1620x2160",
        "iPad13,8": "2048x2732",
    }
    return resolutions.get(product_type, "1170x2532")


def screen_size(product_type: str) -> float:
    sizes = {
        "iPhone14,2": 6.1,
        "iPhone14,3": 6.7,
        "iPhone15,2": 6.1,
        "iPhone15,3": 6.7,
        "iPhone16,1": 6.1,
        "iPhone16,2": 6.7,
        "iPad13,1": 10.9,
        "iPad13,8": 12.9,
    }
    return sizes.get(product_type, 6.1)


def int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


async def device_detail(udid: str, appium_ready: bool) -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        payload = await run_pymobiledevice3_json("lockdown", "info", "--udid", udid)
        if isinstance(payload, dict):
            info = payload
    except Exception as exc:
        info = {"DeviceName": udid, "ProductType": "Unknown", "ProductVersion": "Unknown", "error": str(exc)}

    product_type = str(info.get("ProductType") or "Unknown")
    automation_ready = appium_ready and udid in AUTOMATION_READY_UDIDS
    if automation_ready:
        automation_status = "verified_ready"
    elif appium_ready:
        automation_status = "requires_wda_verification"
    else:
        automation_status = "appium_unavailable"

    return {
        "id": udid,
        "name": info.get("DeviceName") or udid,
        "model": product_type,
        "brand": "Apple",
        "os": "ios",
        "os_version": info.get("ProductVersion") or "Unknown",
        "status": "online",
        "screen_resolution": screen_resolution(product_type),
        "screen_size": screen_size(product_type),
        "cpu": info.get("CPUArchitecture") or "arm64",
        "memory": "Unknown",
        "storage": "Unknown",
        "battery_level": int_or_default(info.get("BatteryCurrentCapacity"), 100),
        "appium_ready": appium_ready,
        "automation_ready": automation_ready,
        "automation_status": automation_status,
    }


@app.get("/appium/status")
async def get_appium_status():
    return await appium_status()


@app.get("/health")
async def health():
    status = await appium_status()
    ready = bool(status["ready"] and status["reachable"])
    return {
        "ok": True,
        "ready": ready,
        "service": "ios-agent",
        "appium": status,
    }


@app.get("/devices")
async def list_devices():
    status = await appium_status()
    devices: list[dict[str, Any]] = []

    try:
        payload = await run_pymobiledevice3_json("usbmux", "list")
        if isinstance(payload, list):
            for item in payload:
                udid = item.get("UniqueDeviceID") or item.get("Identifier") or item.get("SerialNumber") or item.get("UDID")
                if udid:
                    detail = await device_detail(str(udid), bool(status["ready"] and status["reachable"]))
                    detail["name"] = item.get("DeviceName") or detail["name"]
                    detail["model"] = item.get("ProductType") or detail["model"]
                    detail["os_version"] = item.get("ProductVersion") or detail["os_version"]
                    devices.append(detail)
    except Exception as exc:
        return {
            "devices": [],
            "appium": status,
            "error": str(exc),
        }

    return {
        "devices": devices,
        "appium": status,
    }


@app.get("/devices/{udid}/screenshot")
async def get_device_screenshot(udid: str):
    value, reused = await appium_session_get(udid, "screenshot")
    if not isinstance(value, str) or not value:
        raise HTTPException(status_code=502, detail="Appium returned an empty screenshot")
    return {
        "device_id": udid,
        "image": value,
        "format": "png",
        "session_reused": reused,
        "screen": await appium_screen(udid),
    }


@app.get("/devices/{udid}/source")
async def get_device_source(udid: str):
    value, reused = await appium_session_get(udid, "source")
    if not isinstance(value, str) or not value:
        raise HTTPException(status_code=502, detail="Appium returned an empty page source")
    return {
        "device_id": udid,
        "source": value,
        "session_reused": reused,
    }


@app.delete("/devices/{udid}/debug-session")
async def delete_debug_session(udid: str):
    async with debug_session_lock(udid):
        cached = debug_sessions.pop(udid, None)
    if cached:
        await delete_appium_session(str(cached["session_id"]))
    return {
        "device_id": udid,
        "released": bool(cached),
    }


@app.post("/devices/{udid}/tap")
async def tap_device(udid: str, request: TapRequest):
    _, reused = await appium_session_post(udid, "actions", tap_actions_payload(request.x, request.y))
    await release_pointer_actions(udid)
    return {
        "device_id": udid,
        "success": True,
        "x": round(request.x),
        "y": round(request.y),
        "session_reused": reused,
        "screen": await appium_screen(udid),
    }


@app.post("/devices/{udid}/swipe")
async def swipe_device(udid: str, request: SwipeRequest):
    _, reused = await appium_session_post(
        udid,
        "actions",
        swipe_actions_payload(request.startX, request.startY, request.endX, request.endY, request.durationMs),
    )
    await release_pointer_actions(udid)
    return {
        "device_id": udid,
        "success": True,
        "startX": round(request.startX),
        "startY": round(request.startY),
        "endX": round(request.endX),
        "endY": round(request.endY),
        "durationMs": request.durationMs,
        "session_reused": reused,
        "screen": await appium_screen(udid),
    }


@app.post("/devices/{udid}/long-press")
async def long_press_device(udid: str, request: LongPressRequest):
    _, reused = await appium_session_post(
        udid,
        "actions",
        long_press_actions_payload(request.x, request.y, request.durationMs),
    )
    await release_pointer_actions(udid)
    return {
        "device_id": udid,
        "success": True,
        "x": round(request.x),
        "y": round(request.y),
        "durationMs": request.durationMs,
        "session_reused": reused,
        "screen": await appium_screen(udid),
    }


@app.post("/devices/{udid}/text")
async def input_text_device(udid: str, request: TextRequest):
    element_id, reused = await active_element_id(udid)
    await appium_session_post(udid, f"element/{element_id}/value", text_value_payload(request.text))
    return {
        "device_id": udid,
        "success": True,
        "text_length": len(request.text),
        "session_reused": reused,
        "screen": await appium_screen(udid),
    }


@app.post("/devices/{udid}/clear-text")
async def clear_text_device(udid: str):
    element_id, reused = await active_element_id(udid)
    await appium_session_post(udid, f"element/{element_id}/clear", {})
    return {
        "device_id": udid,
        "success": True,
        "session_reused": reused,
        "screen": await appium_screen(udid),
    }
