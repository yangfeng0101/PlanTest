# Metrics API Routes
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from datetime import datetime, timedelta
import logging

from app.models import (
    DeviceMetrics,
    MetricsAggregation,
    DeviceThresholdConfig,
    MetricAlert,
)
from app.services.metrics_service import metrics_collector
from app.services import device_service
from app.middleware.auth import get_current_user

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
    hours: Optional[int] = Query(1, description="Hours to look back (default 1)"),
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
    hours: Optional[int] = Query(1, description="Hours to aggregate (default 1)"),
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

    return metrics
