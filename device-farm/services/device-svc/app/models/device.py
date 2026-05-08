# Device Service - Device Models
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class DeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    MAINTAINING = "maintaining"
    MAINTENANCE = "maintenance"  # Legacy alias


class DeviceDrivers(BaseModel):
    """Runtime drivers used by each device capability."""
    metrics: str = Field(default="", description="Metrics collection driver")
    screen: str = Field(default="", description="Screen streaming driver")
    ui_hierarchy: str = Field(default="", description="UI hierarchy driver")
    control: str = Field(default="", description="Remote control driver")
    automation: str = Field(default="", description="Automation execution driver")


class DeviceCapabilities(BaseModel):
    """Runtime capabilities derived from current connection and drivers."""
    screen_mirror: bool = False
    remote_control: bool = False
    ui_hierarchy: bool = False
    metrics: bool = False
    screenshot: bool = False
    app_management: bool = False
    automation: bool = False


class Device(BaseModel):
    """Device model"""
    id: str = Field(..., description="Device unique identifier (serial number)")
    name: str = Field(..., description="Device name")
    model: str = Field(..., description="Device model")
    brand: str = Field(..., description="Device brand")
    os: str = Field(default="android", description="Operating system")
    os_version: str = Field(..., description="OS version")
    status: DeviceStatus = Field(default=DeviceStatus.ONLINE, description="Device status")

    # Hardware info
    screen_resolution: str = Field(..., description="Screen resolution (e.g., 1080x1920)")
    screen_size: float = Field(..., description="Screen size in inches")
    cpu: str = Field(..., description="CPU info")
    memory: str = Field(..., description="Memory size")
    storage: str = Field(..., description="Storage size")
    battery_level: int = Field(default=100, description="Battery level (0-100)")

    # Occupation info
    occupied_by: Optional[str] = Field(default=None, description="User who occupied the device")
    occupied_at: Optional[datetime] = Field(default=None, description="Occupation timestamp")

    # Timestamps
    last_active_at: datetime = Field(default_factory=datetime.now, description="Last active time")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Tags
    tags: List[str] = Field(default_factory=list, description="Device tags")

    # Thumbnail
    thumbnail: Optional[str] = Field(default=None, description="Device thumbnail URL")

    # Runtime display/capability info. These fields are not persisted.
    display_os: str = Field(default="", description="User-facing OS name")
    display_os_version: str = Field(default="", description="User-facing OS version")
    connection_type: str = Field(default="", description="Current connection type: adb, hdc, wda")
    drivers: DeviceDrivers = Field(default_factory=DeviceDrivers, description="Runtime driver mapping")
    capabilities: DeviceCapabilities = Field(default_factory=DeviceCapabilities, description="Runtime capability flags")

    class Config:
        use_enum_values = True

    def model_post_init(self, __context) -> None:
        self.refresh_runtime_fields()

    def refresh_runtime_fields(self) -> None:
        """Derive user-facing platform fields separately from runtime drivers."""
        normalized_os = (self.os or "").lower()

        if normalized_os == "harmony":
            self.display_os = "HarmonyOS"
            self.display_os_version = self.os_version
            self.connection_type = "adb"
            self.drivers = DeviceDrivers(
                metrics="adb",
                screen="scrcpy",
                ui_hierarchy="uiautomator",
                control="scrcpy",
                automation="appium-uiautomator2",
            )
        elif normalized_os == "android":
            self.display_os = "Android"
            self.display_os_version = self.os_version
            self.connection_type = "adb"
            self.drivers = DeviceDrivers(
                metrics="adb",
                screen="scrcpy",
                ui_hierarchy="uiautomator",
                control="scrcpy",
                automation="appium-uiautomator2",
            )
        elif normalized_os == "ios":
            self.display_os = "iOS"
            self.display_os_version = self.os_version
            self.connection_type = "wda"
            self.drivers = DeviceDrivers(
                metrics="pymobiledevice3",
            )
        else:
            self.display_os = self.os or "Unknown"
            self.display_os_version = self.os_version or "Unknown"
            self.connection_type = ""
            self.drivers = DeviceDrivers()

        self.capabilities = DeviceCapabilities(
            screen_mirror=bool(self.drivers.screen),
            remote_control=bool(self.drivers.control),
            ui_hierarchy=bool(self.drivers.ui_hierarchy),
            metrics=bool(self.drivers.metrics),
            screenshot=self.connection_type == "adb",
            app_management=self.connection_type == "adb",
            automation=bool(self.drivers.automation),
        )


class DeviceCreate(BaseModel):
    """Device creation model"""
    name: str
    model: str
    brand: str
    os_version: str
    screen_resolution: str
    screen_size: float
    cpu: str
    memory: str
    storage: str
    tags: List[str] = []


class DeviceUpdate(BaseModel):
    """Device update model"""
    name: Optional[str] = None
    status: Optional[DeviceStatus] = None
    tags: Optional[List[str]] = None


class DeviceOccupyRequest(BaseModel):
    """Device occupy request"""
    user_id: Optional[str] = Field(default=None, description="User ID who wants to occupy")
    duration: Optional[int] = Field(default=None, description="Occupation duration in minutes")


class DeviceListResponse(BaseModel):
    """Device list response"""
    devices: List[Device]
    total: int


class DeviceFilter(BaseModel):
    """Device filter parameters"""
    status: Optional[DeviceStatus] = None
    brand: Optional[str] = None
    os_version: Optional[str] = None
    keyword: Optional[str] = None
    tags: Optional[List[str]] = None
