# Sysdiagnose Analysis Guide — Core I/O (USB / Thunderbolt / PCIe)

How to pull the I/O-relevant signal out of a macOS `sysdiagnose` bundle when
debugging a USB, Thunderbolt, or PCIe issue, and how that maps onto the
data model used by this harness (`core_io_monitor/models.py`).

A `sysdiagnose` bundle runs almost every performance and problem tracing tool macOS has, generating several megabytes of output — most of it irrelevant to an I/O bug. This guide narrows that down to the handful of files that actually matter for Core I/O QE work.

---

## 1. Capturing a sysdiagnose

```bash
sudo sysdiagnose -f ~/Documents
```

or the keyboard shortcut: Shift + Control + Option + Command + Period — macOS generates the file in the background and Finder opens to /private/var/tmp once it's done.

**Timing matters.** Trigger the capture as close to the reproduction as
possible — unified log entries have a limited time-to-live and many become inaccessible within minutes to hours, regardless of capture method. For an intermittent USB/Thunderbolt enumeration bug, capture immediately after the failure, not at the end of a test run.

---

## 2. Where the I/O signal lives inside the bundle

A sysdiagnose archive contains roughly 1,500 files. These are the ones relevant to Core I/O work:

| File / Folder | What it contains | Why it matters for USB/TB/PCIe |
|---|---|---|
| `system_profiler.spx` | Standard System Report XML detailing hardware and software configuration | Same data this harness's `parsers.py` consumes via live `system_profiler -json` — a static snapshot equivalent to one `DeviceSnapshot` |
| `ioreg/` folder | A suite of text files detailing all IOKit settings, including known devices and USB | Lower-level than `system_profiler` — useful when a device doesn't show up in the summary view but is still present in the IORegistry |
| `kextstat.txt` | A detailed listing of loaded kernel extensions | Check for third-party USB/Thunderbolt kexts that could be interfering with Apple's native drivers |
| `system_logs.logarchive` | A snapshot of the unified system log as of the time the sysdiagnose was created | Where IOKit driver probe/match failures, power state transitions, and enumeration retries get logged |
| `powermetrics`/`pmset` output | Power state and current-draw data | Relevant for USB-PD and bus-powered device current negotiation failures |

---

## 3. Extracting USB/Thunderbolt events from the unified logarchive

The `system_logs.logarchive` is the most useful single file for an
intermittent enumeration bug. Filter it by subsystem:

```bash
# All IOKit / USB-family subsystem activity
log show --archive system_logs.logarchive \
  --predicate 'subsystem == "com.apple.iokit.IOUSBFamily" OR subsystem CONTAINS "thunderbolt"' \
  --info --debug

# Narrow to a specific time window around the repro
log show --archive system_logs.logarchive \
  --predicate 'subsystem CONTAINS "usb"' \
  --start "2026-06-29 14:30:00" --end "2026-06-29 14:35:00"
```

Older sysdiagnose bundles or direct `system.log` greps follow the same
pattern referenced in Apple Community threads on tracking external device connections — `zgrep` for the device's serial number across rotated system.log files, or use SPFireWireDataType/SPThunderboltDataType for Thunderbolt-connected devices specifically.

---

## 4. Mapping sysdiagnose data onto this harness's models

The harness's `DeviceSnapshot` is intentionally shaped to be filled from
either a **live poll** (`collectors.py` → `system_profiler -json`) or a
**static capture** (a sysdiagnose's `system_profiler.spx`, converted to
JSON). This means a real sysdiagnose capture can become a test fixture:

```bash
# On the affected Mac, capture a one-off snapshot in the same format
# this harness's collectors.py already expects:
system_profiler SPUSBDataType -json > usb_capture.json
system_profiler SPThunderboltDataType -json > tb_capture.json
```

```python
from core_io_monitor.monitor import DeviceMonitor
import json

with open("usb_capture.json") as f:
    usb_json = json.load(f)

snapshot = DeviceMonitor.snapshot_from_json(usb_json=usb_json)
for device in snapshot.usb_devices:
    print(device.name, device.negotiated_speed, device.is_speed_downgraded)
```

This is the bridge between a real bug report (sysdiagnose bundle) and this
harness's offline test path — exactly the same pattern used in
`tests/conftest.py`'s `usb_json_before`/`usb_json_after` fixtures, just
sourced from a real device capture instead of a hand-written JSON file.

**Recommended workflow when triaging a real I/O bug report:**

1. Get the sysdiagnose bundle (or capture one if you have the device).
2. Pull `system_profiler.spx` and convert/re-capture as JSON if needed.
3. Load it through `DeviceMonitor.snapshot_from_json()`.
4. If you have a "before" and "after" capture (e.g., before and after a
   failed re-enumeration), run them through `DeviceMonitor.diff()` to get
   a structured list of what actually changed — rather than manually
   diffing two huge `system_profiler` dumps by eye.
5. Cross-reference any flagged `speed_downgrade` or `detach` events
   against the unified logarchive timestamps from step 3 of this guide to
   find the corresponding IOKit driver log lines.

---

## 5. Known gaps in this mapping (be upfront about these)

- This harness's `parsers.py` currently only consumes `system_profiler`
  JSON — it does not yet parse the `ioreg/` text files or
  `system_logs.logarchive` directly. Steps 3–4 above are a manual bridge,
  not yet automated.
- A natural next extension (not yet built): a `sysdiagnose_parser.py`
  module — following the same pattern as `netqual`'s
  `utils/sysdiagnose_parser.py` — that ingests a full sysdiagnose bundle
  and automatically extracts the USB/Thunderbolt-relevant subset rather
  than requiring a fresh `system_profiler -json` capture.
- Unified log TTL means a sysdiagnose captured well after an intermittent
  failure may have already lost the relevant log lines — see unified log entries expiring within minutes to hours depending on TTL above. This is a real limitation when triaging field reports days after the fact, not just a tooling gap.
