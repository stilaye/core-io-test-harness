"""
Shared pytest fixtures for the core-io-test-harness suite.

Fixtures here mirror the pattern used in DeCAF/netqual: load static JSON
fixtures from disk so the full parsing + diffing pipeline can be exercised
without needing a real Mac, real USB hardware, or root/sudo access. This
mirrors how the Core I/O team would want CI-safe tests that still validate
real protocol-level logic.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core_io_monitor.monitor import DeviceMonitor
from core_io_monitor.models import USBDevice, USBSpeed, BusType

SAMPLE_DATA_DIR = Path(__file__).parent.parent / "sample_data"


def _load_json(filename: str) -> dict:
    with open(SAMPLE_DATA_DIR / filename) as f:
        return json.load(f)


@pytest.fixture
def usb_json_before() -> dict:
    """Baseline USB bus state: SSD + keyboard attached."""
    return _load_json("usb_snapshot_before.json")


@pytest.fixture
def usb_json_after() -> dict:
    """USB bus state after SSD was unplugged and a webcam plugged in."""
    return _load_json("usb_snapshot_after.json")


@pytest.fixture
def monitor() -> DeviceMonitor:
    """A DeviceMonitor instance with no real polling (used for snapshot/diff calls)."""
    return DeviceMonitor(poll_interval_sec=0.0)


@pytest.fixture
def snapshot_before(monitor, usb_json_before):
    return monitor.snapshot_from_json(usb_json=usb_json_before, timestamp=1000.0)


@pytest.fixture
def snapshot_after(monitor, usb_json_after):
    return monitor.snapshot_from_json(usb_json=usb_json_after, timestamp=1002.0)


@pytest.fixture
def downgraded_usb_device() -> USBDevice:
    """
    A synthetic device that negotiated USB 2.0 High Speed despite supporting
    USB 3.1 SuperSpeed+ — simulates a bad cable, dirty contacts, or a hub
    that can't deliver full bandwidth. This is the #1 real-world USB bug
    pattern flagged in the field.
    """
    return USBDevice(
        name="Generic USB3 Storage",
        vendor_id="0x1234",
        product_id="0x5678",
        serial_number="SIM-DOWNGRADE-001",
        negotiated_speed=USBSpeed.HIGH_SPEED,
        max_supported_speed=USBSpeed.SUPER_SPEED_PLUS,
        bus_type=BusType.USB,
    )
