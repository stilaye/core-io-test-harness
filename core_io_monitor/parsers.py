"""
Parsers for macOS hardware-introspection command output.

These functions take the *parsed JSON* (from `system_profiler -json`) or raw
text (from `ioreg`) and convert it into the normalized dataclasses in
`models.py`. Parsing is kept separate from subprocess invocation
(`collectors.py`) so it can be unit tested with static fixture files,
without needing real macOS hardware or even macOS itself.
"""

from __future__ import annotations

import time
from typing import Any

from .models import USBDevice, ThunderboltDevice, DeviceSnapshot, USBSpeed, BusType


_SPEED_TEXT_MAP = {
    "up to 1.5 mb/s": USBSpeed.LOW_SPEED,
    "up to 12 mb/s": USBSpeed.FULL_SPEED,
    "up to 480 mb/s": USBSpeed.HIGH_SPEED,
    "up to 5 gb/s": USBSpeed.SUPER_SPEED,
    "up to 10 gb/s": USBSpeed.SUPER_SPEED_PLUS,
    "up to 20 gb/s": USBSpeed.SUPER_SPEED_20,
    "up to 40 gb/s": USBSpeed.USB4,
    "up to 80 gb/s": USBSpeed.USB4_V2,
}


def parse_speed_string(speed_str: str | None) -> USBSpeed:
    """Map system_profiler's human-readable speed string to a USBSpeed enum."""
    if not speed_str:
        return USBSpeed.UNKNOWN
    normalized = speed_str.strip().lower()
    return _SPEED_TEXT_MAP.get(normalized, USBSpeed.UNKNOWN)


def _walk_usb_tree(node: dict[str, Any]) -> list[USBDevice]:
    """
    Recursively walk the `system_profiler SPUSBDataType -json` tree.

    Each node may contain `_items` (children) and device-specific keys like
    `vendor_id`, `product_id`, `serial_num`, `bcd_device`, etc. depending on
    macOS version. We extract what's present and leave the rest in `raw`.
    """
    devices: list[USBDevice] = []

    name = node.get("_name", "Unknown Device")
    is_real_device = "vendor_id" in node or "product_id" in node

    if is_real_device:
        device = USBDevice(
            name=name,
            vendor_id=node.get("vendor_id"),
            product_id=node.get("product_id"),
            serial_number=node.get("serial_num"),
            location_id=node.get("location_id"),
            negotiated_speed=parse_speed_string(node.get("device_speed")),
            max_supported_speed=parse_speed_string(node.get("device_speed")),
            current_required_ma=_parse_ma(node.get("current_required")),
            extra_op_required_ma=_parse_ma(node.get("extra_operating_current")),
            manufacturer=node.get("manufacturer"),
            bus_type=BusType.USB,
            raw=node,
        )
        devices.append(device)

    for child in node.get("_items", []):
        devices.extend(_walk_usb_tree(child))

    return devices


def _parse_ma(value: str | None) -> int | None:
    """Parse strings like '500 mA' -> 500."""
    if not value:
        return None
    digits = "".join(c for c in value if c.isdigit())
    return int(digits) if digits else None


def parse_usb_data(system_profiler_json: dict[str, Any]) -> list[USBDevice]:
    """
    Entry point for parsing `system_profiler SPUSBDataType -json` output.

    Expected top-level shape:
        {"SPUSBDataType": [ {controller node with _items}, ... ]}
    """
    devices: list[USBDevice] = []
    for controller in system_profiler_json.get("SPUSBDataType", []):
        devices.extend(_walk_usb_tree(controller))
    return devices


def _walk_thunderbolt_tree(node: dict[str, Any]) -> list[ThunderboltDevice]:
    devices: list[ThunderboltDevice] = []

    name = node.get("_name", "Unknown Thunderbolt Device")
    is_real_device = "device_id_key" in node or "vendor_id_key" in node or "receptacle_1_tb" in node

    if is_real_device or "device_name_key" in node:
        link_speed = node.get("current_speed_key") or node.get("speed_key")
        device = ThunderboltDevice(
            name=name,
            device_id=node.get("device_id_key"),
            vendor_id=node.get("vendor_id_key"),
            link_speed_gbps=_parse_gbps(link_speed),
            link_width=node.get("link_width_key"),
            is_pcie_tunnel=bool(node.get("receptacle_1_tb")),
            raw=node,
        )
        devices.append(device)

    for child in node.get("_items", []):
        devices.extend(_walk_thunderbolt_tree(child))

    return devices


def _parse_gbps(value: str | None) -> float | None:
    """Parse strings like 'Up to 40 Gb/s x2' -> 40.0."""
    if not value:
        return None
    import re
    match = re.search(r"(\d+(?:\.\d+)?)\s*Gb/s", value)
    return float(match.group(1)) if match else None


def parse_thunderbolt_data(system_profiler_json: dict[str, Any]) -> list[ThunderboltDevice]:
    """
    Entry point for parsing `system_profiler SPThunderboltDataType -json` output.

    Expected top-level shape:
        {"SPThunderboltDataType": [ {bus node with _items}, ... ]}
    """
    devices: list[ThunderboltDevice] = []
    for bus_node in system_profiler_json.get("SPThunderboltDataType", []):
        devices.extend(_walk_thunderbolt_tree(bus_node))
    return devices


def build_snapshot(
    usb_json: dict[str, Any] | None = None,
    thunderbolt_json: dict[str, Any] | None = None,
    timestamp: float | None = None,
) -> DeviceSnapshot:
    """Build a normalized DeviceSnapshot from raw system_profiler JSON blobs."""
    return DeviceSnapshot(
        timestamp=timestamp if timestamp is not None else time.time(),
        usb_devices=parse_usb_data(usb_json) if usb_json else [],
        thunderbolt_devices=parse_thunderbolt_data(thunderbolt_json) if thunderbolt_json else [],
    )
