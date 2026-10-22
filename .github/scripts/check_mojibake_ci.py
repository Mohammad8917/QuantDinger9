#!/usr/bin/env python3
"""Run the repository mojibake guard with high-specificity signatures.

Single Chinese characters and accented Latin letters are valid in supported
locales; they are not sufficient evidence of encoding corruption. Keep the
multi-character signatures from the frontend's dedicated encoding audit.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_mojibake as checker  # noqa: E402

checker.SKIP_PATHS = checker.SKIP_PATHS | {
    # These files deliberately contain corruption markers to test detectors.
    "QuantDinger-Vue/scripts/encoding-audit.mjs",
    "QuantDinger-Vue/tests/unit/i18nExperience.test.mjs",
    "QuantDinger-Vue/tests/unit/indicatorIdeInteractionRegressions.test.mjs",
}
checker.MOJIBAKE_MARKERS = {
    "\u040e\u0404": "UTF-8 punctuation decoded through the wrong legacy code page",
    "\u0432\u2013": "UTF-8 symbol decoded through the wrong legacy code page",
    "\ufffd": "Unicode replacement character",
    "\u00ef\u00bf\u00bd": "UTF-8 bytes for replacement character decoded as Latin-1",
    "锟斤拷": "Known replacement mojibake sequence",
    "鐠?": "Known GBK mojibake sequence",
    "鍐呯殑": "Known GBK mojibake sequence",
    "鎵€鏈": "Known GBK mojibake sequence",
    "澶村儚": "Known GBK mojibake sequence",
    "閾炬帴": "Known GBK mojibake sequence",
    "鍥炬爣": "Known GBK mojibake sequence",
    "鏍峰紡": "Known GBK mojibake sequence",
}

if __name__ == "__main__":
    raise SystemExit(checker.main())
