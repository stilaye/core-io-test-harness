"""
Diff engine: compares two DeviceSnapshots and emits DeviceEvents.

This is the core "monitor" logic — given a before/after pair of snapshots,
detect: device attach, device detach, USB speed downgrade (negotiated speed
lower than the device's max supported speed), and Thunderbolt link width/
speed degradation.
"""

from __future__ import annotations

import time

from .models import DeviceSnapshot, DeviceEvent, BusType


def diff_usb_snapshots(before: DeviceSnapshot, after: DeviceSnapshot) -> list[DeviceEvent]:
    events: list[DeviceEvent] = []
    ts = after.timestamp

    before_map = before.usb_by_identity()
    after_map = after.usb_by_identity()

    # Attaches: present in after, not in before
    for identity, device in after_map.items():
        if identity not in before_map:
            events.append(DeviceEvent(
                event_type="attach",
                bus_type=BusType.USB,
                device_identity=identity,
                device_name=device.name,
                timestamp=ts,
                detail=f"speed={device.negotiated_speed.value}",
            ))
        else:
            # Present in both — check for speed downgrade
            prior = before_map[identity]
            if device.is_speed_downgraded:
                events.append(DeviceEvent(
                    event_type="speed_downgrade",
                    bus_type=BusType.USB,
                    device_identity=identity,
                    device_name=device.name,
                    timestamp=ts,
                    detail=(
                        f"negotiated={device.negotiated_speed.value} "
                        f"max_supported={device.max_supported_speed.value}"
                    ),
                ))
            elif prior.negotiated_speed != device.negotiated_speed:
                events.append(DeviceEvent(
                    event_type="speed_changed",
                    bus_type=BusType.USB,
                    device_identity=identity,
                    device_name=device.name,
                    timestamp=ts,
                    detail=(
                        f"from={prior.negotiated_speed.value} "
                        f"to={device.negotiated_speed.value}"
                    ),
                ))

    # Detaches: present in before, not in after
    for identity, device in before_map.items():
        if identity not in after_map:
            events.append(DeviceEvent(
                event_type="detach",
                bus_type=BusType.USB,
                device_identity=identity,
                device_name=device.name,
                timestamp=ts,
            ))

    return events


def diff_thunderbolt_snapshots(before: DeviceSnapshot, after: DeviceSnapshot) -> list[DeviceEvent]:
    events: list[DeviceEvent] = []
    ts = after.timestamp

    before_map = before.thunderbolt_by_identity()
    after_map = after.thunderbolt_by_identity()

    for identity, device in after_map.items():
        if identity not in before_map:
            events.append(DeviceEvent(
                event_type="attach",
                bus_type=BusType.THUNDERBOLT,
                device_identity=identity,
                device_name=device.name,
                timestamp=ts,
                detail=f"link_speed={device.link_speed_gbps}Gbps",
            ))
        else:
            prior = before_map[identity]
            if (
                prior.link_speed_gbps is not None
                and device.link_speed_gbps is not None
                and device.link_speed_gbps < prior.link_speed_gbps
            ):
                events.append(DeviceEvent(
                    event_type="link_degraded",
                    bus_type=BusType.THUNDERBOLT,
                    device_identity=identity,
                    device_name=device.name,
                    timestamp=ts,
                    detail=(
                        f"from={prior.link_speed_gbps}Gbps "
                        f"to={device.link_speed_gbps}Gbps"
                    ),
                ))

    for identity, device in before_map.items():
        if identity not in after_map:
            events.append(DeviceEvent(
                event_type="detach",
                bus_type=BusType.THUNDERBOLT,
                device_identity=identity,
                device_name=device.name,
                timestamp=ts,
            ))

    return events


def diff_snapshots(before: DeviceSnapshot, after: DeviceSnapshot) -> list[DeviceEvent]:
    """Combine USB and Thunderbolt diffs into a single chronological event list."""
    events = diff_usb_snapshots(before, after) + diff_thunderbolt_snapshots(before, after)
    return sorted(events, key=lambda e: e.timestamp)
