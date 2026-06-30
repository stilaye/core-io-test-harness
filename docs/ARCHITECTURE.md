# Architecture

## Design Goal

The core constraint driving this design: **test logic must be verifiable
without real Apple hardware**, while still being a faithful model of how
real USB/Thunderbolt validation would work on macOS. That single constraint
shapes every layer boundary in this codebase.

This matters for two reasons specific to this POC's context. First, it was
built and CI-tested on Linux, not macOS — so anything that shells out to
`system_profiler` or `ioreg` had to be cleanly separated from the logic that
actually matters (parsing bus state, detecting anomalies). Second, that
separation is exactly the kind of testability discipline a Core I/O QE
framework would need anyway — you can't always have every device variant
physically attached to a CI runner, so the parsing and diffing logic has to
be independently verifiable against captured/fixture data.

## Layer Breakdown

```
┌─────────────────────────────────────────────────────────┐
│  collectors.py                                          │
│  Shells out to system_profiler / ioreg.                 │
│  ONLY layer that touches the real OS.                   │
│  Raises CollectorError on non-macOS or command failure.  │
└───────────────────────┬───────────────────────────────────┘
                         │ raw JSON / text
                         ▼
┌─────────────────────────────────────────────────────────┐
│  parsers.py                                              │
│  Pure functions: raw JSON → normalized dataclasses.       │
│  No subprocess calls, no I/O. Fully unit-testable with    │
│  static fixture files on any OS.                          │
└───────────────────────┬───────────────────────────────────┘
                         │ USBDevice / ThunderboltDevice
                         ▼
┌─────────────────────────────────────────────────────────┐
│  models.py                                                │
│  Dataclasses + enums (USBSpeed, BusType) shared by every   │
│  other layer. Includes derived properties like             │
│  is_speed_downgraded — domain logic lives here, not         │
│  scattered across parsers/diff engine.                      │
└───────────────────────┬───────────────────────────────────┘
                         │ DeviceSnapshot (before, after)
                         ▼
┌─────────────────────────────────────────────────────────┐
│  diff_engine.py                                            │
│  Compares two snapshots, emits DeviceEvent list:            │
│  attach / detach / speed_downgrade / speed_changed /         │
│  link_degraded. Pure functions — no I/O, no subprocess.      │
└───────────────────────┬───────────────────────────────────┘
                         │ list[DeviceEvent]
                         ▼
┌─────────────────────────────────────────────────────────┐
│  monitor.py                                                │
│  Orchestration layer. DeviceMonitor ties the above together│
│  for two use cases:                                          │
│   - take_snapshot() + run(): live polling loop on real Mac   │
│   - snapshot_from_json(): offline/test path, same diff logic │
└─────────────────────────────────────────────────────────┘
```

## Why this boundary, specifically

**`collectors.py` is the only file that can fail because of the environment
it runs in.** Every other layer fails only because of a logic bug. That
distinction is what let the test suite hit 28 passing tests with zero
mocking-framework complexity — `parsers.py` and `diff_engine.py` are pure
functions over plain data, so tests just construct the data and assert on
output. No `unittest.mock.patch`, no fixture servers, no flakiness.

**`models.py` owns domain logic, not just data shape.** The
`is_speed_downgraded` property on `USBDevice` and the `_SPEED_RANK` ordering
table live in the model, not duplicated inside `diff_engine.py`. If the
speed-ranking logic ever needs to change (e.g., when Thunderbolt 5 / USB4 v2
gets added to the enum), there's exactly one place to change it.

**`monitor.py` is intentionally thin.** It has two entry points —
`take_snapshot()` for live hardware and `snapshot_from_json()` for
tests/offline analysis — that both terminate in the same `diff()` call.
That guarantees test coverage of the diff logic via the offline path
automatically covers the logic the live path depends on. There's no
"test version" of the diff engine that could drift from the "real version."

## Data flow example: a speed downgrade

1. Poll 1: `collectors.collect_usb_data()` returns JSON showing a dock at
   SuperSpeed+ (10 Gb/s).
2. `parsers.parse_usb_data()` builds a `USBDevice` with
   `negotiated_speed=SUPER_SPEED_PLUS`, `max_supported_speed=SUPER_SPEED_PLUS`.
3. Poll 2 (after a sleep/wake cycle, say): the same dock now reports
   `negotiated_speed=HIGH_SPEED` in raw JSON.
4. `diff_engine.diff_usb_snapshots()` sees the same `identity` (serial
   number) in both snapshots, calls `device.is_speed_downgraded`, which
   compares `speed_rank(HIGH_SPEED) < speed_rank(SUPER_SPEED_PLUS)` → `True`.
5. A `DeviceEvent(event_type="speed_downgrade", ...)` is emitted with the
   before/after speed values in `detail`.
6. `monitor.run()` would log this as a JSON line to `events.jsonl` if
   actively polling; in the offline/test path, the event is just returned
   for assertion.

## Extension points (USB → Thunderbolt/PCIe/DisplayPort)

The same five-layer pattern is designed to extend directly:

- **PCIe**: add `PCIeDevice` to `models.py` (link width, Gen 3/4/5 speed),
  a `parse_pcie_data()` function in `parsers.py` wrapping
  `ioreg -p IOPCIPlane`, and a `diff_pcie_snapshots()` in `diff_engine.py`
  following the exact attach/detach/degraded pattern already used for USB
  and Thunderbolt.
- **DisplayPort**: same pattern, parsing EDID/HPD state from
  `system_profiler SPDisplaysDataType -json`.
- **Protocol analyzer cross-validation**: a new `analyzer_collectors.py`
  module could ingest captured bus traffic (e.g., from an Ellisys/Teledyne
  analyzer export) and feed it through the same `DeviceSnapshot` shape,
  letting the diff engine flag discrepancies between IOKit-reported state
  and ground-truth physical-layer captures.

No existing layer needs to change to support these — that's the point of
the boundary.
