import asyncio
import json
import os
import sys
import time
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException


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


async def run_pymobiledevice3_json(*args: str) -> Any:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
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
    for env_name in ("IOS_XCODE_ORG_ID", "IOS_XCODE_SIGNING_ID", "IOS_WDA_BUNDLE_ID"):
        value = os.getenv(env_name, "").strip()
        if value:
            sanitized = sanitized.replace(value, "<configured>")
    return sanitized


def debug_session_lock(udid: str) -> asyncio.Lock:
    lock = debug_session_locks.get(udid)
    if lock is None:
        lock = asyncio.Lock()
        debug_session_locks[udid] = lock
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


async def appium_session_get(udid: str, endpoint: str) -> tuple[Any, bool]:
    session_id, reused = await get_debug_session(udid)
    async with httpx.AsyncClient(timeout=COMMAND_TIMEOUT) as client:
        response = await client.get(f"{APPIUM_HOST}/session/{session_id}/{endpoint.lstrip('/')}")

    if is_invalid_session_response(response):
        async with debug_session_lock(udid):
            debug_sessions.pop(udid, None)
        session_id, _ = await get_debug_session(udid)
        async with httpx.AsyncClient(timeout=COMMAND_TIMEOUT) as client:
            response = await client.get(f"{APPIUM_HOST}/session/{session_id}/{endpoint.lstrip('/')}")
        reused = False

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=sanitize_appium_error(response.text))

    data = response.json()
    value = data.get("value") if isinstance(data, dict) else None
    return value, reused


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
