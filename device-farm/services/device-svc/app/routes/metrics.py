# Metrics API Routes
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import logging
import httpx
import csv
import io
import json

from app.models import (
    DeviceMetrics,
    MetricsAggregation,
    DeviceThresholdConfig,
    MetricAlert,
)
from app.services.metrics_service import metrics_collector
from app.services import device_service
from app.services.threshold_service import threshold_service
from app.middleware.auth import get_current_user
from app.config import settings
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{device_id}", response_model=DeviceMetrics)
async def get_device_metrics(device_id: str):
    """
    Get current performance metrics for a specific device.

    Returns real-time metrics including CPU, memory, network, battery, and temperature.
    """
    # Check if device exists
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if not device.capabilities.metrics:
        raise HTTPException(status_code=400, detail="Metrics are not supported by this device connection")

    # Try to get cached metrics first
    metrics = metrics_collector.get_current_metrics(device_id)

    if not metrics:
        # Try to get from Redis
        metrics = await metrics_collector.get_cached_metrics(device_id)

    if not metrics:
        # Try to collect metrics now if device is online
        if device.status == "online":
            metrics = await metrics_collector.collect_device_metrics(device)
            if metrics:
                await metrics_collector.store_metrics(metrics)
        else:
            raise HTTPException(
                status_code=503,
                detail="Device is offline, metrics unavailable"
            )

    if not metrics:
        raise HTTPException(
            status_code=503,
            detail="Unable to collect metrics for device"
        )

    return metrics


@router.get("/{device_id}/history", response_model=List[DeviceMetrics])
async def get_device_metrics_history(
    device_id: str,
    start_time: Optional[datetime] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[datetime] = Query(None, description="End time (ISO format)"),
    hours: Optional[float] = Query(1, description="Hours to look back (default 1)"),
):
    """
    Get historical metrics for a device.

    Returns metrics within the specified time range.
    If start_time and end_time are not specified, returns the last N hours.
    """
    # Check if device exists
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if not device.capabilities.metrics:
        raise HTTPException(status_code=400, detail="Metrics are not supported by this device connection")

    # Determine time range
    if not end_time:
        end_time = datetime.utcnow()
    if not start_time:
        start_time = end_time - timedelta(hours=hours)

    # Validate time range
    if start_time >= end_time:
        raise HTTPException(
            status_code=400,
            detail="start_time must be before end_time"
        )

    # Get history from Redis
    metrics_history = await metrics_collector.get_metrics_history(
        device_id, start_time, end_time
    )

    return metrics_history


@router.get("/{device_id}/aggregation", response_model=MetricsAggregation)
async def get_device_metrics_aggregation(
    device_id: str,
    start_time: Optional[datetime] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[datetime] = Query(None, description="End time (ISO format)"),
    hours: Optional[float] = Query(1, description="Hours to aggregate (default 1)"),
):
    """
    Get aggregated metrics statistics for a device.

    Returns average, min, and max values for metrics over the specified time range.
    """
    # Check if device exists
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Determine time range
    if not end_time:
        end_time = datetime.utcnow()
    if not start_time:
        start_time = end_time - timedelta(hours=hours)

    # Get history
    metrics_history = await metrics_collector.get_metrics_history(
        device_id, start_time, end_time
    )

    if not metrics_history:
        return MetricsAggregation(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            sample_count=0
        )

    # Calculate aggregations
    cpu_values = [m.cpu_usage for m in metrics_history if m.cpu_usage > 0]
    memory_values = [m.memory_usage for m in metrics_history if m.memory_usage > 0]
    battery_values = [m.battery_level for m in metrics_history]
    temp_values = [m.device_temperature for m in metrics_history if m.device_temperature]

    # Network calculations
    if len(metrics_history) >= 2:
        first = metrics_history[0]
        last = metrics_history[-1]
        rx_total_mb = (last.network_rx_bytes - first.network_rx_bytes) / (1024 * 1024)
        tx_total_mb = (last.network_tx_bytes - first.network_tx_bytes) / (1024 * 1024)
    else:
        rx_total_mb = 0
        tx_total_mb = 0

    rx_speeds = [m.network_rx_speed_kbps for m in metrics_history if m.network_rx_speed_kbps > 0]
    tx_speeds = [m.network_tx_speed_kbps for m in metrics_history if m.network_tx_speed_kbps > 0]

    aggregation = MetricsAggregation(
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
        cpu_usage_avg=sum(cpu_values) / len(cpu_values) if cpu_values else None,
        cpu_usage_max=max(cpu_values) if cpu_values else None,
        cpu_usage_min=min(cpu_values) if cpu_values else None,
        memory_usage_avg=sum(memory_values) / len(memory_values) if memory_values else None,
        memory_usage_max=max(memory_values) if memory_values else None,
        memory_usage_min=min(memory_values) if memory_values else None,
        network_rx_total_mb=rx_total_mb,
        network_tx_total_mb=tx_total_mb,
        network_rx_avg_kbps=sum(rx_speeds) / len(rx_speeds) if rx_speeds else None,
        network_tx_avg_kbps=sum(tx_speeds) / len(tx_speeds) if tx_speeds else None,
        battery_level_avg=sum(battery_values) / len(battery_values) if battery_values else None,
        battery_level_min=min(battery_values) if battery_values else None,
        temperature_avg=sum(temp_values) / len(temp_values) if temp_values else None,
        temperature_max=max(temp_values) if temp_values else None,
        sample_count=len(metrics_history)
    )

    return aggregation


@router.get("", response_model=List[DeviceMetrics])
async def get_all_device_metrics():
    """
    Get current metrics for all devices.

    Returns the latest cached metrics for all devices.
    """
    all_metrics = metrics_collector.get_all_current_metrics()
    return list(all_metrics.values())


@router.post("/{device_id}/collect", response_model=DeviceMetrics)
async def collect_device_metrics_now(
    device_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Force immediate metrics collection for a device.

    Triggers an on-demand metrics collection and returns the results.
    Requires authentication.
    """
    # Check if device exists
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if device.status != "online":
        raise HTTPException(
            status_code=503,
            detail="Device is offline, cannot collect metrics"
        )

    # Collect metrics
    metrics = await metrics_collector.collect_device_metrics(device)

    if not metrics:
        raise HTTPException(
            status_code=500,
            detail="Failed to collect metrics for device"
        )

    # Store metrics
    await metrics_collector.store_metrics(metrics)

    # Check thresholds and trigger alerts if needed
    await check_thresholds_and_alert(metrics, device_id)

    return metrics


# === Threshold Configuration API ===

@router.get("/{device_id}/thresholds", response_model=DeviceThresholdConfig)
async def get_device_thresholds(
    device_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get threshold configuration for a device.

    Returns warning and critical thresholds for CPU, memory, battery, and temperature.
    """
    # Check if device exists
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Get from database or return default
    return await threshold_service.get_threshold(db, device_id)


@router.put("/{device_id}/thresholds", response_model=DeviceThresholdConfig)
async def update_device_thresholds(
    device_id: str,
    config: DeviceThresholdConfig,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update threshold configuration for a device.

    Allows setting custom warning and critical thresholds for performance metrics.
    Requires authentication.
    """
    # Check if device exists
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Validate thresholds
    if config.cpu_warning >= config.cpu_critical:
        raise HTTPException(
            status_code=400,
            detail="CPU warning threshold must be less than critical threshold"
        )
    if config.memory_warning >= config.memory_critical:
        raise HTTPException(
            status_code=400,
            detail="Memory warning threshold must be less than critical threshold"
        )
    if config.battery_warning <= config.battery_critical:
        raise HTTPException(
            status_code=400,
            detail="Battery warning threshold must be greater than critical threshold"
        )
    if config.temperature_warning >= config.temperature_critical:
        raise HTTPException(
            status_code=400,
            detail="Temperature warning threshold must be less than critical threshold"
        )

    # Save to database
    config.device_id = device_id
    saved_config = await threshold_service.set_threshold(db, device_id, config)

    logger.info(f"Updated threshold config for device {device_id} by {current_user.get('username', 'unknown')}")

    return saved_config


@router.post("/{device_id}/thresholds/reset", response_model=DeviceThresholdConfig)
async def reset_device_thresholds(
    device_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Reset threshold configuration to defaults.

    Requires authentication.
    """
    # Check if device exists
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Delete from database to reset to defaults
    await threshold_service.delete_threshold(db, device_id)

    logger.info(f"Reset threshold config for device {device_id} by {current_user.get('username', 'unknown')}")

    # Return default config
    return DeviceThresholdConfig(device_id=device_id)


@router.get("/{device_id}/alerts", response_model=List[MetricAlert])
async def get_device_metric_alerts(
    device_id: str,
    limit: int = Query(50, ge=1, le=200),
):
    """
    Get recent metric alerts for a device.

    Returns alerts triggered by threshold violations.
    """
    # Check if device exists
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Get cached alerts from metrics collector
    alerts = metrics_collector.get_device_alerts(device_id)

    return alerts[:limit]


async def check_thresholds_and_alert(metrics: DeviceMetrics, device_id: str):
    """
    Check metrics against thresholds and trigger alerts if exceeded.

    Integrates with the existing alert system in report-svc.
    """
    from app.database import get_db_session

    # Get threshold config from database
    async with get_db_session() as db:
        config = await threshold_service.get_threshold(db, device_id)
    alerts_to_trigger = []

    # CPU check
    if metrics.cpu_usage >= config.cpu_critical:
        alerts_to_trigger.append({
            "metric_type": "cpu",
            "severity": "critical",
            "value": metrics.cpu_usage,
            "threshold": config.cpu_critical,
        })
    elif metrics.cpu_usage >= config.cpu_warning:
        alerts_to_trigger.append({
            "metric_type": "cpu",
            "severity": "warning",
            "value": metrics.cpu_usage,
            "threshold": config.cpu_warning,
        })

    # Memory check
    if metrics.memory_usage >= config.memory_critical:
        alerts_to_trigger.append({
            "metric_type": "memory",
            "severity": "critical",
            "value": metrics.memory_usage,
            "threshold": config.memory_critical,
        })
    elif metrics.memory_usage >= config.memory_warning:
        alerts_to_trigger.append({
            "metric_type": "memory",
            "severity": "warning",
            "value": metrics.memory_usage,
            "threshold": config.memory_warning,
        })

    # Battery check (low battery is bad)
    if metrics.battery_level <= config.battery_critical:
        alerts_to_trigger.append({
            "metric_type": "battery",
            "severity": "critical",
            "value": metrics.battery_level,
            "threshold": config.battery_critical,
        })
    elif metrics.battery_level <= config.battery_warning:
        alerts_to_trigger.append({
            "metric_type": "battery",
            "severity": "warning",
            "value": metrics.battery_level,
            "threshold": config.battery_warning,
        })

    # Temperature check
    device_temp = metrics.device_temperature or metrics.cpu_temperature
    if device_temp:
        if device_temp >= config.temperature_critical:
            alerts_to_trigger.append({
                "metric_type": "temperature",
                "severity": "critical",
                "value": device_temp,
                "threshold": config.temperature_critical,
            })
        elif device_temp >= config.temperature_warning:
            alerts_to_trigger.append({
                "metric_type": "temperature",
                "severity": "warning",
                "value": device_temp,
                "threshold": config.temperature_warning,
            })

    # Trigger alerts
    for alert_data in alerts_to_trigger:
        await trigger_metric_alert(device_id, alert_data)


async def trigger_metric_alert(device_id: str, alert_data: dict):
    """
    Trigger an alert by calling the report-svc alert API.
    """
    try:
        async with httpx.AsyncClient() as client:
            # Create alert payload
            metric_type = alert_data["metric_type"]
            severity = alert_data["severity"]
            value = alert_data["value"]
            threshold = alert_data["threshold"]

            title = f"设备 {device_id} {metric_type.upper()} {'严重告警' if severity == 'critical' else '警告'}"
            message = f"{metric_type.upper()} 使用率 {value:.1f}% 超过{'严重' if severity == 'critical' else '警告'}阈值 {threshold}%"

            # Call alert service
            response = await client.post(
                f"{settings.REPORT_SVC_URL}/api/v1/alerts/trigger",
                params={
                    "rule_id": f"metric_{metric_type}_{severity}",
                    "title": title,
                    "message": message,
                    "device_id": device_id,
                },
                timeout=5.0,
            )

            if response.status_code == 200:
                logger.info(f"Triggered {severity} alert for {device_id} {metric_type}: {value:.1f}%")
            else:
                logger.warning(f"Failed to trigger alert: {response.status_code}")

    except Exception as e:
        logger.error(f"Error triggering metric alert: {e}")


# === Export API ===

@router.post("/export")
async def export_metrics(
    device_ids: Optional[List[str]] = Query(None, description="Device IDs to export (empty for all)"),
    start_time: Optional[datetime] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[datetime] = Query(None, description="End time (ISO format)"),
    hours: Optional[float] = Query(1, description="Hours to look back (default 1)"),
    format: str = Query("json", description="Export format: json or csv"),
):
    """
    Export metrics data in JSON or CSV format.

    Supports filtering by device IDs and time range.
    """
    # Determine time range
    if not end_time:
        end_time = datetime.utcnow()
    if not start_time:
        start_time = end_time - timedelta(hours=hours)

    # Validate time range
    if start_time >= end_time:
        raise HTTPException(
            status_code=400,
            detail="start_time must be before end_time"
        )

    # Get all devices or specified ones
    if device_ids:
        devices = []
        for device_id in device_ids:
            device = await device_service.get_device(device_id)
            if device:
                devices.append(device)
    else:
        devices = await device_service.get_all_devices()

    if not devices:
        raise HTTPException(status_code=404, detail="No devices found")

    # Collect metrics for each device
    all_metrics = []
    for device in devices:
        metrics_history = await metrics_collector.get_metrics_history(
            device.id, start_time, end_time
        )
        for m in metrics_history:
            all_metrics.append({
                "device_id": m.device_id,
                "device_name": device.name,
                "timestamp": m.timestamp.isoformat(),
                "cpu_usage": m.cpu_usage,
                "cpu_cores": m.cpu_cores,
                "memory_usage": m.memory_usage,
                "memory_total_mb": m.memory_total_mb,
                "memory_used_mb": m.memory_used_mb,
                "memory_free_mb": m.memory_free_mb,
                "network_rx_bytes": m.network_rx_bytes,
                "network_tx_bytes": m.network_tx_bytes,
                "network_rx_speed_kbps": m.network_rx_speed_kbps,
                "network_tx_speed_kbps": m.network_tx_speed_kbps,
                "battery_level": m.battery_level,
                "battery_status": m.battery_status,
                "battery_temperature": m.battery_temperature,
                "cpu_temperature": m.cpu_temperature,
                "device_temperature": m.device_temperature,
                "uptime_seconds": m.uptime_seconds,
            })

    if not all_metrics:
        raise HTTPException(
            status_code=404,
            detail="No metrics data found for the specified criteria"
        )

    # Generate export file
    if format.lower() == "csv":
        # Create CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=all_metrics[0].keys())
        writer.writeheader()
        writer.writerows(all_metrics)

        # Generate filename
        filename = f"metrics_export_{start_time.strftime('%Y%m%d_%H%M')}_{end_time.strftime('%Y%m%d_%H%M')}.csv"

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    else:
        # Return JSON
        filename = f"metrics_export_{start_time.strftime('%Y%m%d_%H%M')}_{end_time.strftime('%Y%m%d_%H%M')}.json"

        return StreamingResponse(
            iter([json.dumps(all_metrics, indent=2)]),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
