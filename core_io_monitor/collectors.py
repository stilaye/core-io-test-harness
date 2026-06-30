"""
Collectors: thin wrappers around macOS CLI tools that gather raw hardware
state. Kept separate from parsing (`parsers.py`) so the parsing logic can be
unit tested on any OS using static fixture files, while these functions are
only exercised in integration tests run on real macOS / real hardware.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any


class CollectorError(RuntimeError):
    """Raised when a system command fails or returns unparseable output."""


def _run_json_command(args: list[str], timeout: float = 10.0) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    except FileNotFoundError as exc:
        raise CollectorError(f"Command not found: {args[0]} (are you on macOS?)") from exc
    except subprocess.CalledProcessError as exc:
        raise CollectorError(f"Command failed: {' '.join(args)}\n{exc.stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CollectorError(f"Command timed out: {' '.join(args)}") from exc

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CollectorError(f"Failed to parse JSON from {args[0]}: {exc}") from exc


def collect_usb_data() -> dict[str, Any]:
    """Run `system_profiler SPUSBDataType -json` and return parsed JSON."""
    return _run_json_command(["system_profiler", "SPUSBDataType", "-json"])


def collect_thunderbolt_data() -> dict[str, Any]:
    """Run `system_profiler SPThunderboltDataType -json` and return parsed JSON."""
    return _run_json_command(["system_profiler", "SPThunderboltDataType", "-json"])


def collect_ioreg_usb_raw(timeout: float = 10.0) -> str:
    """
    Run `ioreg -p IOUSB -l -w0` and return raw text.

    This is a secondary, lower-level data source used when system_profiler's
    summary view doesn't expose a needed field (e.g., specific IOKit
    properties like IOServiceState or location-in-tree relationships).
    """
    try:
        result = subprocess.run(
            ["ioreg", "-p", "IOUSB", "-l", "-w0"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    except FileNotFoundError as exc:
        raise CollectorError("ioreg not found (are you on macOS?)") from exc
    except subprocess.CalledProcessError as exc:
        raise CollectorError(f"ioreg failed: {exc.stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CollectorError("ioreg timed out") from exc

    return result.stdout
