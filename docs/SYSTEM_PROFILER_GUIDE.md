# system_profiler Usage Guide

A practical reference for `system_profiler` — the macOS utility this
harness's `collectors.py` wraps — specifically for Core I/O (USB,
Thunderbolt, PCIe, DisplayPort) work. See also `docs/SYSDIAGNOSE_ANALYSIS_GUIDE.md`
for how this same data appears inside a sysdiagnose bundle.

---

## What it is

`system_profiler` is a built-in macOS CLI utility (`/usr/sbin/system_profiler`) — the command-line equivalent of the "About This Mac → System Report" window. It reports hardware and software configuration as a plain-text report or an XML/JSON report, and is the same data source the System Information.app GUI uses.

No installation, no special entitlements, no `sudo` required for the data types this harness uses (`SPUSBDataType`, `SPThunderboltDataType`).

---

## Core syntax

```bash
# Full report — everything, can take 30-60+ seconds
system_profiler

# One or more specific data types — fast, scoped
system_profiler SPUSBDataType
system_profiler SPUSBDataType SPThunderboltDataType

# JSON output (what this harness's collectors.py consumes)
system_profiler SPUSBDataType -json

# XML output (.spx — opens in System Information.app directly)
system_profiler -xml SPUSBDataType > usb_report.spx

# List every available data type
system_profiler -listDataTypes

# Control verbosity
system_profiler -detailLevel mini    # no personal/identifying info
system_profiler -detailLevel basic   # basic hardware + network
system_profiler -detailLevel full    # everything available
```

---

## Data types relevant to Core I/O

| Data Type | Covers | Used by this harness |
|---|---|---|
| `SPUSBDataType` | USB controllers, hubs, and attached devices — vendor/product ID, speed, current draw | ✅ `collectors.collect_usb_data()` |
| `SPThunderboltDataType` | Thunderbolt bus, attached devices, link speed | ✅ `collectors.collect_thunderbolt_data()` |
| `SPDisplaysDataType` | Connected displays, resolution, EDID-derived info | Not yet — see `docs/RUNBOOK.md` extension path |
| `SPPCIDataType` | PCIe devices, vendor/device IDs | Not yet — `ioreg -p IOPCIPlane` may expose more for link-training detail |
| `SPHardwareDataType` | Mac model, chip, serial number | Useful for populating `device_config.yaml`'s `dut` section |
| `SPPowerDataType` | AC wattage, battery state | Relevant context for USB-PD current-draw debugging |

Run `system_profiler -listDataTypes` on your own machine to see the full list — it grows with each macOS release (newer types like `SPNVMeDataType`, `SPSecureElementDataType` have appeared over time).

---

## Practical examples for this repo

```bash
# What this harness's take_snapshot() effectively runs:
system_profiler SPUSBDataType -json
system_profiler SPThunderboltDataType -json

# Find your real USB drive's identifiers to fill into device_config.yaml
system_profiler SPUSBDataType -json | python3 -m json.tool | less
# Look for vendor_id, product_id, serial_num under your drive's node

# Quick eyeball check of what's attached right now (no JSON parsing needed)
system_profiler SPUSBDataType

# Confirm your Mac's chip/model for device_config.yaml's dut section
system_profiler SPHardwareDataType | grep -E "Model Name|Chip|Model Identifier"

# Generate an .spx file you can open directly in System Information.app —
# useful for visually comparing against this harness's parsed output
system_profiler -xml SPUSBDataType SPThunderboltDataType > /tmp/io_report.spx
open /tmp/io_report.spx
```

---

## Performance note

A full unscoped `system_profiler` call (no data type arguments) walks
every subsystem and can take 30-60+ seconds on a loaded machine — one
real-world report clocked nearly 60 seconds wall-clock for the full
report. **Always scope to specific data types** (`SPUSBDataType`,
`SPThunderboltDataType`) for anything performance-sensitive — this is
exactly why `collectors.py` never calls `system_profiler` with no
arguments.

---

## The limitation that matters most for this harness's design

`system_profiler` is fundamentally a **snapshot/reporting tool** — every
invocation walks the current hardware tree and returns what's true *right
now*. It has no concept of a live event stream; there's no `--watch` flag,
no callback, no subscription model. Each call is a fresh, independent poll.

That single fact is the entire reason this harness is built as
**poll → snapshot → diff** (see `core_io_monitor/monitor.py` and
`docs/ARCHITECTURE.md`) rather than a live event listener. It also means
the architecture has a structural blind spot: anything that happens
*between* two polls — a device that attaches and detaches within one
interval, or a speed value that flaps and returns to its original state —
is invisible to a diff-based approach. See
`tests/test_polling_limitations.py` for tests that prove this concretely
rather than just describing it.

**What a production implementation would do differently:** hook IOKit's
push-based notification APIs directly —
[`IOServiceAddMatchingNotification`](https://developer.apple.com/documentation/iokit)
— to receive a callback the instant a device matches/un-matches a given
service class, with no polling interval and no blind-spot window. That's
a C/IOKit-level integration rather than a `subprocess` wrapper around
`system_profiler`, and it's the natural "path to production" step beyond
this POC (see `docs/RUNBOOK.md`).

`system_profiler` remains the right tool for *this* POC specifically
because it's scriptable from pure Python with zero compiled dependencies,
which is what makes the parsing and diffing logic in this repo testable
on any OS, in CI, without a compiled IOKit extension. The tradeoff is
explicit: testability and portability now, versus the zero-blind-spot
event model a shipping implementation would need.
