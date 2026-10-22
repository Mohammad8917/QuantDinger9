#!/usr/bin/env python3
"""Run the upstream documentation checker while recognizing webpack template URLs.

Webpack resolves <%= ... %> expressions during the frontend build, so they are
not filesystem paths that can be validated before template expansion.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_docs as checker  # noqa: E402

_original_resolve = checker.resolve_local_target


def _resolve_local_target(source: Path, raw_target: str) -> Path | None:
    if "<%" in raw_target or "%>" in raw_target:
        return None
    return _original_resolve(source, raw_target)


checker.resolve_local_target = _resolve_local_target

if __name__ == "__main__":
    raise SystemExit(checker.main())
