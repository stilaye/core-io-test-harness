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
│   └── monitor.py                    # DeviceMonitor: orchestration + polling loop
│
├── tests/                            # pytest suite (28 tests, CI-safe)
│   ├── conftest.py                   # shared fixtures (snapshots, sample JSON)
│   ├── test_parsers.py               # 14 tests — JSON parsing correctness
│   ├── test_diff_engine.py           # 9 tests — attach/detach/downgrade detection
│   └── test_monitor.py               # 5 tests — orchestration + macOS-only integration
│
├── sample_data/                      # Static JSON fixtures (mirrors system_profiler output)
│   ├── usb_snapshot_before.json      # SSD + keyboard attached
│   └── usb_snapshot_after.json       # SSD unplugged, webcam plugged in
│
├── demo.py                           # Standalone narratable demo (no pytest needed)
├── conftest.py                       # Root-level: auto-skips macOS-only tests off-Mac
├── pytest.ini                        # Markers, strict mode
├── requirements.txt
└── .github/workflows/tests.yml       # CI: runs full suite on every push
```

---

## Quick Start

```bash
git clone https://github.com/stilaye/core-io-test-harness.git
cd core-io-test-harness
pip install -r requirements.txt

# Run the full test suite
pytest -v

# Run with coverage
pytest --cov=core_io_monitor --cov-report=term-missing

# Run the narratable live demo (no real hardware needed)
python demo.py
```

---

## Test Summary

| Suite                  | Tests  | Runs Offline? | Coverage                                     |
|-------------------------|--------|----------------|-----------------------------------------------|
| `test_parsers.py`       | 14     | ✅ Yes         | JSON → model parsing, speed string mapping    |
| `test_diff_engine.py`   | 9      | ✅ Yes         | Attach/detach, speed downgrade, serialization |
| `test_monitor.py`       | 5      | ✅ Yes (3) / `requires_macos` (2) | Orchestration + real-hardware integration |
| **Total**               | **28** |                | **71% line coverage** on `core_io_monitor/`   |

```bash
pytest -m "not requires_macos"   # 28 tests, fully offline-safe (CI default)
pytest -m requires_macos         # 2 integration tests — run these on real Mac hardware
```

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
