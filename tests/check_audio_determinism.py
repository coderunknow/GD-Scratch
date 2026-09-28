#!/usr/bin/env python3
"""Verify that every generated game sound is reproducible byte-for-byte.

    PYTHONPATH=src python3 tests/check_audio_determinism.py

The release archives name audio assets by MD5, so noise synthesized from the
module-global RNG can change sound content, asset names, and project JSON on an
otherwise identical build. Build each declared sound twice in this process and
compare raw WAV bytes, not just filenames.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from gdscratch.game import _sounds


def main() -> int:
    first = list(_sounds())
    second = list(_sounds())
    if [name for name, _ in first] != [name for name, _ in second]:
        print("FAIL: sound order changed between syntheses")
        return 1
    changed = [name for (name, a), (_, b) in zip(first, second) if a != b]
    if changed:
        print(f"FAIL: nondeterministic sound assets: {', '.join(changed)}")
        return 1
    print(f"PASS: {len(first)} synthesized sounds are byte-for-byte deterministic")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
