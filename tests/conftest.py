"""Cross-platform test collection hooks.

The ``windows_only`` marker (declared in ``pyproject.toml`` under
``tool.pytest.ini_options.markers``) flags tests that need a live Windows
desktop session to drive the UIA accessibility tree. On non-Windows hosts the
``uiautomation``/``comtypes`` stack hard-fails at import time (COM is not
available outside Windows), so a bare ``pytest.importorskip("uiautomation")``
surfaces as a broken-import error rather than a skip on recent pytest. Skip
these tests up front on non-Windows hosts so the suite stays green
cross-platform without weakening the marker's meaning on Windows CI.
"""

from __future__ import annotations

import sys

import pytest


def pytest_collection_modifyitems(config, items):  # noqa: ANN001
    skip_marker = pytest.mark.skip(reason="windows_only: needs a live Windows desktop session")
    if sys.platform.startswith("win"):
        return
    for item in items:
        if "windows_only" in item.keywords:
            item.add_marker(skip_marker)
