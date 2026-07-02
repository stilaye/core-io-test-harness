# Roadmap — planned data-source additions

Diagrams: [current pipeline](diagrams/pipeline-current.svg) &middot;
[planned additions](diagrams/pipeline-planned.svg)

Current state: the live pipeline (`collectors.py` → `parsers.py` →
`models.py` → `diff_engine.py` → `monitor.py`) is wired end-to-end on top
of **`system_profiler`** only (`SPUSBDataType` / `SPThunderboltDataType`,
JSON, polled). Two other OS-level sources exist in the codebase or docs
today but aren't wired in:

- **`ioreg`** — `collect_ioreg_usb_raw()` in `collectors.py` is defined
  but has zero callers. No parser consumes its output; `parsers.py` only
  accepts `system_profiler` JSON today.
- **IOKit** — never called directly (no PyObjC/ctypes, no
  `IOServiceGetMatchingServices`/notification ports). The "IOKit-backed"
  framing in the README refers to `system_profiler`/`ioreg` themselves
  being CLI front-ends over IOKit-reported state, not a direct API
  integration.
- **`sysdiagnose`** — covered only as a manual analyst workflow in
  `docs/SYSDIAGNOSE_ANALYSIS_GUIDE.md`. No automation ingests a bundle.

## Planned additions

### 1. Wire the ioreg parser
Add `parse_ioreg_usb()` to `parsers.py` that consumes the existing
`collect_ioreg_usb_raw()` stub as a fallback when `system_profiler`'s
summary view doesn't expose a needed field (e.g. `IOServiceState`,
location-in-tree relationships — see the docstring already on
`collect_ioreg_usb_raw`). Closes out dead code that's been sitting
unused since the POC.

### 2. IOKit live notifications
New collector using `IOServiceAddMatchingNotification` (via PyObjC or
ctypes) for event-driven attach/detach instead of the current
poll-and-diff loop in `monitor.py`. Addresses the polling-interval gap
covered by `tests/test_polling_limitations.py` — a device that attaches
and detaches between two polls is invisible today.

### 3. sysdiagnose bundle ingestion
New offline collector, `parse_sysdiagnose_bundle(path)`, reading
`system_profiler.spx` and the `ioreg/` folder out of a captured bundle
directory and feeding them through the same `parsers.py` → `models.py`
path. Turns `docs/SYSDIAGNOSE_ANALYSIS_GUIDE.md` from a manual guide into
an automated post-mortem triage tool, reusing the existing
`DeviceMonitor.snapshot_from_json()` offline path — no new orchestration
layer needed.

Each of these follows the same five-layer pattern described in
`docs/ARCHITECTURE.md` and the "Adding a new bus type" section of
`docs/RUNBOOK.md`: new subprocess/file-read logic stays in `collectors.py`,
new parsing stays pure in `parsers.py`, nothing new touches `monitor.py`
beyond wiring the new collector/parser pair into `take_snapshot()`.
