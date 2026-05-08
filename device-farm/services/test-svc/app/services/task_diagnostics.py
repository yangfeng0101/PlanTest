from typing import Any, Optional


INTERNAL_TASK_CAPABILITY_KEYS = {"_device_snapshot", "_appium_diagnostics"}


def build_device_snapshot(device: dict[str, Any]) -> dict[str, Any]:
    capabilities = device.get("capabilities") if isinstance(device.get("capabilities"), dict) else {}
    drivers = device.get("drivers") if isinstance(device.get("drivers"), dict) else {}

    return {
        "id": device.get("id"),
        "name": device.get("name"),
        "os": device.get("os"),
        "os_version": device.get("os_version"),
        "status": device.get("status"),
        "automation": bool(capabilities.get("automation")),
        "automation_status": device.get("automation_status"),
        "appium_ready": device.get("appium_ready"),
        "drivers": drivers,
    }


def merge_task_diagnostics(
    capabilities: Optional[dict[str, Any]],
    *,
    device: dict[str, Any],
    platform: str,
    device_id: Optional[str],
) -> dict[str, Any]:
    merged = dict(capabilities or {})
    for key in INTERNAL_TASK_CAPABILITY_KEYS:
        merged.pop(key, None)

    merged["_device_snapshot"] = build_device_snapshot(device)

    if platform == "ios":
        from app.drivers.appium import AppiumDriver

        driver = AppiumDriver(
            platform=platform,
            device_id=device_id,
            capabilities=merged,
        )
        merged["_appium_diagnostics"] = driver.sanitized_diagnostics()

    return merged
