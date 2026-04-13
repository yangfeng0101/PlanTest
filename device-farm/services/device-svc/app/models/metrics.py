# Device Metrics Models
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class MetricType(str, Enum):
    """Types of metrics"""
    CPU = "cpu"
    MEMORY = "memory"
    NETWORK = "network"
    BATTERY = "battery"
    TEMPERATURE = "temperature"


class DeviceMetrics(BaseModel):
    """Real-time device performance metrics"""
    device_id: str = Field(..., description="Device unique identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Metric collection timestamp")

    # CPU metrics
    cpu_usage: float = Field(default=0.0, ge=0, le=100, description="CPU usage percentage")
    cpu_cores: Optional[int] = Field(default=None, description="Number of CPU cores")

    # Memory metrics
    memory_usage: float = Field(default=0.0, ge=0, le=100, description="Memory usage percentage")
    memory_total_mb: Optional[int] = Field(default=None, description="Total memory in MB")
    memory_used_mb: Optional[int] = Field(default=None, description="Used memory in MB")
    memory_free_mb: Optional[int] = Field(default=None, description="Free memory in MB")

    # Network metrics
    network_rx_bytes: int = Field(default=0, description="Total received bytes")
    network_tx_bytes: int = Field(default=0, description="Total transmitted bytes")
    network_rx_speed_kbps: float = Field(default=0.0, description="Current download speed in KB/s")
    network_tx_speed_kbps: float = Field(default=0.0, description="Current upload speed in KB/s")

    # Battery metrics
    battery_level: int = Field(default=100, ge=0, le=100, description="Battery level percentage")
    battery_status: str = Field(default="unknown", description="Battery status: charging, discharging, full, unknown")
    battery_temperature: Optional[float] = Field(default=None, description="Battery temperature in Celsius")

    # Temperature metrics
    cpu_temperature: Optional[float] = Field(default=None, description="CPU temperature in Celsius")
    device_temperature: Optional[float] = Field(default=None, description="Overall device temperature in Celsius")

    # Additional info
    uptime_seconds: Optional[int] = Field(default=None, description="Device uptime in seconds")

    class Config:
        use_enum_values = True


class MetricsThreshold(BaseModel):
    """Threshold configuration for metric alerts"""
    metric_type: MetricType = Field(..., description="Type of metric")
    warning_threshold: float = Field(default=80.0, description="Warning threshold value")
    critical_threshold: float = Field(default=95.0, description="Critical threshold value")
    enabled: bool = Field(default=True, description="Whether threshold checking is enabled")


class DeviceThresholdConfig(BaseModel):
    """Threshold configuration for a specific device"""
    device_id: str = Field(..., description="Device unique identifier")
    cpu_warning: float = Field(default=80.0, description="CPU warning threshold %")
    cpu_critical: float = Field(default=95.0, description="CPU critical threshold %")
    memory_warning: float = Field(default=80.0, description="Memory warning threshold %")
    memory_critical: float = Field(default=95.0, description="Memory critical threshold %")
    battery_warning: float = Field(default=20.0, description="Battery warning threshold % (low battery)")
    battery_critical: float = Field(default=10.0, description="Battery critical threshold %")
    temperature_warning: float = Field(default=45.0, description="Temperature warning threshold in Celsius")
    temperature_critical: float = Field(default=55.0, description="Temperature critical threshold in Celsius")


class MetricAlert(BaseModel):
    """Alert triggered when metrics exceed thresholds"""
    id: str = Field(..., description="Alert unique identifier")
    device_id: str = Field(..., description="Device unique identifier")
    metric_type: MetricType = Field(..., description="Type of metric that triggered alert")
    severity: str = Field(..., description="Alert severity: warning or critical")
    value: float = Field(..., description="Actual metric value")
    threshold: float = Field(..., description="Threshold that was exceeded")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Alert timestamp")
    acknowledged: bool = Field(default=False, description="Whether alert has been acknowledged")


class MetricsHistoryQuery(BaseModel):
    """Query parameters for historical metrics"""
    device_id: str = Field(..., description="Device unique identifier")
    start_time: datetime = Field(..., description="Start time of query range")
    end_time: datetime = Field(default_factory=datetime.utcnow, description="End time of query range")
    metric_types: Optional[List[MetricType]] = Field(default=None, description="Filter by metric types")
    interval_seconds: int = Field(default=60, description="Aggregation interval in seconds")


class MetricsAggregation(BaseModel):
    """Aggregated metrics over a time period"""
    device_id: str = Field(..., description="Device unique identifier")
    start_time: datetime = Field(..., description="Start time of aggregation period")
    end_time: datetime = Field(..., description="End time of aggregation period")

    # CPU aggregation
    cpu_usage_avg: Optional[float] = Field(default=None, description="Average CPU usage")
    cpu_usage_max: Optional[float] = Field(default=None, description="Maximum CPU usage")
    cpu_usage_min: Optional[float] = Field(default=None, description="Minimum CPU usage")

    # Memory aggregation
    memory_usage_avg: Optional[float] = Field(default=None, description="Average memory usage")
    memory_usage_max: Optional[float] = Field(default=None, description="Maximum memory usage")
    memory_usage_min: Optional[float] = Field(default=None, description="Minimum memory usage")

    # Network aggregation
    network_rx_total_mb: Optional[float] = Field(default=None, description="Total received MB")
    network_tx_total_mb: Optional[float] = Field(default=None, description="Total transmitted MB")
    network_rx_avg_kbps: Optional[float] = Field(default=None, description="Average download speed KB/s")
    network_tx_avg_kbps: Optional[float] = Field(default=None, description="Average upload speed KB/s")

    # Battery aggregation
    battery_level_avg: Optional[float] = Field(default=None, description="Average battery level")
    battery_level_min: Optional[int] = Field(default=None, description="Minimum battery level")

    # Temperature aggregation
    temperature_avg: Optional[float] = Field(default=None, description="Average temperature")
    temperature_max: Optional[float] = Field(default=None, description="Maximum temperature")

    sample_count: int = Field(default=0, description="Number of samples in aggregation")


class MetricsSubscription(BaseModel):
    """WebSocket subscription for metrics updates"""
    device_ids: List[str] = Field(..., description="Device IDs to subscribe to")
    interval_seconds: int = Field(default=5, description="Update interval in seconds")
