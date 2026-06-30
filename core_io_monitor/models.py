"""
Data models for USB and Thunderbolt device state.

These dataclasses normalize the raw output of `system_profiler` and `ioreg`
into a stable shape that the rest of the framework (monitor, parsers, tests)
can depend on regardless of macOS version differences in CLI output format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BusType(str, Enum):
    USB = "USB"
    THUNDERBOLT = "Thunderbolt"
    PCIE = "PCIe"
    UNKNOWN = "Unknown"


class USBSpeed(str, Enum):
    LOW_SPEED = "low_speed"          # 1.5 Mbps
    FULL_SPEED = "full_speed"        # 12 Mbps
    HIGH_SPEED = "high_speed"        # 480 Mbps  (USB 2.0)
    SUPER_SPEED = "super_speed"      # 5 Gbps    (USB 3.0 / 3.1 Gen1)
    SUPER_SPEED_PLUS = "super_speed_plus"  # 10 Gbps (USB 3.1 Gen2)
    SUPER_SPEED_20 = "super_speed_20"      # 20 Gbps (USB 3.2 Gen2x2)
    USB4 = "usb4"                    # 40 Gbps
    USB4_V2 = "usb4_v2"              # 80 Gbps (Thunderbolt 5 territory)
    UNKNOWN = "unknown"


# Ordering used to detect "speed downgrade" anomalies.
_SPEED_RANK = {
    USBSpeed.LOW_SPEED: 0,
    USBSpeed.FULL_SPEED: 1,
    USBSpeed.HIGH_SPEED: 2,
    USBSpeed.SUPER_SPEED: 3,
    USBSpeed.SUPER_SPEED_PLUS: 4,
    USBSpeed.SUPER_SPEED_20: 5,
    USBSpeed.USB4: 6,
    USBSpeed.USB4_V2: 7,
    USBSpeed.UNKNOWN: -1,
}


def speed_rank(speed: USBSpeed) -> int:
    return _SPEED_RANK.get(speed, -1)


@dataclass
class USBDevice:
    """Normalized representation of a single USB device node."""
    name: str
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    serial_number: Optional[str] = None
    location_id: Optional[str] = None
    negotiated_speed: USBSpeed = USBSpeed.UNKNOWN
    max_supported_speed: USBSpeed = USBSpeed.UNKNOWN
    current_required_ma: Optional[int] = None
    extra_op_required_ma: Optional[int] = None
    manufacturer: Optional[str] = None
    bus_type: BusType = BusType.USB
    raw: dict = field(default_factory=dict)

    @property
    def is_speed_downgraded(self) -> bool:
        """True if the device negotiated a lower speed than it supports."""
        if self.max_supported_speed == USBSpeed.UNKNOWN:
            return False
        return speed_rank(self.negotiated_speed) < speed_rank(self.max_supported_speed)

    @property
    def identity(self) -> str:
        """Stable identity key for diffing across snapshots."""
        return self.serial_number or self.location_id or f"{self.vendor_id}:{self.product_id}:{self.name}"


@dataclass
class ThunderboltDevice:
    """Normalized representation of a Thunderbolt/USB4 device node."""
    name: str
    device_id: Optional[str] = None
    vendor_id: Optional[str] = None
    link_speed_gbps: Optional[float] = None
    link_width: Optional[str] = None
    is_pcie_tunnel: bool = False
    receptacle_count: Optional[int] = None
    raw: dict = field(default_factory=dict)

    @property
    def identity(self) -> str:
        return self.device_id or self.name


@dataclass
class DeviceSnapshot:
    """A point-in-time capture of all USB + Thunderbolt devices on the bus."""
    timestamp: float
    usb_devices: list[USBDevice] = field(default_factory=list)
    thunderbolt_devices: list[ThunderboltDevice] = field(default_factory=list)

    def usb_by_identity(self) -> dict[str, USBDevice]:
        return {d.identity: d for d in self.usb_devices}

    def thunderbolt_by_identity(self) -> dict[str, ThunderboltDevice]:
        return {d.identity: d for d in self.thunderbolt_devices}


@dataclass
class DeviceEvent:
    """A detected change between two snapshots."""
    event_type: str          # "attach" | "detach" | "speed_downgrade" | "link_degraded"
    bus_type: BusType
    device_identity: str
    device_name: str
    timestamp: float
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "bus_type": self.bus_type.value,
            "device_identity": self.device_identity,
            "device_name": self.device_name,
            "timestamp": self.timestamp,
            "detail": self.detail,
        }
