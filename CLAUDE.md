# CLAUDE.md

Context for AI coding assistants (Claude Code, Copilot, etc.) working in
this repository.

## What this is

A proof-of-concept IOKit-backed USB/Thunderbolt device monitor and pytest
framework, built for a Core I/O Quality Engineering interview at Apple. It
demonstrates snapshot-diff anomaly detection (attach/detach/speed-downgrade)
without requiring real macOS hardware to test the core logic.

## Architecture (see `docs/ARCHITECTURE.md` for full detail)

Five layers, strictly separated:

1. `collectors.py` — subprocess wrappers around `system_profiler`/`ioreg`.
   **Only file allowed to shell out to the OS.**
2. `parsers.py` — pure functions converting raw JSON to dataclasses. No I/O.
3. `models.py` — dataclasses (`USBDevice`, `ThunderboltDevice`,
   `DeviceSnapshot`, `DeviceEvent`) and enums (`USBSpeed`, `BusType`).
   Domain logic (e.g. `is_speed_downgraded`) lives here.
4. `diff_engine.py` — pure functions comparing two snapshots, emitting
   `DeviceEvent` lists.
5. `monitor.py` — orchestration (`DeviceMonitor`), exposing both a live
   polling path (`take_snapshot()` + `run()`) and an offline/test path
   (`snapshot_from_json()`), both terminating in the same `diff()` call.

## Conventions to follow when extending this repo

- **Never put subprocess calls outside `collectors.py`.** If you're adding
  a new bus type (PCIe, DisplayPort), the new collector function belongs in
  `collectors.py`, not inline in `parsers.py` or `monitor.py`.
- **Parsers must be pure functions.** No file I/O, no subprocess, no
  `time.time()` calls (timestamp is always passed in or defaulted at the
  `monitor.py` layer). This is what keeps `tests/test_parsers.py` fast and
  deterministic.
- **New bus types follow the exact same five-step pattern as USB.** See
  "Adding a new bus type" in `docs/RUNBOOK.md` before writing any code —
  don't invent a new pattern.
- **Identity matching uses `serial_number` first, falling back to
  `location_id`.** Location IDs can change across reboots/re-enumeration;
  don't rely on them alone for diffing logic that needs to track a device
  across multiple polls.
- **Every new dataclass needs an `identity` property** — that's what
  `diff_engine.py` keys snapshots on. Without it, attach/detach detection
  silently breaks (treats every poll as all-new devices).

## Testing requirements

- All new logic in `parsers.py` and `diff_engine.py` must be testable with
  static JSON fixtures in `sample_data/` — no mocking frameworks needed.
- Anything that touches real hardware goes behind the `requires_macos`
  pytest marker (see `conftest.py` at repo root for the auto-skip logic).
- Run `pytest -v --cov=core_io_monitor --cov-report=term-missing` before
  committing — current baseline is 28 passed, 2 skipped, 71% coverage.
  Don't let coverage regress on `parsers.py` or `diff_engine.py` specifically
  (those should stay near 100% since they require no real hardware to test).

## Known limitations (be honest about these if asked)

- `collectors.py` is untested in CI (Linux runner can't shell out to
  `system_profiler`) — only validated manually on real macOS hardware.
- PCIe and DisplayPort bus types are not yet implemented — `models.py`,
  `collectors.py`, `parsers.py`, and `diff_engine.py` only cover USB and
  Thunderbolt today. See `docs/RUNBOOK.md` for the extension path.
- No protocol-analyzer (Ellisys/Teledyne) integration yet — IOKit-reported
  state is not cross-validated against physical-layer captures.
