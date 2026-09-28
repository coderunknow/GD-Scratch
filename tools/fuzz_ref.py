"""Generate fuzz schedules and their exact reference traces.

Single source of truth for the fuzz tests: the schedules are derived from
seeded PRNGs here, and the traces come from gdscratch.verify -- the same
reference the fixtures use. tests/headless/fuzz.js shells out to this file so
the VM is always compared against the real reference, never a copy.

    PYTHONPATH=src python3 tools/fuzz_ref.py --level 1 --frames 400 \
        --seeds 1,2,3 [--out /tmp/ref.json]

Output JSON: {"level": N, "frames": F, "cases": [
    {"seed": S, "holds": [0/1...], "event": "run|die|win", "frame": lastStep,
     "trace": [[y, vy, grounded, grav], ...]}   # one row per step, 1..frame
]}
A schedule that is still running at --frames gets event "run" and a full-length
trace; the VM must agree on every one of those steps.
"""

import argparse
import json
import random
import sys

from gdscratch.levels import LEVELS
from gdscratch.verify import step, initial_state, DIE, WIN


def gen_holds(seed: int, n: int) -> list[int]:
    """Bursty random input: isolated taps and 2-4 frame holds, ~5.5% density."""
    r = random.Random(seed)
    holds = []
    burst = 0
    for _ in range(n):
        if burst > 0:
            holds.append(1)
            burst -= 1
        elif r.random() < 0.055:
            burst = r.randint(1, 4)
            holds.append(1)
            burst -= 1
        else:
            holds.append(0)
    return holds


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, required=True)
    ap.add_argument("--frames", type=int, default=400)
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    lv = LEVELS[args.level - 1]
    cases = []
    for seed in (int(s) for s in args.seeds.split(",")):
        holds = gen_holds(seed, args.frames)
        st = initial_state()
        trace = []
        event = "run"
        for f in range(1, args.frames + 1):
            st, ev = step(lv, st, holds[f - 1])
            trace.append([round(st.y, 9), round(st.vy, 9), st.grounded, st.grav])
            if ev == DIE:
                event = "die"
                break
            if ev == WIN:
                event = "win"
                break
        cases.append({"seed": seed, "holds": holds, "event": event,
                      "frame": len(trace), "trace": trace})

    out = json.dumps({"level": args.level, "frames": args.frames,
                      "cases": cases}, separators=(",", ":"))
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(out)
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
