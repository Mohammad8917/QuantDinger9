#!/usr/bin/env python3
"""Run the upstream mojibake checker, excluding files that test the detector.

The excluded files intentionally contain corruption-marker strings so the
scanner can recognize those patterns; they are not user-facing corrupted text.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_mojibake as checker  # noqa: E402

checker.SKIP_PATHS = checker.SKIP_PATHS | {
    "QuantDinger-Vue/scripts/encoding-audit.mjs",
    "QuantDinger-Vue/tests/unit/i18nExperience.test.mjs",
}

if __name__ == "__main__":
    raise SystemExit(checker.main())
