#!/usr/bin/env python3
"""Prove every level is completable and dump replay schedules for the tests."""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from gdscratch.levels import LEVELS  # noqa: E402
from gdscratch.verify import play, progress, solve  # noqa: E402


def main() -> int:
    out_dir = os.path.join(ROOT, "tests", "fixtures")
    os.makedirs(out_dir, exist_ok=True)
    failures = []
    for level in LEVELS:
        res = solve(level)
        if res is None:
            print(f"  L{level.index} {level.name:<16} UNSOLVABLE")
            failures.append(level.index)
            continue
        holds, frames = res
        event, trace = play(level, holds)
        print(
            f"  L{level.index} {level.name:<16} width={level.length:<4} "
            f"finish={progress(level, frames):5.1f}%  frames={frames:<5} "
            f"({frames / 30:4.1f}s)  key-frames={sum(holds):<4} replay={event}"
        )
        if event != "win":
            failures.append(level.index)
        with open(os.path.join(out_dir, f"level{level.index}_solution.json"), "w") as fh:
            json.dump({
                "level": level.index,
                "name": level.name,
                "holds": holds,
                "frames": frames,
                "expectedEvent": event,
                "trace": [{"f": s.frame, "y": s.y, "vy": s.vy,
                           "grav": s.grav, "grounded": s.grounded} for s in trace],
                "coinsInLevel": level.coins(),
            }, fh)
    if failures:
        print(f"FAILED levels: {failures}")
        return 1
    print(f"all {len(LEVELS)} levels solvable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
