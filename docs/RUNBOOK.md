# Runbook

Operational guide for running, validating, and extending this harness —
written so a teammate (or future me) could pick this up without a handoff
conversation.

## Running the suite

```bash
pip install -r requirements.txt

# Full suite (macOS-only tests auto-skip if not on Darwin)
pytest -v

# Offline-only (explicit — same result as above off-Mac)
pytest -m "not requires_macos"

# With coverage
pytest --cov=core_io_monitor --cov-report=term-missing

# Live narratable demo (no pytest, no hardware required)
python demo.py
```

Expected result on any machine: **28 passed, 2 skipped** (the 2 skips are
the `requires_macos` integration tests — see below).

## Validating on real macOS hardware (do this before presenting live)

The `requires_macos` tests in `tests/test_monitor.py::TestLiveCollection`
only run on Darwin. To validate against real hardware:

```bash
# Confirm you're on macOS and the marker isn't skipped
python -c "import platform; print(platform.system())"   # should print "Darwin"

pytest -v -m requires_macos
```

If `test_take_snapshot_against_real_hardware` fails with a `CollectorError`,
check:
1. `system_profiler` is on PATH (`which system_profiler`) — should always
   be true on macOS, this would indicate a sandboxed/restricted shell.
2. No SIP or permissions issue blocking `system_profiler`/`ioreg` (rare,
   but possible under MDM-managed devices).

If it fails with an assertion error instead, that's a real signal — open
an issue, this is exactly the kind of thing the monitor is meant to catch.

## Running the live polling loop

```python
from core_io_monitor.monitor import DeviceMonitor

monitor = DeviceMonitor(poll_interval_sec=2.0)
events = monitor.run(duration_sec=60, log_path="events.jsonl")

for e in events:
    print(e.event_type, e.device_name, e.detail)
```

This polls every 2 seconds for 60 seconds, appending each detected event as
a JSON line to `events.jsonl`. Useful for a manual hot-plug stress test:
start this, then physically plug/unplug a USB or Thunderbolt device a few
times and watch the events stream in.

## Adding a new bus type (e.g., PCIe)

Follow the existing USB pattern exactly — this is the intended extension
path (see `docs/ARCHITECTURE.md` for the full rationale):

1. **`models.py`** — add a `PCIeDevice` dataclass with an `identity`
   property, following `USBDevice`/`ThunderboltDevice`.
2. **`collectors.py`** — add `collect_pcie_data()` wrapping
   `ioreg -p IOPCIPlane -l` or equivalent.
3. **`parsers.py`** — add `parse_pcie_data()` converting raw output into
   `list[PCIeDevice]`.
4. **`diff_engine.py`** — add `diff_pcie_snapshots()` mirroring
   `diff_usb_snapshots()`'s attach/detach/degraded logic.
5. **`models.py` → `DeviceSnapshot`** — add a `pcie_devices` field and a
   `pcie_by_identity()` helper.
6. **Tests** — add `sample_data/pcie_snapshot_before.json` /
   `_after.json` fixtures, then mirror `test_parsers.py` /
   `test_diff_engine.py` test classes for the new bus type.

No changes needed to `monitor.py`'s orchestration logic — `diff_snapshots()`
just needs to also call the new `diff_pcie_snapshots()` and concatenate
results.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `CollectorError: Command not found: system_profiler` | Running on non-macOS | Expected off-Mac; use `snapshot_from_json()` with fixtures instead |
| `pytest: error: unrecognized arguments: -m requires_macos` | Marker not registered | Confirm `pytest.ini` is being picked up (`pytest --collect-only` should show no warnings) |
| Speed downgrade not detected for a real device | Device identity mismatch across polls | Check that `serial_number` is populated; falls back to `location_id` which can change across reboots/re-enumeration |
| `JSONDecodeError` in `collectors.py` | `system_profiler` output changed format in a newer macOS version | Update `parsers.py`'s key lookups (e.g., `device_speed`) to match the new schema; log the raw output for diffing against `sample_data/` fixtures |
| CI passes locally but fails in GitHub Actions | Almost certainly a `requires_macos` test running where it shouldn't | Confirm `conftest.py`'s `pytest_collection_modifyitems` is skipping correctly — runner platform should be Linux |

## Pre-interview checklist (Core I/O technical screen)

- [ ] `pytest -v` passes clean (28 passed, 2 skipped) on whatever machine
      you're demoing from
- [ ] `python demo.py` output reviewed — know what each line means before
      narrating it live
- [ ] If demoing on your own Mac: run `pytest -m requires_macos` once
      beforehand to confirm real-hardware collection works
- [ ] Have `docs/ARCHITECTURE.md` open in a second tab in case the
      interviewer asks "why is it structured this way"
