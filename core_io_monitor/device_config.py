"""
device_config: loads `device_config.yaml` and provides matching logic to
find a configured reference/auxiliary device within a live or fixture-based
DeviceSnapshot.

This is what turns "some USB device showed up" into "the specific reference
drive we declared in device_config.yaml showed up, and it's negotiating the
speed we expect it to" — the difference between a generic monitor and a
real hardware-in-the-loop test asset inventory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from .models import USBDevice, ThunderboltDevice, DeviceSnapshot, USBSpeed, speed_rank


DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "device_config.yaml"


@dataclass
class DeviceIdentifiers:
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    device_id: Optional[str] = None
    serial_number: Optional[str] = None
    name_pattern: Optional[str] = None


@dataclass
class DeviceExpectation:
    min_speed: Optional[USBSpeed] = None
    max_supported_speed: Optional[USBSpeed] = None
    min_link_speed_gbps: Optional[float] = None


@dataclass
class ConfiguredDevice:
    name: str
    role: str                      # "dut" | "reference" | "auxiliary"
    bus_type: str = "USB"
    identifiers: DeviceIdentifiers = field(default_factory=DeviceIdentifiers)
    expected: DeviceExpectation = field(default_factory=DeviceExpectation)
    notes: str = ""

    def matches_usb(self, device: USBDevice) -> bool:
        """Check whether a live USBDevice matches this configured device."""
        ids = self.identifiers

        if ids.serial_number and device.serial_number == ids.serial_number:
            return True
        if ids.vendor_id and ids.product_id:
            if device.vendor_id == ids.vendor_id and device.product_id == ids.product_id:
                return True
        if ids.name_pattern and re.search(ids.name_pattern, device.name, re.IGNORECASE):
            return True
        return False

    def matches_thunderbolt(self, device: ThunderboltDevice) -> bool:
        ids = self.identifiers
        if ids.device_id and device.device_id == ids.device_id:
            return True
        if ids.vendor_id and device.vendor_id == ids.vendor_id:
            return True
        if ids.name_pattern and re.search(ids.name_pattern, device.name, re.IGNORECASE):
            return True
        return False


@dataclass
class DeviceConfig:
    dut_name: str
    dut_chip: str
    reference_devices: list[ConfiguredDevice]
    auxiliary_devices: list[ConfiguredDevice]
    live_demo_poll_interval_sec: float = 1.0
    live_demo_duration_sec: float = 45.0
    live_demo_log_path: str = "events.jsonl"

    def find_reference_usb_match(self, snapshot: DeviceSnapshot) -> Optional[tuple[ConfiguredDevice, USBDevice]]:
        """Find the first live USB device matching any configured reference device."""
        for configured in self.reference_devices:
            if configured.bus_type != "USB":
                continue
            for live_device in snapshot.usb_devices:
                if configured.matches_usb(live_device):
                    return configured, live_device
        return None

    def find_reference_thunderbolt_match(
        self, snapshot: DeviceSnapshot
    ) -> Optional[tuple[ConfiguredDevice, ThunderboltDevice]]:
        for configured in self.reference_devices:
            if configured.bus_type != "Thunderbolt":
                continue
            for live_device in snapshot.thunderbolt_devices:
                if configured.matches_thunderbolt(live_device):
                    return configured, live_device
        return None

    def check_speed_meets_expectation(
        self, configured: ConfiguredDevice, device: USBDevice
    ) -> tuple[bool, str]:
        """
        Returns (passed, detail_message) — checks the live device's
        negotiated speed against the configured minimum expectation.
        """
        min_speed = configured.expected.min_speed
        if min_speed is None:
            return True, "no minimum speed configured"

        if speed_rank(device.negotiated_speed) >= speed_rank(min_speed):
            return True, f"negotiated={device.negotiated_speed.value} meets min={min_speed.value}"
        return False, f"negotiated={device.negotiated_speed.value} BELOW min={min_speed.value}"


def _parse_identifiers(raw: dict[str, Any]) -> DeviceIdentifiers:
    return DeviceIdentifiers(
        vendor_id=raw.get("vendor_id"),
        product_id=raw.get("product_id"),
        device_id=raw.get("device_id"),
        serial_number=raw.get("serial_number"),
        name_pattern=raw.get("name_pattern"),
    )


def _parse_expectation(raw: dict[str, Any]) -> DeviceExpectation:
    min_speed_str = raw.get("min_speed")
    max_speed_str = raw.get("max_supported_speed")
    return DeviceExpectation(
        min_speed=USBSpeed(min_speed_str) if min_speed_str else None,
        max_supported_speed=USBSpeed(max_speed_str) if max_speed_str else None,
        min_link_speed_gbps=raw.get("min_link_speed_gbps"),
    )


def _parse_device_list(raw_list: list[dict[str, Any]], role: str) -> list[ConfiguredDevice]:
    devices = []
    for raw in raw_list:
        devices.append(ConfiguredDevice(
            name=raw["name"],
            role=role,
            bus_type=raw.get("bus_type", "USB"),
            identifiers=_parse_identifiers(raw.get("identifiers", {})),
            expected=_parse_expectation(raw.get("expected", {})),
            notes=raw.get("notes", ""),
        ))
    return devices


def load_device_config(path: str | Path | None = None) -> DeviceConfig:
    """Load and parse device_config.yaml into a DeviceConfig object."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    dut_raw = raw.get("dut", {})
    live_demo_raw = raw.get("live_demo", {})

    return DeviceConfig(
        dut_name=dut_raw.get("name", "Unknown DUT"),
        dut_chip=dut_raw.get("chip", "unknown"),
        reference_devices=_parse_device_list(raw.get("reference_devices", []), role="reference"),
        auxiliary_devices=_parse_device_list(raw.get("auxiliary_devices", []), role="auxiliary"),
        live_demo_poll_interval_sec=live_demo_raw.get("poll_interval_sec", 1.0),
        live_demo_duration_sec=live_demo_raw.get("duration_sec", 45.0),
        live_demo_log_path=live_demo_raw.get("log_path", "events.jsonl"),
    )
