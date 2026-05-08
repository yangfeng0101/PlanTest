import asyncio
import json
import os
import sys
from typing import Any

import httpx
from fastapi import FastAPI


APPIUM_HOST = os.getenv("IOS_APPIUM_HOST", "http://127.0.0.1:4724").rstrip("/")
COMMAND_TIMEOUT = float(os.getenv("IOS_AGENT_COMMAND_TIMEOUT", "20"))
AUTOMATION_READY_UDIDS = {
    udid.strip()
    for udid in os.getenv("IOS_AGENT_AUTOMATION_READY_UDIDS", "").split(",")
    if udid.strip()
}

app = FastAPI(title="Device Farm iOS Agent", version="0.1.0")


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
