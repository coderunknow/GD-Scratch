"""Procedural art for every costume and backdrop in the game.

All coordinates are in *logical* Scratch pixels. Sprites are rendered at 2x and
saved with ``bitmapResolution = 2`` so they stay crisp, exactly like the assets
that ship with Scratch itself.
"""

from __future__ import annotations

import math
import random

from .png import Image

# Palette ------------------------------------------------------------------
INK = (12, 14, 32, 255)
WHITE = (255, 255, 255, 255)

THEMES = {
    1: {  # "Stereo Sunrise" -- warm dusk
        "sky_top": (24, 20, 74),
        "sky_bottom": (198, 74, 120),
        "far": (70, 44, 118),
        "near": (40, 26, 84),
        "ground": (30, 20, 62),
        "ground_line": (255, 120, 170),
        "accent": (255, 214, 90),
        "block": (60, 170, 255),
        "block_dark": (18, 82, 158),
        "spike": (255, 240, 250),
        "player": (90, 230, 130),
        "player_ink": (18, 70, 44),
        "coin": (255, 208, 60),
        "seed": 11,
    },
    2: {  # "Neon Rush" -- cyan night city
        "sky_top": (4, 8, 30),
        "sky_bottom": (24, 90, 130),
        "far": (16, 44, 78),
        "near": (10, 26, 52),
        "ground": (10, 22, 44),
        "ground_line": (90, 240, 255),
        "accent": (120, 255, 220),
        "block": (255, 96, 168),
        "block_dark": (140, 24, 84),
        "spike": (230, 250, 255),
        "player": (255, 226, 84),
        "player_ink": (120, 84, 10),
        "coin": (140, 255, 220),
        "seed": 23,
    },
    3: {  # "Gravity Flux" -- violet void
        "sky_top": (10, 4, 28),
        "sky_bottom": (78, 24, 108),
        "far": (46, 18, 76),
        "near": (26, 10, 50),
        "ground": (22, 10, 44),
        "ground_line": (200, 130, 255),
        "accent": (255, 120, 240),
        "block": (150, 120, 255),
        "block_dark": (60, 40, 130),
        "spike": (250, 240, 255),
        "player": (120, 255, 210),
        "player_ink": (16, 80, 66),
        "coin": (255, 150, 240),
        "seed": 37,
    },
}

CELL = 30          # logical px per level cell
RES = 2            # bitmap resolution for sprite costumes


def _at2(img: Image) -> Image:
    return img.scale(RES)


# --- player ---------------------------------------------------------------
def player_cube(theme: dict) -> bytes:
    """The hero cube: chunky GD-style square with a face."""
    s = 30
    img = Image(s, s)
    body = theme["player"]
    ink = theme["player_ink"]
    img.rect(2, 2, s - 4, s - 4, body)
    img.frame(2, 2, s - 4, s - 4, ink, 2)
    img.frame(0, 0, s, s, (0, 0, 0, 120), 2)
    # inner highlight
    img.rect(5, 5, s - 12, 3, (255, 255, 255, 110))
    # face
    img.rect(9, 12, 4, 6, ink)
    img.rect(18, 12, 4, 6, ink)
    img.rect(9, 21, 13, 2, ink)
    img.rect(11, 20, 9, 1, ink)
    return _at2(img).to_png()


def player_ghost(theme: dict) -> bytes:
    """Faint after-image used while the cube is airborne."""
    s = 30
    img = Image(s, s)
    body = tuple(list(theme["player"])[:3]) + (90,)
    img.rect(3, 3, s - 6, s - 6, body)
    img.frame(3, 3, s - 6, s - 6, (255, 255, 255, 70), 1)
    return _at2(img).to_png()


# --- tiles ----------------------------------------------------------------
def tile_block(theme: dict) -> bytes:
    s = CELL
    img = Image(s, s)
    img.rect(0, 0, s, s, theme["block_dark"])
    img.rect(2, 2, s - 4, s - 4, theme["block"])
    img.frame(2, 2, s - 4, s - 4, (255, 255, 255, 130), 2)
    img.rect(5, 5, s - 14, 3, (255, 255, 255, 120))
    img.rect(5, s - 9, s - 10, 3, (0, 0, 0, 60))
    return _at2(img).to_png()


def tile_platform(theme: dict) -> bytes:
    """A thin floating ledge (top half of a cell is solid)."""
    s = CELL
    img = Image(s, s)
    img.rect(0, s // 2, s, s // 2, theme["block_dark"])
    img.rect(1, s // 2, s - 2, s // 2 - 2, theme["block"])
    img.rect(1, s // 2, s - 2, 2, (255, 255, 255, 150))
    return _at2(img).to_png()


def _spike(theme: dict, up: bool = True) -> bytes:
    s = CELL
    img = Image(s, s)
    pts = [(1, s - 1), (s // 2, 3), (s - 2, s - 1)]
    if not up:
        pts = [(1, 0), (s // 2, s - 4), (s - 2, 0)]
    img.polygon(pts, theme["spike"])
    # dark inner facet for depth
    inner = [(s // 2, 8), (s - 8, s - 2), (s // 2, s - 2)]
    if not up:
        inner = [(s // 2, s - 9), (s - 8, 1), (s // 2, 1)]
    img.polygon(inner, (0, 0, 0, 70))
    img.line(s // 2, 3 if up else s - 4, s // 2, s - 6 if up else 5,
             (255, 255, 255, 200), 1)
    return _at2(img).to_png()


def tile_spike_up(theme: dict) -> bytes:
    return _spike(theme, True)


def tile_spike_down(theme: dict) -> bytes:
    return _spike(theme, False)


def tile_coin(theme: dict) -> bytes:
    s = CELL
    img = Image(s, s)
    c = s // 2
    img.disc(c, c, 10, (0, 0, 0, 90))
    img.disc(c, c, 9, theme["coin"])
    img.disc(c, c, 6, (255, 255, 255, 200))
    img.disc(c, c, 4, theme["coin"])
    img.disc(c - 3, c - 3, 2, (255, 255, 255, 230))
    return _at2(img).to_png()


def tile_portal(theme: dict) -> bytes:
    """Gravity-flip portal: a tall glowing gate."""
    w, h = CELL, CELL * 3
    img = Image(w, h)
    img.rect(0, 0, w, h, (0, 0, 0, 0))
    img.frame(2, 2, w - 4, h - 4, theme["accent"], 3)
    for i in range(3, h - 3, 6):
        img.rect(4, i, w - 8, 3, (255, 255, 255, 90))
    img.polygon([(w // 2, h // 2 - 14), (w - 8, h // 2), (w // 2, h // 2 + 14)],
                theme["accent"])
    img.polygon([(w // 2 - 3, h // 2 - 8), (w - 11, h // 2), (w // 2 - 3, h // 2 + 8)],
                (255, 255, 255, 220))
    return _at2(img).to_png()


def tile_pad(theme: dict) -> bytes:
    """Yellow jump pad -- launches the cube much higher."""
    s = CELL
    img = Image(s, s)
    img.rect(2, s - 8, s - 4, 6, (0, 0, 0, 120))
    img.rect(3, s - 10, s - 6, 6, theme["accent"])
    img.rect(5, s - 14, s - 10, 4, (255, 255, 255, 200))
    return _at2(img).to_png()


def tile_orb(theme: dict) -> bytes:
    """Blue jump ring -- tap while airborne for a second jump."""
    s = CELL
    img = Image(s, s)
    c = s // 2
    img.disc(c, c, 11, (0, 0, 0, 80))
    img.disc(c, c, 10, (60, 200, 255, 255))
    img.disc(c, c, 6, (240, 252, 255, 255))
    img.disc(c, c, 3, (60, 200, 255, 255))
    return _at2(img).to_png()


def tile_finish(theme: dict) -> bytes:
    w, h = 12, 210
    img = Image(w, h)
    for y in range(0, h, 12):
        for x in range(0, w, 6):
            on = ((y // 12) + (x // 6)) % 2 == 0
            img.rect(x, y, 6, 12, (255, 255, 255, 255) if on else (20, 20, 20, 255))
    img.frame(0, 0, w, h, theme["accent"], 1)
    return _at2(img).to_png()


# --- world ----------------------------------------------------------------
def ground_strip(theme: dict, width: int = 480, height: int = 120,
                 flip: bool = False) -> bytes:
    """A horizontally tileable ground band with a neon edge line."""
    img = Image(width, height)
    img.rect(0, 0, width, height, theme["ground"])
    img.rect(0, 0, width, 3, theme["ground_line"])
    img.rect(0, 3, width, 2, (255, 255, 255, 120))
    # tileable grid: vertical seams every 30px, horizontals every 30px
    for x in range(0, width, CELL):
        img.vline(x, 6, height - 1, (255, 255, 255, 26))
    for y in range(6, height, CELL):
        img.hline(0, width - 1, y, (255, 255, 255, 22))
    # a subtle top-to-bottom fade so it sits in the scene
    for y in range(height):
        a = int(90 * y / height)
        img.hline(0, width - 1, y, (0, 0, 0, a))
    if flip:
        img = img.flip_v()
    return _at2(img).to_png()


def _skyline(width: int, height: int, color, seed: int, base: int,
             min_h: int, max_h: int, min_w: int, max_w: int) -> Image:
    rnd = random.Random(seed)
    img = Image(width, height)
    x = 0
    while x < width:
        w = rnd.randint(min_w, max_w)
        h = rnd.randint(min_h, max_h)
        img.rect(x, base - h, w, h, color)
        # windows
        for wy in range(base - h + 6, base - 4, 10):
            for wx in range(x + 4, x + w - 4, 8):
                if rnd.random() < 0.35:
                    img.rect(wx, wy, 3, 4, (255, 255, 255, 40))
        x += w + rnd.randint(4, 16)
    return img


def parallax_layer(theme: dict, key: str, seed: int) -> bytes:
    """A 480px-wide horizontally repeating background layer."""
    width, height = 480, 360
    img = Image(width, height)
    if key == "far":
        img.blit(_skyline(width, height, theme["far"], seed, 240, 40, 150, 24, 60), 0, 0)
    else:
        layer = _skyline(width, height, theme["near"], seed + 991, 300, 60, 210, 34, 84)
        layer.alpha_mul(0.92)
        img.blit(layer, 0, 0)
    return _at2(img).to_png()


def stars(width: int = 480, height: int = 360, seed: int = 7) -> bytes:
    rnd = random.Random(seed)
    img = Image(width, height)
    for _ in range(150):
        x = rnd.randint(0, width - 1)
        y = rnd.randint(0, int(height * 0.75))
        a = rnd.randint(60, 220)
        s = 1 if rnd.random() < 0.85 else 2
        img.rect(x, y, s, s, (255, 255, 255, a))
    return _at2(img).to_png()


# --- backdrops ------------------------------------------------------------
def backdrop(theme: dict, index: int) -> bytes:
    """Full 480x360 stage backdrop (rendered at 1x -- backdrops are never scaled)."""
    w, h = 480, 360
    img = Image(w, h)
    img.vgradient(0, 0, w, h, theme["sky_top"], theme["sky_bottom"])
    rnd = random.Random(theme["seed"] * 100 + index)
    for _ in range(170):
        x = rnd.randint(0, w - 1)
        y = rnd.randint(0, int(h * 0.8))
        a = rnd.randint(50, 230)
        img.rect(x, y, 1, 1, (255, 255, 255, a))
    # distant glow on the horizon
    for r in range(120, 0, -2):
        a = int(28 * (1 - r / 120))
        img.disc(120 + index * 130, 250, r, (255, 200, 255, a))
    # silhouetted skyline
    img.blit(_skyline(w, h, tuple(theme["near"]) + (255,), theme["seed"] + index,
                      250, 30, 120, 22, 58), 0, 0)
    img.rect(0, 250, w, 110, tuple(theme["ground"]) + (255,))
    return img.to_png()


def backdrop_menu() -> bytes:
    w, h = 480, 360
    img = Image(w, h)
    img.vgradient(0, 0, w, h, (8, 6, 26), (44, 16, 74))
    rnd = random.Random(4)
    for _ in range(220):
        x = rnd.randint(0, w - 1)
        y = rnd.randint(0, h - 1)
        img.rect(x, y, 1, 1, (255, 255, 255, rnd.randint(40, 220)))
    for r in range(200, 0, -3):
        img.disc(240, 300, r, (140, 60, 220, int(16 * (1 - r / 200))))
    for i in range(6):
        x = 20 + i * 82
        img.rect(x, 300 - (i % 3) * 26, 46, 60 + (i % 3) * 26, (18, 12, 44, 255))
        img.frame(x, 300 - (i % 3) * 26, 46, 60 + (i % 3) * 26, (120, 70, 200, 90), 1)
    img.rect(0, 300, w, 60, (10, 8, 26, 255))
    img.hline(0, w - 1, 300, (180, 120, 255, 200))
    return img.to_png()


def backdrop_dark() -> bytes:
    img = Image(480, 360, (6, 6, 14, 255))
    for y in range(0, 360, 4):
        img.hline(0, 479, y, (255, 255, 255, 6))
    return img.to_png()


# --- ui -------------------------------------------------------------------
def ui_button(w: int = 200, h: int = 44, accent=(120, 255, 220, 255)) -> bytes:
    img = Image(w, h)
    img.rounded_rect(0, 0, w, h, (16, 18, 40, 210), 10)
    img.frame(2, 2, w - 4, h - 4, accent, 2)
    img.rect(6, 5, w - 12, 2, (255, 255, 255, 70))
    return _at2(img).to_png()


def ui_selector(w: int = 260, h: int = 26, accent=(255, 214, 90, 255)) -> bytes:
    img = Image(w, h)
    img.frame(0, 0, w, h, accent, 3)
    img.rect(0, 0, w, h, (255, 255, 255, 26))
    return _at2(img).to_png()


def ui_panel(w: int = 380, h: int = 260) -> bytes:
    img = Image(w, h)
    img.rounded_rect(0, 0, w, h, (10, 10, 26, 225), 14)
    img.frame(3, 3, w - 6, h - 6, (140, 160, 255, 160), 2)
    return _at2(img).to_png()


def ui_bar(w: int = 300, h: int = 12) -> bytes:
    img = Image(w, h)
    img.rect(0, 0, w, h, (0, 0, 0, 160))
    img.frame(0, 0, w, h, (255, 255, 255, 170), 2)
    return _at2(img).to_png()


def ui_bar_fill(w: int = 296, h: int = 8) -> bytes:
    img = Image(w, h)
    img.hgradient(0, 0, w, h, (120, 255, 220, 255), (255, 214, 90, 255))
    return _at2(img).to_png()


def blank_pixel() -> bytes:
    """A 1x1 fully transparent PNG.

    Used as the costume of the invisible master-clock sprite. The sprite has
    to stay *shown* -- ``RenderedTarget.setXY`` only asks the runtime for a
    redraw when the target is both visible and attached to a renderer, and
    that request is what holds a ``forever`` loop to one iteration per frame.
    A transparent pixel keeps it off screen while it does so.
    """
    return _at2(Image(1, 1)).to_png()


def ui_dot(size: int = 8) -> bytes:
    img = Image(size, size)
    img.disc(size / 2, size / 2, size / 2 - 1, (255, 255, 255, 255))
    return _at2(img).to_png()


def ui_cursor(w: int = 22, h: int = 22) -> bytes:
    img = Image(w, h)
    img.polygon([(2, 2), (2, 17), (7, 13), (10, 19), (13, 17), (10, 11), (16, 11)],
                (255, 255, 255, 255))
    img.line(2, 2, 2, 17, (0, 0, 0, 255), 1)
    return _at2(img).to_png()


# --- particles ------------------------------------------------------------
def fx_spark(size: int = 8) -> bytes:
    img = Image(size, size)
    img.disc(size / 2, size / 2, size / 2 - 1, (255, 255, 255, 255))
    img.disc(size / 2, size / 2, size / 4, (255, 240, 180, 255))
    return _at2(img).to_png()


def fx_shard(size: int = 10) -> bytes:
    img = Image(size, size)
    img.polygon([(0, size - 1), (size // 2, 0), (size - 1, size - 1)],
                (255, 255, 255, 255))
    return _at2(img).to_png()


def fx_ring(size: int = 24) -> bytes:
    img = Image(size, size)
    img.disc(size / 2, size / 2, size / 2 - 1, (255, 255, 255, 200), filled=False, t=3)
    return _at2(img).to_png()


def fx_trail(size: int = 30) -> bytes:
    img = Image(size, size)
    img.rect(0, 0, size, size, (255, 255, 255, 60))
    img.alpha_mul(0.7)
    return _at2(img).to_png()


# --- glyph sheet ----------------------------------------------------------
def glyph_images() -> dict[str, bytes]:
    """One PNG per character, drawn from the bundled 5x7 font.

    Costume names are the characters themselves, so ``switch costume to (ch)``
    works directly with no lookup table at runtime.
    """
    from .font import GLYPHS

    out: dict[str, bytes] = {}
    # 4x with bitmapResolution 2 -> 10x14 logical px glyphs, crisp on retina
    scale = 4
    for ch, rows in GLYPHS.items():
        img = Image(5 * scale, 7 * scale)
        for gy, row in enumerate(rows):
            for gx, bit in enumerate(row):
                if bit == "#":
                    img.rect(gx * scale, gy * scale, scale, scale, (255, 255, 255, 255))
        name = "space" if ch == " " else ch
        out[name] = img.to_png()
    return out


def logo_image(text: str, scale: int = 6) -> bytes:
    """Big blocky wordmark used on the title screen."""
    from .font import GLYPH_W, GLYPHS

    n = len(text)
    w = n * (GLYPH_W + 1) * scale - scale
    h = 7 * scale
    img = Image(max(1, w), h)
    img.text(text, 0, 0, (255, 255, 255, 255), scale, 1,
             shadow=(20, 8, 40, 200), outline=(0, 0, 0, 255))
    return _at2(img).to_png()


# ===========================================================================
# Menu screens.
#
# Every *static* label in the game is baked into a backdrop here instead of
# being drawn at runtime: it renders crisply, costs nothing per frame, and
# keeps the runtime glyph pool small enough for only the values that actually
# change (percentages, attempt counters, coins, ON/OFF).
#
# Row positions are returned alongside each image so the selection highlight
# and the runtime text always line up with the artwork.
# ===========================================================================
_TITLE = (255, 255, 255)
_DIM = (168, 176, 214)
_ACCENT = (120, 255, 220)
_WARN = (255, 214, 90)


def _screen() -> Image:
    img = Image(480, 360)
    img.vgradient(0, 0, 480, 360, (10, 8, 34), (34, 16, 62))
    rnd = random.Random(4242)
    for _ in range(140):
        x = rnd.randint(0, 479)
        y = rnd.randint(0, 300)
        img.rect(x, y, 1, 1, (255, 255, 255, rnd.randint(30, 170)))
    for r in range(150, 0, -3):
        a = int(26 * (1 - r / 150))
        img.disc(240, 330, r, (120, 70, 200, a))
    return img


def _center(img: Image, s: str, cy: int, scale: int, color=_TITLE,
            outline=(0, 0, 0), shadow=(0, 0, 0, 190)) -> None:
    w = img.text_width(s, scale, 1)
    y = cy - (7 * scale) // 2
    img.text(s, (480 - w) // 2, y, color, scale, 1,
             shadow=shadow if shadow else None,
             outline=outline if outline else None)


def _rule(img: Image, y: int, x0: int = 90, x1: int = 390,
          color=(120, 140, 255, 120)) -> None:
    img.hline(x0, x1, y, color)


def screen_menu() -> bytes:
    img = _screen()
    _center(img, "GEOMETRY DASH", 62, 4, _TITLE)
    _center(img, "SCRATCH EDITION", 100, 2, _ACCENT, outline=None, shadow=None)
    _rule(img, 122)
    for i, label in enumerate(["PLAY", "LEVEL SELECT", "HOW TO PLAY", "SETTINGS"]):
        _center(img, label, 150 + i * 32, 2, _TITLE)
    _rule(img, 268)
    _center(img, "UP DOWN TO CHOOSE   SPACE OR CLICK", 300, 2, _DIM,
            outline=None, shadow=None)
    _center(img, "P PAUSE   R RETRY   M MUSIC", 324, 2, _DIM,
            outline=None, shadow=None)
    return img.to_png()


def screen_select(names: list[str]) -> bytes:
    img = _screen()
    _center(img, "SELECT LEVEL", 48, 3, _TITLE)
    _rule(img, 76)
    for i, name in enumerate(names):
        y = 116 + i * 46
        img.rounded_rect(70, y - 17, 340, 34, (16, 18, 44, 200), 8)
        img.frame(71, y - 16, 338, 32, (120, 140, 255, 90), 1)
        img.text(name, 86, y - 7, _TITLE, 2, 1, outline=(0, 0, 0))
    _center(img, "BEST PROGRESS AND COINS SHOWN AT RIGHT", 300, 2, _DIM,
            outline=None, shadow=None)
    return img.to_png()


def screen_settings(labels: list[str]) -> bytes:
    img = _screen()
    _center(img, "SETTINGS", 48, 3, _TITLE)
    _rule(img, 76)
    # 7 evenly spaced rows starting below the rule; the value pill is wide
    # enough for "ULTRA" and the selector costume (selWide, 360 px) reaches
    # past its right edge
    for i, label in enumerate(labels):
        y = 96 + i * 30
        img.text(label, 96, y - 7, _TITLE, 2, 1, outline=(0, 0, 0))
        img.rect(318, y - 9, 84, 18, (10, 12, 30, 220))
        img.frame(318, y - 9, 84, 18, (120, 140, 255, 120), 1)
    _center(img, "SPACE OR CLICK TO TOGGLE", 316, 2, _DIM, outline=None, shadow=None)
    return img.to_png()


def screen_help(lines: list[str]) -> bytes:
    img = _screen()
    _center(img, "HOW TO PLAY", 44, 3, _TITLE)
    _rule(img, 70)
    for i, line in enumerate(lines):
        _center(img, line, 98 + i * 27, 2, _TITLE if i < 6 else _DIM,
                outline=(0, 0, 0) if i < 6 else None,
                shadow=(0, 0, 0, 190) if i < 6 else None)
    _center(img, "CLICK OR PRESS SPACE TO GO BACK", 320, 2, _ACCENT,
            outline=None, shadow=None)
    return img.to_png()


def screen_pause() -> bytes:
    img = _screen()
    img.rect(0, 0, 480, 360, (4, 4, 14, 150))
    _center(img, "PAUSED", 80, 4, _TITLE)
    _rule(img, 118)
    for i, label in enumerate(["RESUME", "RESTART LEVEL", "QUIT TO MENU"]):
        _center(img, label, 160 + i * 34, 2, _TITLE)
    return img.to_png()


def screen_win() -> bytes:
    img = _screen()
    _center(img, "LEVEL COMPLETE", 60, 3, _WARN)
    _rule(img, 88)
    img.rounded_rect(110, 104, 260, 74, (16, 18, 44, 210), 10)
    img.frame(111, 105, 258, 72, (255, 214, 90, 130), 1)
    for i, label in enumerate(["NEXT LEVEL", "RETRY LEVEL", "QUIT TO MENU"]):
        _center(img, label, 216 + i * 34, 2, _TITLE)
    return img.to_png()


def hud_name(name: str, theme: dict) -> bytes:
    """Top-left level nameplate used during play."""
    w = 200
    img = Image(w, 22)
    img.rounded_rect(0, 0, w, 22, (8, 8, 22, 170), 6)
    img.rect(0, 0, 3, 22, theme["ground_line"] + (255,)
             if len(theme["ground_line"]) == 3 else theme["ground_line"])
    img.text(name, 12, 4, (255, 255, 255, 255), 2, 1, outline=(0, 0, 0, 255))
    return _at2(img).to_png()
