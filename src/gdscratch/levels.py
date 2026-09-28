"""Level data and the physics constants shared by the game and the verifier.

A level is a grid of characters. Column ``c`` spans world x in
``[c*CELL, (c+1)*CELL)`` and row ``r`` spans world y in
``[GY + r*CELL, GY + (r+1)*CELL)`` (row 0 sits directly on the ground).

Charset
-------
    .   empty
    #   solid block (land on top of it, die if you hit its side)
    ^   spike pointing up        (deadly)
    v   spike pointing down      (deadly, for inverted sections)
    P   yellow jump pad          (big launch)
    O   blue jump ring           (tap in mid-air for another jump)
    C   collectible coin
    G   portal: set gravity to INVERTED (fall upward)
    N   portal: set gravity to NORMAL (fall downward)
    F   finish line

The same constants drive the generated Scratch project and the Python
verifier, and the headless test replays a verified solution inside scratch-vm
to prove the two agree.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- shared physics -------------------------------------------------------
CELL = 30.0            # logical px per grid cell (also the cube's size)
HALF = 15.0            # half of the player's collision box
GY = -120.0            # y of the ground surface
CEIL_Y = 120.0         # y of the ceiling (used by gravity-flip sections)
ROWS = 8               # rows encoded per level
PLAYER_X = -110.0      # fixed screen x of the cube
SPEED = 10.0           # world scroll px per 30fps frame
GRAVITY = 3.8          # px per frame^2, applied against the gravity direction
JUMP_V = 27.0          # launch speed of a normal jump (clears 2 cells, not 3)
PAD_V = 32.0           # launch speed of a yellow pad (~4 cells of height)
ORB_V = 25.0           # launch speed of a blue ring
MAX_FALL = 24.0        # terminal speed (must stay below CELL to avoid tunneling)
ROT_PER_FRAME = 26.0   # cube spin while airborne, degrees per frame

SPIKE_INSET_X = 8.0    # spike hitbox is narrower than its art, like real GD
SPIKE_H = 20.0         # spike hitbox height measured from its base


@dataclass
class Level:
    index: int
    name: str
    short: str
    rows: list[str]
    music: str
    hint: str = ""

    def __post_init__(self):
        width = max(len(r) for r in self.rows)
        self.rows = [r.ljust(width, ".") for r in self.rows]
        while len(self.rows) < ROWS:
            self.rows.append("." * width)
        self.rows = self.rows[:ROWS]
        self.width = width

    # -- queries ---------------------------------------------------------
    @property
    def length(self) -> int:
        return self.width

    @property
    def flat(self) -> str:
        """The level as one string, rows separated by '|' (row 0 first)."""
        return "|".join(self.rows)

    def char(self, col: int, row: int) -> str:
        if col < 0 or col >= self.width or row < 0 or row >= ROWS:
            return "."
        return self.rows[row][col]

    def finish_col(self) -> int:
        for c in range(self.width):
            for r in range(ROWS):
                if self.char(c, r) == "F":
                    return c
        return self.width - 1

    def coins(self) -> int:
        return sum(r.count("C") for r in self.rows)

    def difficulty(self) -> str:
        return {1: "EASY", 2: "NORMAL", 3: "HARD"}.get(self.index, "?")


# --------------------------------------------------------------------------
# Pattern library. A pattern is a list of row strings, index 0 = ground row.
# --------------------------------------------------------------------------
P: dict[str, list[str]] = {
    "-": ["."],                      # one empty column
    "--": [".."],
    "run4": ["...."],
    "run6": ["......"],
    "run8": ["........"],
    "s1": ["^"],
    "s2": ["^^"],
    "s3": ["^^^"],
    "b1": ["#"],
    "b2": ["##"],
    "b3": ["###"],
    "col2": ["#", "#"],              # 2-tall pillar
    "col3": ["#", "#", "#"],   # 3-tall: only clearable with a pad
    "step": [".", "#"],              # jump onto a 1-high block, gap in front
    "stairs": ["..", ".#", "##"],    # 3 columns, rising
    "gap3": ["...", "..."],
    "pit2": ["..", "..", ".."],
    "pad": ["P"],
    "orb": [".", ".", "O"],
    "coin1": [".", "C"],
    "coin2": [".", ".", "C"],
    "coin3": [".", "C", "C"],
    "portal": ["G"],
    "ceiling1": [".", ".", ".", ".", ".", ".", ".", "v"],
    "ceiling2": [".", ".", ".", ".", ".", ".", ".", "vv"],
    "floor_spike_under": ["^"],
}


def compose(pieces: list[str]) -> list[str]:
    """Concatenate pattern names into level rows (bottom row first)."""
    rows = [""] * ROWS
    for name in pieces:
        pat = P[name]
        width = max(len(s) for s in pat)
        for r in range(ROWS):
            piece = pat[r] if r < len(pat) else ""
            rows[r] += piece.ljust(width, ".")
    return rows


def append(rows: list[str], more: str, row: int = 0) -> list[str]:
    """Append a raw string to one row (used for ceilings and finish lines)."""
    out = list(rows)
    out[row] = out[row] + more
    return out


def finish(rows: list[str], tail: int = 6) -> list[str]:
    """Add the finish line and a short run-out."""
    out = [r + "." * 2 for r in rows]
    out[0] = out[0] + "F" + "." * tail
    for r in range(1, ROWS):
        out[r] = out[r] + "." * (tail + 1)
    return out


# --------------------------------------------------------------------------
# Level 1 -- "Stereo Sunrise": learn to jump. Generous spacing.
# --------------------------------------------------------------------------
_L1 = compose([
    "run8", "s1", "run6", "s1", "run6",
    "s2", "run6", "b1", "run4", "coin1", "run4",
    "s1", "run4", "s1", "run6",
    "col2", "run6", "s2", "run6",
    "b1", "run4", "s1", "run4", "coin1", "run4",
    "s3", "run6", "b2", "run4", "s1", "run6",
    "step", "run4", "s2", "run6",
    "pad", "run6", "coin2", "run4", "col2", "run6",
    "s2", "run4", "s1", "run4", "b1", "run6",
    "orb", "run6", "coin1", "run4", "s2", "run6",
    "col2", "run4", "s1", "run4", "s2", "run6",
    "s1", "run4", "b2", "run4", "coin1", "run4", "s2", "run4",
])
_L1 = finish(_L1, tail=8)

# --------------------------------------------------------------------------
# Level 2 -- "Neon Rush": triples, pillars and ring jumps.
# --------------------------------------------------------------------------
_L2 = compose([
    "run8", "s2", "run4", "s3", "run6",
    "col2", "run4", "s2", "run4", "coin1", "run4",
    "s3", "run6", "b2", "run4", "s1", "run4",
    "pad", "run4", "coin2", "run4", "col2", "run6",
    "s2", "run4", "s2", "run4", "orb", "run4", "coin1", "run4",
    "b3", "run4", "s3", "run6",
    "s1", "run4", "col2", "run4", "s2", "run4", "b1", "run4",
    "orb", "run4", "coin3", "run4", "s3", "run6",
    "pad", "run6", "col2", "run4", "s2", "run4", "s1", "run4",
    "s3", "run6", "b2", "run4", "coin1", "run4",
    "col2", "run4", "s1", "run4", "s2", "run4", "col2", "run4",
    "orb", "run6", "s2", "run4", "coin1", "run4", "s3", "run4",
])
_L2 = finish(_L2, tail=8)

# --------------------------------------------------------------------------
# Level 3 -- "Gravity Flux": ground -> inverted -> ground -> inverted -> ground.
#
# A gravity flip moves the cube 210px (7 cells) to the other surface, which
# takes ~4 cells of travel, so every portal gets 8 clear cells on both sides.
# --------------------------------------------------------------------------
def _build_l3(width: int = 300) -> list[str]:
    g = [["."] * width for _ in range(ROWS)]

    def put(c: int, r: int, ch: str) -> None:
        if 0 <= c < width and 0 <= r < ROWS:
            g[r][c] = ch

    def spikes(c: int, n: int = 1, r: int = 0) -> None:
        for i in range(n):
            put(c + i, r, "^")

    def cspikes(c: int, n: int = 1) -> None:
        for i in range(n):
            put(c + i, ROWS - 1, "v")

    def blocks(c: int, n: int = 1, r: int = 0, h: int = 1) -> None:
        for i in range(n):
            for k in range(h):
                put(c + i, r + k, "#")

    def coin(c: int, r: int = 1) -> None:
        put(c, r, "C")

    # --- section A: on the ground --------------------------------------
    spikes(12)
    spikes(20, 2)
    blocks(28, h=2)
    coin(30, 3)
    spikes(34)
    put(46, 0, "G")                     # -> inverted

    # --- section B: inverted corridor ----------------------------------
    cspikes(58)
    cspikes(66, 2)
    coin(74, ROWS - 2)
    cspikes(80)
    cspikes(88, 2)
    cspikes(96)
    coin(102, ROWS - 2)
    put(112, ROWS - 1, "N")             # -> back to normal

    # --- section C: on the ground --------------------------------------
    spikes(126, 2)
    put(134, 0, "P")
    coin(138, 3)
    blocks(144, h=2)
    coin(146, 3)
    spikes(152, 3)
    put(160, 2, "O")
    coin(163, 1)
    spikes(168)
    put(176, 0, "G")                    # -> inverted

    # --- section D: inverted corridor ----------------------------------
    cspikes(190, 2)
    cspikes(198)
    coin(204, ROWS - 2)
    cspikes(210, 2)
    cspikes(218)
    cspikes(226, 2)
    put(238, ROWS - 1, "N")             # -> back to normal

    # --- section E: final sprint ---------------------------------------
    spikes(252, 2)
    blocks(260, h=2)
    coin(262, 3)
    spikes(268, 2)
    put(274, 2, "O")
    spikes(278)
    put(286, 0, "F")
    return ["".join(row) for row in g]


_L3 = _build_l3()


LEVELS = [
    Level(index=1, name="STEREO SUNRISE", short="SUNRISE", rows=_L1,
          music="music1", hint="HOLD SPACE OR CLICK TO JUMP"),
    Level(index=2, name="NEON RUSH", short="NEON", rows=_L2,
          music="music2", hint="BLUE RINGS JUMP IN MID AIR"),
    Level(index=3, name="GRAVITY FLUX", short="FLUX", rows=_L3,
          music="music3", hint="PORTALS FLIP YOUR GRAVITY"),
]
