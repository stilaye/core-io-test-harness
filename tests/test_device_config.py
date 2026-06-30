"""
Tests for core_io_monitor.device_config — loading device_config.yaml and
matching live devices against configured DUT/reference/auxiliary entries.

These run fully offline against the real device_config.yaml shipped in the
repo, plus synthetic device objects — no real hardware required.
"""

from __future__ import annotations

from core_io_monitor.device_config import (
    load_device_config,
    ConfiguredDevice,
    DeviceIdentifiers,
    DeviceExpectation,
)
from core_io_monitor.models import USBDevice, ThunderboltDevice, DeviceSnapshot, USBSpeed


class TestLoadDeviceConfig:
    def test_loads_without_error(self):
        config = load_device_config()
        assert config.dut_name == "MacBook Pro (DUT)"

    def test_parses_reference_devices(self):
        config = load_device_config()
        names = {d.name for d in config.reference_devices}
        assert "Reference USB3 Drive" in names
        assert "Reference Thunderbolt Dock" in names

    def test_parses_auxiliary_devices(self):
        config = load_device_config()
        names = {d.name for d in config.auxiliary_devices}
        assert "Apple Keyboard" in names
        assert "Apple Trackpad" in names

    def test_live_demo_settings_loaded(self):
        config = load_device_config()
        assert config.live_demo_duration_sec == 45.0
        assert config.live_demo_poll_interval_sec == 1.0

    def test_reference_usb_drive_has_expected_min_speed(self):
        config = load_device_config()
        drive = next(d for d in config.reference_devices if d.name == "Reference USB3 Drive")
        assert drive.expected.min_speed == USBSpeed.SUPER_SPEED


class TestConfiguredDeviceMatching:
    def test_matches_by_name_pattern(self):
        configured = ConfiguredDevice(
            name="Test Drive",
            role="reference",
            identifiers=DeviceIdentifiers(name_pattern="SanDisk|Samsung"),
        )
        live_device = USBDevice(name="SanDisk Extreme SSD", negotiated_speed=USBSpeed.SUPER_SPEED)
        assert configured.matches_usb(live_device) is True

    def test_does_not_match_unrelated_device(self):
        configured = ConfiguredDevice(
            name="Test Drive",
            role="reference",
            identifiers=DeviceIdentifiers(name_pattern="SanDisk|Samsung"),
        )
        live_device = USBDevice(name="Apple Keyboard", negotiated_speed=USBSpeed.FULL_SPEED)
        assert configured.matches_usb(live_device) is False

    def test_matches_by_exact_serial_number(self):
        configured = ConfiguredDevice(
            name="Test Drive",
            role="reference",
            identifiers=DeviceIdentifiers(serial_number="ABC123"),
        )
        live_device = USBDevice(name="Some Drive", serial_number="ABC123")
        assert configured.matches_usb(live_device) is True

    def test_matches_by_vendor_and_product_id(self):
        configured = ConfiguredDevice(
            name="Test Drive",
            role="reference",
            identifiers=DeviceIdentifiers(vendor_id="0x0781", product_id="0x5591"),
        )
        live_device = USBDevice(name="Unnamed", vendor_id="0x0781", product_id="0x5591")
        assert configured.matches_usb(live_device) is True

    def test_thunderbolt_matches_by_name_pattern(self):
        configured = ConfiguredDevice(
            name="Test Dock",
            role="reference",
            bus_type="Thunderbolt",
            identifiers=DeviceIdentifiers(name_pattern="Dock|Hub"),
        )
        live_device = ThunderboltDevice(name="CalDigit TS4 Dock")
        assert configured.matches_thunderbolt(live_device) is True


class TestFindReferenceMatch:
    def test_finds_reference_usb_device_in_snapshot(self):
        config = load_device_config()
        snapshot = DeviceSnapshot(
            timestamp=1.0,
            usb_devices=[
                USBDevice(name="SanDisk Extreme SSD", negotiated_speed=USBSpeed.SUPER_SPEED_PLUS),
                USBDevice(name="Apple Keyboard", negotiated_speed=USBSpeed.FULL_SPEED),
            ],
        )
        result = config.find_reference_usb_match(snapshot)
        assert result is not None
        configured, live = result
        assert configured.name == "Reference USB3 Drive"
        assert live.name == "SanDisk Extreme SSD"

    def test_returns_none_when_no_reference_device_present(self):
        config = load_device_config()
        snapshot = DeviceSnapshot(
            timestamp=1.0,
            usb_devices=[USBDevice(name="Apple Keyboard", negotiated_speed=USBSpeed.FULL_SPEED)],
        )
        result = config.find_reference_usb_match(snapshot)
        assert result is None


class TestSpeedExpectationCheck:
    def test_passes_when_speed_meets_minimum(self):
        config = load_device_config()
        drive_config = next(d for d in config.reference_devices if d.name == "Reference USB3 Drive")
        device = USBDevice(name="SanDisk Extreme SSD", negotiated_speed=USBSpeed.SUPER_SPEED_PLUS)

        passed, detail = config.check_speed_meets_expectation(drive_config, device)
        assert passed is True

    def test_fails_when_speed_below_minimum(self):
        config = load_device_config()
        drive_config = next(d for d in config.reference_devices if d.name == "Reference USB3 Drive")
        device = USBDevice(name="SanDisk Extreme SSD", negotiated_speed=USBSpeed.HIGH_SPEED)

        passed, detail = config.check_speed_meets_expectation(drive_config, device)
        assert passed is False
        assert "BELOW min" in detail
