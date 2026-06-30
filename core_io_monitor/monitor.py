"""
DeviceMonitor: the orchestration layer that ties collectors, parsers, and
the diff engine together into a continuous polling monitor.

Usage (on real macOS hardware):

    from core_io_monitor.monitor import DeviceMonitor

    monitor = DeviceMonitor(poll_interval_sec=2.0)
    monitor.run(duration_sec=60, log_path="events.jsonl")

Usage (testing / CI, no real hardware):

    monitor = DeviceMonitor()
    before = monitor.snapshot_from_json(usb_json=fixture_before)
    after = monitor.snapshot_from_json(usb_json=fixture_after)
    events = monitor.diff(before, after)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from .collectors import collect_usb_data, collect_thunderbolt_data, CollectorError
from .parsers import build_snapshot
from .diff_engine import diff_snapshots
from .models import DeviceSnapshot, DeviceEvent


class DeviceMonitor:
    """
    Polls USB + Thunderbolt bus state at a fixed interval and emits
    structured DeviceEvents whenever something changes.
    """

    def __init__(
        self,
        poll_interval_sec: float = 2.0,
        on_event: Callable[[DeviceEvent], None] | None = None,
    ):
        self.poll_interval_sec = poll_interval_sec
        self.on_event = on_event
        self._last_snapshot: DeviceSnapshot | None = None

    # ── Snapshot construction ────────────────────────────────────────────

    def take_snapshot(self) -> DeviceSnapshot:
        """Collect live data from the real machine and build a snapshot."""
        usb_json = collect_usb_data()
        try:
            tb_json = collect_thunderbolt_data()
        except CollectorError:
            # Not every Mac has a Thunderbolt controller (or it's a VM);
            # degrade gracefully rather than failing the whole snapshot.
            tb_json = None
        return build_snapshot(usb_json=usb_json, thunderbolt_json=tb_json)

    @staticmethod
    def snapshot_from_json(
        usb_json: dict[str, Any] | None = None,
        thunderbolt_json: dict[str, Any] | None = None,
        timestamp: float | None = None,
    ) -> DeviceSnapshot:
        """Build a snapshot directly from JSON (for tests / offline analysis)."""
        return build_snapshot(usb_json=usb_json, thunderbolt_json=thunderbolt_json, timestamp=timestamp)

    @staticmethod
    def diff(before: DeviceSnapshot, after: DeviceSnapshot) -> list[DeviceEvent]:
        return diff_snapshots(before, after)

    # ── Continuous polling ───────────────────────────────────────────────

    def run(self, duration_sec: float, log_path: str | Path | None = None) -> list[DeviceEvent]:
        """
        Poll the bus every `poll_interval_sec` for `duration_sec` total,
        emitting events as changes are detected. Returns all events seen.

        If `log_path` is given, events are appended as JSON Lines (one
        event per line) for later analysis — e.g. by a CI artifact step.
        """
        all_events: list[DeviceEvent] = []
        deadline = time.monotonic() + duration_sec
        log_file = open(log_path, "a") if log_path else None

        try:
            self._last_snapshot = self.take_snapshot()
            while time.monotonic() < deadline:
                time.sleep(self.poll_interval_sec)
                current = self.take_snapshot()
                events = self.diff(self._last_snapshot, current)
                for event in events:
                    all_events.append(event)
                    if self.on_event:
                        self.on_event(event)
                    if log_file:
                        log_file.write(json.dumps(event.to_dict()) + "\n")
                self._last_snapshot = current
        finally:
            if log_file:
                log_file.close()

        return all_events
