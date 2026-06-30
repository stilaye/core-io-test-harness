"""
Root-level conftest: automatically skips tests marked `requires_macos` when
not running on a real Mac. This lets the full suite run cleanly in CI
(GitHub Actions ubuntu-latest) while still preserving real-hardware
integration tests for local validation on actual Apple hardware.
"""

import platform

import pytest


def pytest_collection_modifyitems(config, items):
    if platform.system() == "Darwin":
        return  # Running on real macOS — let requires_macos tests execute.

    skip_marker = pytest.mark.skip(reason="requires real macOS hardware (system_profiler/ioreg)")
    for item in items:
        if "requires_macos" in item.keywords:
            item.add_marker(skip_marker)
