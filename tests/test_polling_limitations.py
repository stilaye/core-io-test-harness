"""
Tests documenting the fundamental limitation of poll-and-diff architecture:
a device that attaches AND detaches entirely *between* two polls is
invisible to this harness, because the diff engine only ever compares two
discrete snapshots — it has no knowledge of what happened in between them.

This isn't a bug to fix in this POC; it's the architectural tradeoff that
motivates the "path to production" note in the README and ARCHITECTURE.md:
a real production monitor would hook IOKit's push-based notification APIs
(IOServiceAddMatchingNotification) instead of polling system_profiler,
specifically to close this blind spot. These tests exist to make that
tradeoff concrete and provable rather than just asserted in prose.
"""

from __future__ import annotations

from core_io_monitor.diff_engine import diff_snapshots
from core_io_monitor.models import USBDevice, DeviceSnapshot, USBSpeed


class TestPollingBlindSpot:
    """
    Demonstrates that poll-and-diff cannot observe state changes that occur
    entirely between two poll instants — only the net difference between
    the two snapshots is ever visible.
    """

    def test_device_that_attaches_and_detaches_between_polls_is_invisible(self):
        """
        Scenario: a flaky USB device plugs in, briefly enumerates, and
        unplugs again — all in the gap between poll N and poll N+1 (e.g.
        a marginal cable causing a connect/disconnect bounce faster than
        the poll_interval_sec). Because both snapshots only capture the
        device's *absence*, the diff engine correctly reports... nothing.
        That's the blind spot, demonstrated rather than just described.
        """
        before = DeviceSnapshot(timestamp=1.0, usb_devices=[])
        # The device attached AND detached here — poll never observed it.
        after = DeviceSnapshot(timestamp=2.0, usb_devices=[])

        events = diff_snapshots(before, after)

        assert events == [], (
            "A device that fully attaches and detaches within a single "
            "poll interval produces zero events under this poll-and-diff "
            "architecture — this is the exact gap a push-based IOKit "
            "notification (IOServiceAddMatchingNotification) would close."
        )

    def test_rapid_speed_flapping_between_polls_only_shows_net_change(self):
        """
        Scenario: a device's negotiated speed bounces between two values
        several times within one poll interval (e.g. power-management
        renegotiation under marginal signal integrity). The diff engine
        only ever sees the value at poll time — not the bounce in between.
        """
        flapping_device_before = USBDevice(
            name="Flaky Dock",
            serial_number="FLAP-001",
            negotiated_speed=USBSpeed.SUPER_SPEED_PLUS,
            max_supported_speed=USBSpeed.SUPER_SPEED_PLUS,
        )
        # In between these two polls, imagine the real device actually
        # flapped: SUPER_SPEED_PLUS -> HIGH_SPEED -> SUPER_SPEED_PLUS ->
        # HIGH_SPEED, multiple times. The poll only ever samples one
        # instant, so only the final observed state matters to the diff.
        flapping_device_after = USBDevice(
            name="Flaky Dock",
            serial_number="FLAP-001",
            negotiated_speed=USBSpeed.HIGH_SPEED,
            max_supported_speed=USBSpeed.SUPER_SPEED_PLUS,
        )

        before = DeviceSnapshot(timestamp=1.0, usb_devices=[flapping_device_before])
        after = DeviceSnapshot(timestamp=2.0, usb_devices=[flapping_device_after])

        events = diff_snapshots(before, after)
        downgrade_events = [e for e in events if e.event_type == "speed_downgrade"]

        # We DO catch that it ended up downgraded relative to start...
        assert len(downgrade_events) == 1
        # ...but the test name and docstring make clear: any flapping that
        # happened strictly *between* poll instants is unobservable. A
        # device that flapped 50 times and happened to land on the same
        # speed at both poll instants would show zero events at all —
        # see the next test for that exact case.

    def test_speed_that_flaps_and_returns_to_original_value_shows_nothing(self):
        """
        The starkest version of the blind spot: a device that degrades
        and recovers entirely between two polls — landing on the exact
        same negotiated speed at both poll instants — produces zero
        events, even though a real intermittent hardware problem occurred.
        """
        device_at_poll_1 = USBDevice(
            name="Marginal Cable Drive",
            serial_number="MARGINAL-001",
            negotiated_speed=USBSpeed.SUPER_SPEED_PLUS,
            max_supported_speed=USBSpeed.SUPER_SPEED_PLUS,
        )
        # Between these polls: SUPER_SPEED_PLUS -> HIGH_SPEED -> back to
        # SUPER_SPEED_PLUS. A push-based notification stream would catch
        # both transitions. Poll-and-diff catches neither.
        device_at_poll_2 = USBDevice(
            name="Marginal Cable Drive",
            serial_number="MARGINAL-001",
            negotiated_speed=USBSpeed.SUPER_SPEED_PLUS,
            max_supported_speed=USBSpeed.SUPER_SPEED_PLUS,
        )

        before = DeviceSnapshot(timestamp=1.0, usb_devices=[device_at_poll_1])
        after = DeviceSnapshot(timestamp=2.0, usb_devices=[device_at_poll_2])

        events = diff_snapshots(before, after)

        assert events == [], (
            "A device that degrades and recovers to its original speed "
            "entirely between two polls is invisible to poll-and-diff — "
            "this is the strongest argument for IOKit push notifications "
            "in a production implementation: intermittent hardware faults "
            "are exactly the bugs Core I/O QE most needs to catch, and "
            "they're exactly what polling is structurally blind to."
        )

    def test_smaller_poll_interval_reduces_but_does_not_eliminate_blind_spot(self):
        """
        Documents (rather than asserts numerically, since this is a
        conceptual point) that decreasing poll_interval_sec narrows the
        blind-spot window but can never close it to zero — only a
        push-based notification model can do that, since polling is
        fundamentally sampling, not observing.
        """
        from core_io_monitor.monitor import DeviceMonitor

        fast_monitor = DeviceMonitor(poll_interval_sec=0.1)
        slow_monitor = DeviceMonitor(poll_interval_sec=5.0)

        # The blind-spot window IS the poll interval — smaller is better,
        # but it's still a window, not zero. This assertion just confirms
        # the configuration value flows through correctly; the real point
        # is documented in the docstring above and in docs/ARCHITECTURE.md.
        assert fast_monitor.poll_interval_sec < slow_monitor.poll_interval_sec
        assert fast_monitor.poll_interval_sec > 0, (
            "Even the fastest practical poll interval is non-zero — "
            "poll-and-diff can shrink the blind spot but never eliminate "
            "it. IOServiceAddMatchingNotification has no such window "
            "because it's event-driven, not sample-driven."
        )
