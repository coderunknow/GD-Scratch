"""Reference physics + level solver.

``step()`` is the single source of truth for how the cube moves. The Scratch
project is a literal transcription of it, and ``tests/headless`` replays a
solution inside scratch-vm and asserts the y-position matches bit-for-bit, so
the Python model and the real game cannot drift apart.

``solve()`` proves a level is completable: it searches the space of jump
timings and returns a per-frame "is the jump key held" schedule.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .levels import (
    CELL,
    CORNER_FORGIVE,
    CEIL_Y,
    GRAVITY,
    GY,
    HALF,
    JUMP_V,
    Level,
    MAX_FALL,
    ORB_V,
    PAD_V,
    PLAYER_X,
    ROWS,
    SPEED,
    SPIKE_H,
    SPIKE_INSET_X,
)

EPS = 1e-9

# event codes returned by step()
RUN = "run"
DIE = "die"
WIN = "win"


@dataclass(frozen=True)
class State:
    frame: int
    y: float
    vy: float
    grounded: int
    grav: int
    held_prev: int

    def key(self):
        return (self.frame, self.y, self.vy, self.grounded, self.grav, self.held_prev)


def world_x(frame: int) -> float:
    """Distance scrolled after ``frame`` steps (exact: SPEED is a power-of-10 float)."""
    return frame * SPEED


def player_x(frame: int) -> float:
    return world_x(frame) + PLAYER_X


def cell_range_x(px: float) -> range:
    return range(int(math.floor((px - HALF) / CELL)),
                 int(math.floor((px + HALF) / CELL)) + 1)


def cell_range_y(py: float) -> range:
    return range(int(math.floor((py - HALF - GY) / CELL)),
                 int(math.floor((py + HALF - GY) / CELL)) + 1)


def step(level: Level, st: State, hold: int):
    """Advance one 30fps frame. Returns (new_state, event).

    The block order below is the exact order used by the generated Scratch
    script -- do not reorder without updating ``game.py``.
    """
    frame = st.frame + 1
    px = player_x(frame)
    grav = st.grav
    vy = st.vy
    grounded = st.grounded
    y = st.y
    jump_edge = 1 if (hold and not st.held_prev) else 0

    # 1. jump (only while resting on something)
    if grounded and hold:
        vy = JUMP_V * grav
        grounded = 0

    # 2. gravity
    vy = vy - GRAVITY * grav

    # 3. clamp terminal speed
    if vy < -MAX_FALL:
        vy = -MAX_FALL
    if vy > MAX_FALL:
        vy = MAX_FALL

    # 4. integrate
    prev_y = y
    y = y + vy

    # 5. floor / ceiling
    if grav == 1 and y - HALF <= GY:
        y = GY + HALF
        vy = 0.0
        grounded = 1
    if grav == -1 and y + HALF >= CEIL_Y:
        y = CEIL_Y - HALF
        vy = 0.0
        grounded = 1

    # 6. tiles
    died = False
    launch = None
    portal = None
    win = False
    coins = 0
    used_orb = False

    cols = cell_range_x(px)
    rows = cell_range_y(y)

    # portals are full-height gates: passing their column always flips gravity
    for c in cols:
        for r in range(ROWS):
            ch = level.char(c, r)
            if ch in ("G", "N") and px + HALF > c * CELL + 6:
                portal = -1 if ch == "G" else 1
    for c in cols:
        for r in rows:
            ch = level.char(c, r)
            if ch == ".":
                continue
            x0 = c * CELL
            x1 = x0 + CELL
            y0 = GY + r * CELL
            y1 = y0 + CELL
            if not (px - HALF < x1 and x0 < px + HALF):
                continue

            if ch == "#":
                if not (y - HALF < y1 and y0 < y + HALF):
                    continue
                if grav == 1:
                    surface = y1
                    # corner forgiveness: the bottom may sit up to
                    # CORNER_FORGIVE px past the surface when the overlap
                    # starts; the cube then snaps on top instead of dying
                    if prev_y - HALF >= surface - CORNER_FORGIVE and vy <= 0:
                        y = surface + HALF
                        vy = 0.0
                        grounded = 1
                    else:
                        died = True
                else:
                    surface = y0
                    if prev_y + HALF <= surface + CORNER_FORGIVE and vy >= 0:
                        y = surface - HALF
                        vy = 0.0
                        grounded = 1
                    else:
                        died = True
            elif ch == "^":
                sx0 = x0 + SPIKE_INSET_X
                sx1 = x1 - SPIKE_INSET_X
                sy0 = y0
                sy1 = y0 + SPIKE_H
                if px - HALF < sx1 and sx0 < px + HALF and y - HALF < sy1 and sy0 < y + HALF:
                    died = True
            elif ch == "v":
                sx0 = x0 + SPIKE_INSET_X
                sx1 = x1 - SPIKE_INSET_X
                sy1 = y1
                sy0 = y1 - SPIKE_H
                if px - HALF < sx1 and sx0 < px + HALF and y - HALF < sy1 and sy0 < y + HALF:
                    died = True
            elif ch == "P":
                if y - HALF < y0 + 14 and y0 < y + HALF and vy * grav <= 0:
                    launch = PAD_V * grav
            elif ch == "O":
                if jump_edge and not used_orb and y - HALF < y1 and y0 < y + HALF:
                    launch = ORB_V * grav
                    used_orb = True
            elif ch == "C":
                if y - HALF < y1 and y0 < y + HALF:
                    coins += 1
            elif ch == "F":
                if px >= x0:
                    win = True

    if launch is not None:
        vy = launch
        grounded = 0
    if portal is not None and portal != grav:
        grav = portal
        grounded = 0

    # falling out of the world (only possible right after a gravity flip)
    if y < GY - 3 * CELL or y > CEIL_Y + 3 * CELL:
        died = True

    if died:
        return State(frame, y, vy, grounded, grav, hold), DIE
    if win:
        return State(frame, y, vy, grounded, grav, hold), WIN
    return State(frame, y, vy, grounded, grav, hold), RUN


def initial_state() -> State:
    return State(0, GY + HALF, 0.0, 1, 1, 0)


def progress(level: Level, frame: int) -> float:
    finish_x = level.finish_col() * CELL
    px = player_x(frame)
    return max(0.0, min(100.0, (px / finish_x) * 100.0))


def play(level: Level, holds, max_frames: int | None = None):
    """Run a whole attempt from a hold schedule. Returns (event, trace)."""
    st = initial_state()
    trace = [st]
    limit = max_frames or (level.length + 40) * int(CELL / SPEED) + 200
    for f in range(limit):
        hold = 1 if f < len(holds) and holds[f] else 0
        st, event = step(level, st, hold)
        trace.append(st)
        if event != RUN:
            return event, trace
    return RUN, trace


def solve(level: Level, max_states_per_frame: int = 20000):
    """Breadth-first search for a completing input schedule.

    Returns ``(holds, frames)`` or ``None`` when the level cannot be finished.
    ``best`` (attribute of the returned dict when using solve_detailed) records
    how far the search got, which is what makes an unsolvable level debuggable.
    """
    res = solve_detailed(level, max_states_per_frame)
    if res is None or res.get("holds") is None:
        return None
    return res["holds"], res["frames"]


def solve_detailed(level: Level, max_states_per_frame: int = 20000) -> dict | None:
    limit = (level.length + 60) * int(CELL / SPEED) + 600
    start = initial_state()
    came_from: dict = {start.key(): None}
    frontier = [start]
    best_frame = 0
    best_col = 0
    frames_seen = 0
    for _ in range(limit):
        nxt: dict = {}
        for st in frontier:
            for hold in (0, 1):
                st2, event = step(level, st, hold)
                if event == DIE:
                    continue
                k = st2.key()
                if k in came_from or k in nxt:
                    continue
                nxt[k] = (st.key(), hold)
                if st2.frame > best_frame:
                    best_frame = st2.frame
                    best_col = int(player_x(st2.frame) // CELL)
                if event == WIN:
                    came_from[k] = (st.key(), hold)
                    holds = []
                    node = k
                    while came_from.get(node) is not None:
                        prev, h = came_from[node]
                        holds.append(h)
                        node = prev
                    holds.reverse()
                    return {"holds": holds, "frames": st2.frame,
                            "best_frame": best_frame, "best_col": best_col}
        if not nxt:
            return {"holds": None, "frames": best_frame,
                    "best_frame": best_frame, "best_col": best_col}
        came_from.update(nxt)
        if len(nxt) > max_states_per_frame:
            nxt = dict(list(nxt.items())[:max_states_per_frame])
        frontier = [State(*k) for k in nxt]
        frames_seen += 1
    return None


def report() -> str:
    from .levels import LEVELS

    lines = []
    for level in LEVELS:
        res = solve(level)
        if res is None:
            lines.append(f"level {level.index} {level.name}: UNSOLVABLE")
            continue
        holds, frames = res
        event, trace = play(level, holds)
        lines.append(
            f"level {level.index} {level.name:16s} width={level.length:4d} "
            f"coins={level.coins()} solved in {frames} frames "
            f"({frames / 30:.1f}s) jumps={sum(holds)} replay={event}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
