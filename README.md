# Apple Core I/O Quality Engineering — Test Harness POC

**Author: Swapnil Tilaye**
**Built for: SDET, Core I/O Transports Quality Engineering, Core OS (Role #200665480)**

A working proof-of-concept demonstrating an IOKit-backed device monitor and
pytest test framework for USB and Thunderbolt bus state — built specifically
to mirror the responsibilities in the job description: *"Design, develop
and own automated tests... contribute to development of test frameworks &
tools... investigate and analyze issues spanning across the hardware and
software interaction layers."*

This is intentionally scoped as a POC, not a finished framework — it's meant
to demonstrate architecture and methodology that would extend cleanly to
real Apple I/O validation infrastructure.

---

## What this demonstrates

1. **Snapshot-diff anomaly detection** — polls `system_profiler` /
   `ioreg`-style bus state and detects attach, detach, and speed-downgrade
   events between polls (the single most common real-world USB QE bug
   pattern: a device negotiating a lower speed than it supports due to a
   bad cable, dirty contacts, or hub bandwidth starvation).
2. **CI-safe test architecture** — all parsing and diffing logic is testable
   with static JSON fixtures, so the suite runs clean on any OS (this repo's
   CI runs on `ubuntu-latest`) while real-hardware collection is isolated
   behind a `requires_macos` marker for validation on actual Apple silicon.
3. **A structure that mirrors what the Core I/O team would extend** — clean
   separation between data collection (`collectors.py`, shells out to macOS
   tools), parsing (`parsers.py`, pure functions, fully unit-testable), and
   orchestration (`monitor.py`, the polling loop + structured JSONL logging).

---

## Repository Structure

```
core-io-test-harness/
│
├── core_io_monitor/                  # Core package
│   ├── __init__.py
│   ├── models.py                     # USBDevice, ThunderboltDevice, DeviceEvent dataclasses
│   ├── collectors.py                 # subprocess wrappers: system_profiler, ioreg
│   ├── parsers.py                    # raw JSON → normalized models (pure functions)
│   ├── diff_engine.py                # snapshot comparison → DeviceEvent list
│   ├── device_config.py              # loads device_config.yaml, matches DUT/reference/aux devices
│   └── monitor.py                    # DeviceMonitor: orchestration + polling loop
│
├── tests/                            # pytest suite (42 tests, CI-safe)
│   ├── conftest.py                   # shared fixtures (snapshots, sample JSON)
│   ├── test_parsers.py               # 14 tests — JSON parsing correctness
│   ├── test_diff_engine.py           # 9 tests — attach/detach/downgrade detection
│   ├── test_monitor.py               # 5 tests — orchestration + macOS-only integration
│   ├── test_device_config.py         # 14 tests — config loading + device matching
│   └── test_usb_drive_live.py        # 4 tests — live reference USB drive validation (requires_macos)
│
├── sample_data/                      # Static JSON fixtures (mirrors system_profiler output)
│   ├── usb_snapshot_before.json      # SSD + keyboard attached
│   └── usb_snapshot_after.json       # SSD unplugged, webcam plugged in
│
├── device_config.yaml                # DUT, reference & auxiliary device inventory
├── demo.py                           # Standalone narratable demo using static fixtures
├── live_usb_drive_demo.py            # LIVE polling demo against real hardware (run on your Mac)
├── conftest.py                       # Root-level: auto-skips macOS-only tests off-Mac
├── pytest.ini                        # Markers, strict mode
├── requirements.txt
├── docs/
│   ├── ARCHITECTURE.md               # Layered design rationale
│   ├── RUNBOOK.md                    # Operational guide + extension steps
│   ├── SYSDIAGNOSE_ANALYSIS_GUIDE.md # Mapping real sysdiagnose bundles to this harness
│   └── SYSTEM_PROFILER_GUIDE.md      # system_profiler reference + poll-vs-push tradeoff
├── CLAUDE.md                         # Context file for AI coding assistants
└── .github/workflows/tests.yml       # CI: runs full suite on every push
```

---

## Quick Start

```bash
git clone https://github.com/stilaye/core-io-test-harness.git
cd core-io-test-harness
pip install -r requirements.txt

# Run the full test suite (live-hardware tests auto-skip off macOS)
pytest -v

# Run with coverage
pytest --cov=core_io_monitor --cov-report=term-missing

# Run the narratable demo (static fixtures, runs anywhere)
python demo.py
```

### On real macOS hardware

```bash
# 1. Discover your actual USB drive's identifiers
system_profiler SPUSBDataType -json | less
# Copy vendor_id / product_id / serial_num into device_config.yaml's
# reference_devices[0].identifiers

# 2. Run the live hardware tests
pytest -v -m requires_macos tests/test_usb_drive_live.py

# 3. Run the live polling demo — screen-share this during the interview
python live_usb_drive_demo.py
# Plug/unplug your reference USB drive while it's polling to watch
# real ATTACH/DETACH events stream in.
```

---

## Test Summary

| Suite                          | Tests  | Runs Offline? | Coverage                                       |
|----------------------------------|--------|----------------|--------------------------------------------------|
| `test_parsers.py`                | 14     | ✅ Yes         | JSON → model parsing, speed string mapping       |
| `test_diff_engine.py`            | 9      | ✅ Yes         | Attach/detach, speed downgrade, serialization    |
| `test_monitor.py`                | 5      | ✅ Yes (3) / `requires_macos` (2) | Orchestration + real-hardware integration |
| `test_device_config.py`          | 14     | ✅ Yes         | device_config.yaml loading + device matching     |
| `test_polling_limitations.py`    | 4      | ✅ Yes         | Proves the poll-vs-push architectural blind spot |
| `test_usb_drive_live.py`         | 4      | `requires_macos` | Live reference drive detection, speed check, hot-plug capture |
| **Total**                        | **50** |                | **76%+ line coverage** on `core_io_monitor/`     |

```bash
pytest -m "not requires_macos"   # 46 tests, fully offline-safe (CI default)
pytest -m requires_macos         # 6 integration tests — run these on real Mac hardware
pytest -m "requires_macos and interactive"   # the manual hot-plug capture test
```

---

## Device inventory (DUT / reference / auxiliary)

`device_config.yaml` declares three categories of device, mirroring
standard hardware-in-the-loop QE practice:

- **DUT (Device Under Test)** — the host Mac itself. Core I/O QE validates
  the host's USB/Thunderbolt/PCIe controllers and drivers, so the DUT is
  whatever machine this harness runs on.
- **Reference devices** — known-good peripherals with declared expected
  behavior (e.g., a specific USB drive expected to negotiate at least
  SuperSpeed). Tests assert live observed state against these
  expectations, turning "a USB drive showed up" into "the USB drive we
  expect showed up, and it's behaving correctly."
- **Auxiliary devices** — expected-but-out-of-scope devices (keyboard,
  trackpad) tracked so the diff engine doesn't misreport them as
  anomalies during a demo.

Before running the live tests, fill in your actual drive's identifiers:

```bash
system_profiler SPUSBDataType -json | less
```

Copy the `vendor_id`, `product_id`, and `serial_num` into
`device_config.yaml`'s `reference_devices[0].identifiers`.

---

## Why speed-downgrade detection?

A USB device negotiating a lower link speed than it supports — e.g., a
SuperSpeed+ (10 Gb/s) drive falling back to USB 2.0 High Speed (480 Mb/s) —
is one of the most common field-reported I/O bugs, usually caused by a
marginal cable, a hub that can't deliver full bandwidth, or a driver
re-negotiation bug after a sleep/wake cycle. This POC's diff engine flags
exactly that pattern automatically across polls, which is the kind of
regression a continuous monitor running in CI would catch before it ships.

See `demo.py` → `demo_speed_downgrade()` for a runnable example.

---

## Why polling, not push notifications?

`system_profiler` is a snapshot/reporting tool — every call walks the
current hardware tree and returns what's true *right now*. It has no live
event-stream model, which is why this harness is built as
**poll → snapshot → diff** rather than a true event listener.

That architecture has a real, provable blind spot: anything that happens
entirely *between* two polls — a device that attaches and detaches within
one interval, or a speed value that flaps and lands back on its original
state — is invisible to the diff engine. `tests/test_polling_limitations.py`
proves this concretely rather than just asserting it in prose.

A production implementation would hook IOKit's push-based notification
APIs directly (`IOServiceAddMatchingNotification`) instead of polling —
see `docs/SYSTEM_PROFILER_GUIDE.md` for the full tradeoff writeup. This
POC trades a zero-blind-spot event model for pure-Python testability with
no compiled IOKit extension required — a deliberate choice, not an
oversight.

---

## Path to production (what I'd build next)

- Replace static JSON fixtures with a live `system_profiler`/`ioreg` poll
  loop validated against real Mac hardware with real USB3/Thunderbolt/PCIe
  devices attached (`collectors.py` already supports this — `take_snapshot()`
  just needs to run on macOS).
- Add a **protocol analyzer integration layer** for ground-truth comparison
  against captured bus traffic (Ellisys/Teledyne-style captures) — letting
  the diff engine cross-validate IOKit-reported state against the physical
  layer.
- Extend `models.py` to cover PCIe link training (lane width, Gen 3/4/5
  speed) and DisplayPort EDID/HPD state, following the same
  collector → parser → diff_engine pattern already in place for USB.
- Wire `DeviceMonitor.run()` into a CI job that runs against a hardware
  test rig with controllable USB switches for true hot-plug stress testing.

---

**Note:** All code uses publicly documented macOS command-line tools
(`system_profiler`, `ioreg`). No proprietary or confidential Apple
information is included.
