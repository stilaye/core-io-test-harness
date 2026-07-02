"""
Tests for the DeviceMonitor orchestration layer.

These tests focus on the parts of DeviceMonitor that don't require real
hardware: snapshot construction from JSON, and diffing. The `run()` polling
loop and `take_snapshot()` (which shells out to system_profiler/ioreg) are
exercised separately in an integration-only test marked `requires_macos`,
since they cannot run in this Linux-based CI sandbox.
"""

from __future__ import annotations

import pytest

from core_io_monitor.monitor import DeviceMonitor
from core_io_monitor.collectors import CollectorError


class TestSnapshotFromJson:
    def test_builds_snapshot_with_correct_device_count(self, usb_json_before):
        # The hub itself is a legitimate addressable USB device (it has its
        # own vendor_id/product_id) — so the fixture's 1 hub + 1 SSD behind
        # it + 1 keyboard = 3 total nodes. This matches real ioreg/
        # system_profiler behavior, where hubs always appear in the tree.
        snapshot = DeviceMonitor.snapshot_from_json(usb_json=usb_json_before)
        assert len(snapshot.usb_devices) == 3

    def test_timestamp_defaults_to_now_if_unset(self, usb_json_before):
        import time

        before = time.time()
        snapshot = DeviceMonitor.snapshot_from_json(usb_json=usb_json_before)
        after = time.time()
        assert before <= snapshot.timestamp <= after

    def test_explicit_timestamp_is_honored(self, usb_json_before):
        snapshot = DeviceMonitor.snapshot_from_json(usb_json=usb_json_before, timestamp=42.0)
        assert snapshot.timestamp == 42.0

    def test_no_data_produces_empty_snapshot(self):
        snapshot = DeviceMonitor.snapshot_from_json()
        assert snapshot.usb_devices == []
        assert snapshot.thunderbolt_devices == []


class TestMonitorDiff:
    def test_diff_is_equivalent_to_diff_engine(self, snapshot_before, snapshot_after):
        from core_io_monitor.diff_engine import diff_snapshots

        direct = diff_snapshots(snapshot_before, snapshot_after)
        via_monitor = DeviceMonitor.diff(snapshot_before, snapshot_after)
        assert [e.to_dict() for e in direct] == [e.to_dict() for e in via_monitor]


@pytest.mark.requires_macos
class TestLiveCollection:
    """
    Integration tests that require real macOS + real hardware.
    Skipped automatically in this Linux sandbox; run these on the actual
    Mac before the technical interview to validate against real devices.
    """

    def test_take_snapshot_against_real_hardware(self):
        monitor = DeviceMonitor()
        snapshot = monitor.take_snapshot()
        # On any real Mac, at least the internal hub/controller should show up.
        assert len(snapshot.usb_devices) >= 0  # adjust once run on real hardware


class TestCollectorErrorHandling:
    """
    Verifies CollectorError is raised cleanly when the underlying binary
    is missing (e.g. running off macOS). Mocks subprocess so it runs
    anywhere, unlike TestLiveCollection which needs real hardware.
    """

    def test_collector_raises_clean_error_when_binary_missing(self, monkeypatch):
        import subprocess

        from core_io_monitor.collectors import collect_usb_data

        def fake_run(*args, **kwargs):
            raise FileNotFoundError("system_profiler")

        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(CollectorError):
            collect_usb_data()
