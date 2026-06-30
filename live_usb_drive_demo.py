#!/usr/bin/env python3
"""
live_usb_drive_demo.py — run this on real macOS hardware, screen-shared,
during the technical interview.

Unlike demo.py (which replays static JSON fixtures), this script polls
REAL live USB bus state using system_profiler, and watches for your
configured reference drive (see device_config.yaml) to be plugged in or
unplugged in real time.

Usage:
    python live_usb_drive_demo.py

Before running:
    1. Edit device_config.yaml's `reference_devices[0].identifiers` to
       match your actual USB drive — run:
           system_profiler SPUSBDataType -json
       and copy the vendor_id / product_id / serial_num for your drive.
    2. Have the drive handy to plug/unplug during the demo window.
"""

import sys
import time

from core_io_monitor.monitor import DeviceMonitor
from core_io_monitor.device_config import load_device_config
from core_io_monitor.collectors import CollectorError


def main() -> int:
    config = load_device_config()
    monitor = DeviceMonitor(poll_interval_sec=config.live_demo_poll_interval_sec)

    print("=" * 70)
    print("LIVE USB Drive Demo — Core I/O Test Harness")
    print("=" * 70)
    print(f"DUT: {config.dut_name}")
    print(f"Polling interval: {config.live_demo_poll_interval_sec}s")
    print(f"Demo duration: {config.live_demo_duration_sec:.0f}s")
    print()

    try:
        baseline = monitor.take_snapshot()
    except CollectorError as exc:
        print(f"ERROR: {exc}")
        print("This script requires real macOS hardware — system_profiler not found.")
        return 1

    print(f"Baseline snapshot: {len(baseline.usb_devices)} USB device(s) currently attached")

    match = config.find_reference_usb_match(baseline)
    if match:
        configured, live_device = match
        passed, detail = config.check_speed_meets_expectation(configured, live_device)
        status = "PASS" if passed else "FAIL"
        print(f"  Reference drive already connected: {live_device.name} [{status}] {detail}")
        print("  (Unplug it now to see a live DETACH event, or plug in a different")
        print("   USB device to see a live ATTACH event.)")
    else:
        print("  Reference drive not currently connected.")
        print("  Plug it in now to see a live ATTACH event.")

    print()
    print(f"Watching for {config.live_demo_duration_sec:.0f} seconds... "
          f"(Ctrl+C to stop early)")
    print("-" * 70)

    def on_event(event):
        marker = {"attach": "[+]", "detach": "[-]", "speed_downgrade": "[!]"}.get(event.event_type, "[~]")
        print(f"{marker} {event.event_type.upper():16s} {event.device_name:30s} {event.detail}")
        sys.stdout.flush()

    try:
        events = monitor.run(
            duration_sec=config.live_demo_duration_sec,
            log_path=config.live_demo_log_path,
        )
    except KeyboardInterrupt:
        print("\nStopped early by user.")
        return 0
    except CollectorError as exc:
        print(f"\nERROR during polling: {exc}")
        return 1

    print("-" * 70)
    print(f"\nDemo complete. {len(events)} event(s) detected.")
    print(f"Full event log written to: {config.live_demo_log_path}")

    if not events:
        print("\n(No events detected — try re-running and plugging/unplugging a")
        print(" device during the polling window for a more compelling demo.)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
