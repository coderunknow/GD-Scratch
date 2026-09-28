"""Build the distributable .sb3 files.

    python3 -m gdscratch.build [--out dist]

Emits two archives:

``GD-Scratch.sb3``
    The stock build. Loads in scratch.mit.edu, the Scratch 3.32.1 desktop app
    and any other Scratch 3 runtime. Nothing outside the core block set.

``GD-Scratch-TurboWarp.sb3``
    Same project plus the ``runtimeOptions`` block TurboWarp reads to run at
    60fps with interpolation. Stock Scratch ignores unknown top-level keys, so
    this file also loads there; it just runs at 30fps.
"""

from __future__ import annotations

import argparse
import os

from .game import build_project


def build(out_dir: str = "dist", only: str | None = None) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for name, turbo in (("GD-Scratch.sb3", False),
                        ("GD-Scratch-TurboWarp.sb3", True)):
        if only and name != only:
            continue
        path = os.path.join(out_dir, name)
        build_project(turbo=turbo).save_sb3(path)
        written.append(path)
        print(f"{path}  {os.path.getsize(path) // 1024} KB")
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="dist", help="output directory")
    ap.add_argument("--only", default=None,
                    help="build a single archive by file name")
    a = ap.parse_args()
    build(a.out, a.only)


if __name__ == "__main__":
    main()
