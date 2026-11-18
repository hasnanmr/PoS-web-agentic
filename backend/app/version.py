"""The deployed commit, for the post-deploy smoke test and rollback checks.

CI writes the commit SHA to app/BUILD_SHA right before uploading the backend to Railway
(the file is gitignored). Local runs and older images report "unknown".
"""

from __future__ import annotations

from pathlib import Path

_FILE = Path(__file__).with_name("BUILD_SHA")


def build_sha() -> str:
    try:
        return _FILE.read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"


BUILD_SHA = build_sha()
