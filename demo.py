#!/usr/bin/env python3
"""
demo.py — a standalone, narratable walkthrough of the diff engine.

Run this live during the technical interview to show real anomaly
detection without needing real hardware attached:

    python demo.py

It loads the two sample USB snapshots (before/after), runs them through
the diff engine, and prints out the detected events — then runs a second
scenario showing speed-downgrade detection on a synthetic device.
"""

import json
from pathlib import Path

from core_io_monitor.monitor import DeviceMonitor
from core_io_monitor.models import USBDevice, USBSpeed, DeviceSnapshot

SAMPLE_DIR = Path(__file__).parent / "sample_data"


def print_header(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def demo_attach_detach() -> None:
    print_header("DEMO 1: Real-world hot-plug detection (SSD unplugged, webcam plugged in)")

    with open(SAMPLE_DIR / "usb_snapshot_before.json") as f:
        before_json = json.load(f)
    with open(SAMPLE_DIR / "usb_snapshot_after.json") as f:
        after_json = json.load(f)

    before = DeviceMonitor.snapshot_from_json(usb_json=before_json, timestamp=1000.0)
    after = DeviceMonitor.snapshot_from_json(usb_json=after_json, timestamp=1002.0)

    print(f"\nBefore snapshot: {len(before.usb_devices)} USB devices")
    for d in before.usb_devices:
        print(f"  - {d.name} ({d.negotiated_speed.value})")

    print(f"\nAfter snapshot: {len(after.usb_devices)} USB devices")
    for d in after.usb_devices:
        print(f"  - {d.name} ({d.negotiated_speed.value})")

    events = DeviceMonitor.diff(before, after)
    print(f"\nDetected {len(events)} event(s):")
    for e in events:
        print(f"  [{e.event_type.upper()}] {e.device_name} — {e.detail or 'no detail'}")


def demo_speed_downgrade() -> None:
    print_header("DEMO 2: Speed-downgrade detection (cable/hub bandwidth regression)")

    fast = USBDevice(
        name="External Dock",
        serial_number="DOCK-001",
        negotiated_speed=USBSpeed.SUPER_SPEED_PLUS,
        max_supported_speed=USBSpeed.SUPER_SPEED_PLUS,
    )
    slow = USBDevice(
        name="External Dock",
        serial_number="DOCK-001",
        negotiated_speed=USBSpeed.HIGH_SPEED,
        max_supported_speed=USBSpeed.SUPER_SPEED_PLUS,
    )

    before = DeviceSnapshot(timestamp=1.0, usb_devices=[fast])
    after = DeviceSnapshot(timestamp=2.0, usb_devices=[slow])

    print(f"\nPoll #1: {fast.name} negotiated {fast.negotiated_speed.value}")
    print(f"Poll #2: {slow.name} negotiated {slow.negotiated_speed.value} "
          f"(supports {slow.max_supported_speed.value})")

    events = DeviceMonitor.diff(before, after)
    print(f"\nDetected {len(events)} event(s):")
    for e in events:
        print(f"  [{e.event_type.upper()}] {e.device_name} — {e.detail}")


if __name__ == "__main__":
    demo_attach_detach()
    demo_speed_downgrade()
    print()
    print("=" * 70)
    print("On real macOS hardware, DeviceMonitor.take_snapshot() replaces")
    print("snapshot_from_json() — same diff engine, live system_profiler data.")
    print("=" * 70)
