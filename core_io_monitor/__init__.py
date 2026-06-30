"""
core_io_monitor
================

An IOKit-backed monitor and diff engine for USB and Thunderbolt device
state on macOS, built as a proof-of-concept for Core I/O Quality
Engineering test infrastructure.

Modules:
    models       — normalized dataclasses (USBDevice, ThunderboltDevice, DeviceEvent, ...)
    parsers      — convert raw system_profiler JSON into normalized models
    collectors   — subprocess wrappers around system_profiler / ioreg
    diff_engine  — compares snapshots and emits attach/detach/anomaly events
    monitor      — orchestration layer: polling loop + structured logging
"""

from .models import (
    USBDevice,
    ThunderboltDevice,
    DeviceSnapshot,
    DeviceEvent,
    USBSpeed,
    BusType,
)
from .monitor import DeviceMonitor
from .device_config import DeviceConfig, ConfiguredDevice, load_device_config

__all__ = [
    "USBDevice",
    "ThunderboltDevice",
    "DeviceSnapshot",
    "DeviceEvent",
    "USBSpeed",
    "BusType",
    "DeviceMonitor",
    "DeviceConfig",
    "ConfiguredDevice",
    "load_device_config",
]

__version__ = "0.1.0"
