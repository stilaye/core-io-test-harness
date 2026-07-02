"""
Live USB drive tests — run these on real macOS hardware against your
configured reference USB drive (see device_config.yaml).

These are the tests to run during interview prep, and the ones to
screen-share if asked to demo "a real test, not just mocked data."

All tests here are marked `requires_macos` and auto-skip on non-Darwin
systems (see root conftest.py). Before running, plug in the USB drive you
configured in `device_config.yaml` under `reference_devices`.

Run just this file:
    pytest -v tests/test_usb_drive_live.py -m requires_macos
"""

from __future__ import annotations

import pytest

from core_io_monitor.monitor import DeviceMonitor
from core_io_monitor.device_config import load_device_config
from core_io_monitor.collectors import CollectorError


@pytest.mark.requires_macos
class TestReferenceUSBDriveDetection:
    """
    Validates that the configured reference USB drive is detected and
    meets its expected minimum negotiated speed. Requires the drive to be
    physically plugged in before running.
    """

    def test_reference_drive_is_detected(self):
        config = load_device_config()
        monitor = DeviceMonitor()

        try:
            snapshot = monitor.take_snapshot()
        except CollectorError as exc:
            pytest.skip(f"Could not collect live USB data: {exc}")

        result = config.find_reference_usb_match(snapshot)
        assert result is not None, (
            "Reference USB drive not found. Make sure it's plugged in and "
            "device_config.yaml's identifiers (vendor_id/product_id/serial_number/"
            "name_pattern) match your actual drive — check `system_profiler "
            "SPUSBDataType -json` output to fill these in."
        )

    def test_reference_drive_meets_minimum_speed(self):
        config = load_device_config()
        monitor = DeviceMonitor()

        try:
            snapshot = monitor.take_snapshot()
        except CollectorError as exc:
            pytest.skip(f"Could not collect live USB data: {exc}")

        result = config.find_reference_usb_match(snapshot)
        if result is None:
            pytest.skip("Reference USB drive not connected — plug it in to run this test.")

        configured, live_device = result
        passed, detail = config.check_speed_meets_expectation(configured, live_device)

        assert passed, (
            f"Reference drive '{live_device.name}' did not meet minimum speed "
            f"expectation: {detail}. This usually means a bad cable, a USB 2.0 "
            f"port/hub, or a downstream bandwidth-starved hub."
        )

    def test_reference_drive_not_speed_downgraded(self):
        """
        Checks the device's own is_speed_downgraded flag — True only if
        max_supported_speed was independently known to be higher than what
        was negotiated. With system_profiler-only data this will usually
        be False (negotiated speed is the only speed system_profiler
        reports), but this test documents the intended check for when a
        capability database or protocol-analyzer cross-check is added.
        """
        config = load_device_config()
        monitor = DeviceMonitor()

        try:
            snapshot = monitor.take_snapshot()
        except CollectorError as exc:
            pytest.skip(f"Could not collect live USB data: {exc}")

        result = config.find_reference_usb_match(snapshot)
        if result is None:
            pytest.skip("Reference USB drive not connected — plug it in to run this test.")

        _, live_device = result
        assert not live_device.is_speed_downgraded, (
            f"{live_device.name} reports negotiated speed below its own "
            f"recorded max_supported_speed — investigate cable/port/hub."
        )


@pytest.mark.requires_macos
class TestUSBDriveHotPlugLiveCapture:
    """
    Live hot-plug capture test — the centerpiece interview demo.

    This polls real hardware for a fixed window and asserts that the
    diff engine correctly detects an attach or detach event. Designed to
    be run interactively: start the test, then physically plug or unplug
    the configured reference drive during the polling window.

    NOTE: this test requires manual interaction and is skipped by default
    in normal CI/test runs via the `interactive` marker — run it explicitly:
        pytest -v -m "requires_macos and interactive" tests/test_usb_drive_live.py
    """

    @pytest.mark.interactive
    def test_detects_manual_hotplug_during_poll_window(self):
        config = load_device_config()
        monitor = DeviceMonitor(poll_interval_sec=config.live_demo_poll_interval_sec)

        print(
            "\n>>> Plug or unplug the reference USB drive now. "
            f"Polling for {config.live_demo_duration_sec:.0f} seconds...\n"
        )

        try:
            events = monitor.run(duration_sec=config.live_demo_duration_sec)
        except CollectorError as exc:
            pytest.skip(f"Could not collect live USB data: {exc}")

        attach_or_detach = [e for e in events if e.event_type in ("attach", "detach")]
        assert len(attach_or_detach) > 0, (
            "No attach/detach event detected during the polling window — "
            "did you plug/unplug a device while this test was running?"
        )
        for e in attach_or_detach:
            print(f"  Detected: [{e.event_type.upper()}] {e.device_name} — {e.detail}")
