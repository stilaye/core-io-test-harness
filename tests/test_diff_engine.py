"""
Unit tests for core_io_monitor.diff_engine — the core anomaly-detection
logic that the live DeviceMonitor relies on.

These tests use the before/after snapshot fixtures (an SSD that gets
unplugged and a webcam that gets plugged in) to verify attach/detach
detection, plus a synthetic "speed downgrade" device to verify the
bandwidth-regression detector — the #1 real-world USB QE bug pattern.
"""

from core_io_monitor.diff_engine import diff_usb_snapshots, diff_snapshots
from core_io_monitor.models import DeviceSnapshot, USBSpeed, BusType


class TestAttachDetachDetection:
    def test_detects_detached_device(self, snapshot_before, snapshot_after):
        events = diff_usb_snapshots(snapshot_before, snapshot_after)
        detach_events = [e for e in events if e.event_type == "detach"]
        assert len(detach_events) == 1
        assert detach_events[0].device_name == "SanDisk Extreme SSD"

    def test_detects_attached_device(self, snapshot_before, snapshot_after):
        events = diff_usb_snapshots(snapshot_before, snapshot_after)
        attach_events = [e for e in events if e.event_type == "attach"]
        assert len(attach_events) == 1
        assert attach_events[0].device_name == "Logitech Webcam"

    def test_unchanged_device_produces_no_event(self, snapshot_before, snapshot_after):
        events = diff_usb_snapshots(snapshot_before, snapshot_after)
        keyboard_events = [e for e in events if e.device_name == "USB Keyboard"]
        assert keyboard_events == []

    def test_identical_snapshots_produce_no_events(self, snapshot_before):
        events = diff_usb_snapshots(snapshot_before, snapshot_before)
        assert events == []

    def test_events_carry_correct_bus_type(self, snapshot_before, snapshot_after):
        events = diff_usb_snapshots(snapshot_before, snapshot_after)
        assert all(e.bus_type == BusType.USB for e in events)

    def test_events_are_chronologically_sorted(self, snapshot_before, snapshot_after):
        events = diff_snapshots(snapshot_before, snapshot_after)
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)


class TestSpeedDowngradeDetection:
    def test_flags_device_with_downgraded_speed(self, downgraded_usb_device):
        from core_io_monitor.models import DeviceSnapshot

        before = DeviceSnapshot(timestamp=1.0, usb_devices=[])
        after = DeviceSnapshot(timestamp=2.0, usb_devices=[downgraded_usb_device])

        events = diff_usb_snapshots(before, after)
        # Should fire an "attach" event since this is the device's first appearance
        assert any(e.event_type == "attach" for e in events)

    def test_speed_downgrade_flagged_on_existing_device(self):
        """
        Simulates a device that was already connected at full speed,
        then re-negotiates down to a lower speed on a later poll —
        e.g. after a cable reseat or controller power event.
        """
        from core_io_monitor.models import USBDevice

        device_fast = USBDevice(
            name="External Dock",
            serial_number="DOCK-001",
            negotiated_speed=USBSpeed.SUPER_SPEED_PLUS,
            max_supported_speed=USBSpeed.SUPER_SPEED_PLUS,
        )
        device_slow = USBDevice(
            name="External Dock",
            serial_number="DOCK-001",
            negotiated_speed=USBSpeed.HIGH_SPEED,
            max_supported_speed=USBSpeed.SUPER_SPEED_PLUS,
        )

        before = DeviceSnapshot(timestamp=1.0, usb_devices=[device_fast])
        after = DeviceSnapshot(timestamp=2.0, usb_devices=[device_slow])

        events = diff_usb_snapshots(before, after)
        downgrade_events = [e for e in events if e.event_type == "speed_downgrade"]
        assert len(downgrade_events) == 1
        assert "negotiated=high_speed" in downgrade_events[0].detail
        assert "max_supported=super_speed_plus" in downgrade_events[0].detail


class TestDeviceEventSerialization:
    def test_to_dict_produces_json_serializable_output(self, snapshot_before, snapshot_after):
        import json

        events = diff_snapshots(snapshot_before, snapshot_after)
        for event in events:
            # Should not raise — confirms structure is clean for JSONL logging
            serialized = json.dumps(event.to_dict())
            assert isinstance(serialized, str)
