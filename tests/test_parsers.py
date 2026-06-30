"""
Unit tests for core_io_monitor.parsers — verifying that raw
system_profiler-style JSON is correctly normalized into USBDevice objects.
"""

from core_io_monitor.parsers import parse_usb_data, parse_speed_string, parse_thunderbolt_data
from core_io_monitor.models import USBSpeed


class TestParseSpeedString:
    def test_high_speed(self):
        assert parse_speed_string("Up to 480 Mb/s") == USBSpeed.HIGH_SPEED

    def test_super_speed_plus(self):
        assert parse_speed_string("Up to 10 Gb/s") == USBSpeed.SUPER_SPEED_PLUS

    def test_usb4(self):
        assert parse_speed_string("Up to 40 Gb/s") == USBSpeed.USB4

    def test_unknown_string_returns_unknown(self):
        assert parse_speed_string("some weird future spec") == USBSpeed.UNKNOWN

    def test_none_returns_unknown(self):
        assert parse_speed_string(None) == USBSpeed.UNKNOWN

    def test_case_insensitive(self):
        assert parse_speed_string("UP TO 480 MB/S") == USBSpeed.HIGH_SPEED


class TestParseUsbData:
    def test_finds_all_devices_in_nested_tree(self, usb_json_before):
        devices = parse_usb_data(usb_json_before)
        names = {d.name for d in devices}
        assert "SanDisk Extreme SSD" in names
        assert "USB Keyboard" in names

    def test_skips_hub_nodes_without_serial(self, usb_json_before):
        # The hub itself has vendor_id/product_id so it IS captured —
        # but we can assert it has no serial number, distinguishing it
        # from a leaf storage/peripheral device.
        devices = parse_usb_data(usb_json_before)
        hub = next(d for d in devices if d.name == "USB3.1 Hub")
        assert hub.serial_number is None

    def test_extracts_vendor_and_product_id(self, usb_json_before):
        devices = parse_usb_data(usb_json_before)
        ssd = next(d for d in devices if d.name == "SanDisk Extreme SSD")
        assert ssd.vendor_id == "0x0781"
        assert ssd.product_id == "0x5591"

    def test_extracts_current_required(self, usb_json_before):
        devices = parse_usb_data(usb_json_before)
        ssd = next(d for d in devices if d.name == "SanDisk Extreme SSD")
        assert ssd.current_required_ma == 896

    def test_empty_input_returns_empty_list(self):
        assert parse_usb_data({"SPUSBDataType": []}) == []

    def test_malformed_input_does_not_raise(self):
        # Missing SPUSBDataType key entirely — should degrade gracefully.
        assert parse_usb_data({}) == []


class TestParseThunderboltData:
    def test_empty_thunderbolt_data(self):
        assert parse_thunderbolt_data({"SPThunderboltDataType": []}) == []

    def test_missing_key_does_not_raise(self):
        assert parse_thunderbolt_data({}) == []
