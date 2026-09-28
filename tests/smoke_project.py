"""Builds a tiny but feature-complete .sb3 that exercises every construct the
real game uses (procedures, lists, clones, broadcasts, costumes, sounds).

It exists so the generator can be regression-tested in seconds:

    python3 tests/smoke_project.py tmp/smoke.sb3
    node tests/headless/harness.js tmp/smoke.sb3 tests/smoke_script.json
"""

from __future__ import annotations

import io
import math
import os
import struct
import sys
import wave

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from gdscratch import ops as o
from gdscratch.png import Image
from gdscratch.sb3 import Project, Target


def make_square(size: int, color) -> bytes:
    img = Image(size, size, color)
    img.frame(0, 0, size, size, (0, 0, 0, 255), 2)
    return img.to_png()


def make_beep(seconds: float = 0.05, rate: int = 22050, freq: float = 440.0) -> bytes:
    n = int(seconds * rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            v = int(12000 * math.sin(2 * math.pi * freq * i / rate) * (1 - i / n))
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))
    return buf.getvalue()


def build(path: str) -> Project:
    stage = Target("Stage", is_stage=True, layer_order=0)
    stage.add_costume("backdrop1", make_square(4, (30, 30, 60)), "png", 240, 180, 1)
    ticks = stage.var("ticks", 0)
    done = stage.var("done", 0)
    steps = stage.var("steps", 0)
    cloneRan = stage.var("cloneRan", 0)
    chars = stage.lst("chars", [])
    msg = stage.broadcast_var("go")

    player = Target("Player", layer_order=1)
    player.add_costume("square", make_square(30, (255, 200, 40)), "png", 15, 15, 1)
    player.add_sound("beep", make_beep(), 22050, 1102)

    bump = o.Proc(player, "bump", [("amount", "s")], warp=True)
    bump.define(
        o.change_var(steps, bump.arg(0)),
        o.change_x(bump.arg(0)),
        x=30, y=420, comment="smoke: custom block with a number argument",
    )
    player.script(
        o.when_flag(),
        o.set_var(ticks, 0),
        o.set_var(done, 0),
        o.set_var(steps, 0),
        o.delete_of_list("all", chars),
        o.repeat(3, o.add_to_list(o.join("x", o.letter_of(1, "ab")), chars)),
        o.repeat(20, o.change_var(ticks, 1)),
        o.if_(o.gt(o.length_of_list(chars), 2),
              o.broadcast("go", msg),
              o.change_var(steps, 100)),
        bump.call(5),
        o.set_var(done, 1),
        x=30, y=30, comment="smoke: lists, operators, broadcasts, procedure call",
    )
    player.script(
        o.when_broadcast("go", msg),
        o.create_clone("_myself_"),
        o.play_sound("beep"),
        x=430, y=30, comment="smoke: clone + sound",
    )
    player.script(
        o.as_clone(),
        o.change_x(10),
        o.set_var(cloneRan, 1),
        o.wait(0.05),
        o.delete_clone(),
        x=760, y=30, comment="smoke: clone body",
    )

    proj = Project(stage, [player])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    proj.save_sb3(path)
    return proj


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "tmp/smoke.sb3"
    build(out)
    print("wrote", out, os.path.getsize(out), "bytes")
