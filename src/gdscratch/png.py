"""Tiny pure-Python RGBA raster + PNG writer used to generate every costume.

No third-party imaging library is required: the encoder emits a standard
8-bit RGBA PNG with adaptive row filtering, which is all Scratch needs.
"""

from __future__ import annotations

import struct
import zlib

from . import font as font_mod

Color = tuple  # (r, g, b) or (r, g, b, a)


def _norm(c: Color) -> tuple:
    if len(c) == 3:
        return (c[0], c[1], c[2], 255)
    return tuple(c)


def _blend(dst: tuple, src: tuple) -> tuple:
    sa = src[3]
    if sa >= 255:
        return src
    if sa <= 0:
        return dst
    da = dst[3]
    ia = 255 - sa
    out_a = sa + (da * ia) // 255
    if out_a == 0:
        return (0, 0, 0, 0)
    out = []
    for i in range(3):
        s = src[i] * sa
        d = dst[i] * da * ia / 255.0
        out.append(int(round((s + d) / out_a)))
    return (out[0], out[1], out[2], out_a)


def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


class Image:
    """A minimal RGBA image with the handful of primitives the art needs."""

    __slots__ = ("w", "h", "px")

    def __init__(self, w: int, h: int, fill: Color = (0, 0, 0, 0)):
        self.w = w
        self.h = h
        rgba = _norm(fill)
        self.px = bytearray(w * h * 4)
        if rgba != (0, 0, 0, 0):
            for i in range(w * h):
                o = i * 4
                self.px[o] = rgba[0]
                self.px[o + 1] = rgba[1]
                self.px[o + 2] = rgba[2]
                self.px[o + 3] = rgba[3]

    # -- pixel access ------------------------------------------------------
    def set(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            o = (y * self.w + x) * 4
            src = _norm(color)
            if src[3] >= 255:
                self.px[o] = src[0]
                self.px[o + 1] = src[1]
                self.px[o + 2] = src[2]
                self.px[o + 3] = 255
            else:
                dst = (self.px[o], self.px[o + 1], self.px[o + 2], self.px[o + 3])
                r = _blend(dst, src)
                self.px[o] = r[0]
                self.px[o + 1] = r[1]
                self.px[o + 2] = r[2]
                self.px[o + 3] = r[3]

    def get(self, x: int, y: int) -> tuple:
        o = (y * self.w + x) * 4
        return (self.px[o], self.px[o + 1], self.px[o + 2], self.px[o + 3])

    # -- shapes ------------------------------------------------------------
    def fill(self, color: Color) -> None:
        c = _norm(color)
        row = bytes(c) * self.w
        buf = bytearray()
        for _ in range(self.h):
            buf += row
        self.px = buf

    def rect(self, x: int, y: int, w: int, h: int, color: Color) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set(xx, yy, color)

    def frame(self, x: int, y: int, w: int, h: int, color: Color, t: int = 1) -> None:
        self.rect(x, y, w, t, color)
        self.rect(x, y + h - t, w, t, color)
        self.rect(x, y, t, h, color)
        self.rect(x + w - t, y, t, h, color)

    def rounded_rect(self, x: int, y: int, w: int, h: int, color: Color, r: int = 6) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                dx = min(xx - x, x + w - 1 - xx)
                dy = min(yy - y, y + h - 1 - yy)
                if dx < r and dy < r:
                    if (r - dx) ** 2 + (r - dy) ** 2 > r * r:
                        continue
                self.set(xx, yy, color)

    def hline(self, x0: int, x1: int, y: int, color: Color) -> None:
        for xx in range(min(x0, x1), max(x0, x1) + 1):
            self.set(xx, y, color)

    def vline(self, x: int, y0: int, y1: int, color: Color) -> None:
        for yy in range(min(y0, y1), max(y0, y1) + 1):
            self.set(x, yy, color)

    def line(self, x0: int, y0: int, x1: int, y1: int, color: Color, t: int = 1) -> None:
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        half = t // 2
        while True:
            for oy in range(-half, half + 1):
                for ox in range(-(t - 1 - half), half + 1):
                    self.set(x0 + ox, y0 + oy, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def disc(self, cx: float, cy: float, r: float, color: Color, filled: bool = True,
             t: int = 1) -> None:
        for yy in range(int(cy - r - 1), int(cy + r + 2)):
            for xx in range(int(cx - r - 1), int(cx + r + 2)):
                d = ((xx - cx) ** 2 + (yy - cy) ** 2) ** 0.5
                if filled:
                    if d <= r:
                        self.set(xx, yy, color)
                else:
                    if abs(d - r) <= t * 0.7:
                        self.set(xx, yy, color)

    def polygon(self, points: list[tuple], color: Color) -> None:
        if len(points) < 3:
            return
        ys = [p[1] for p in points]
        for yy in range(int(min(ys)), int(max(ys)) + 1):
            xs = []
            n = len(points)
            for i in range(n):
                x0, y0 = points[i]
                x1, y1 = points[(i + 1) % n]
                if (y0 <= yy < y1) or (y1 <= yy < y0):
                    xs.append(x0 + (yy - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.hline(int(round(xs[i])), int(round(xs[i + 1])), yy, color)

    def vgradient(self, x: int, y: int, w: int, h: int, top: Color, bottom: Color) -> None:
        top = _norm(top)
        bottom = _norm(bottom)
        for yy in range(h):
            f = yy / max(1, h - 1)
            c = tuple(int(round(top[i] + (bottom[i] - top[i]) * f)) for i in range(4))
            self.rect(x, y + yy, w, 1, c)

    def hgradient(self, x: int, y: int, w: int, h: int, left: Color, right: Color) -> None:
        left = _norm(left)
        right = _norm(right)
        for xx in range(w):
            f = xx / max(1, w - 1)
            c = tuple(int(round(left[i] + (right[i] - left[i]) * f)) for i in range(4))
            self.rect(x + xx, y, 1, h, c)

    # -- composition -------------------------------------------------------
    def blit(self, other: "Image", x: int, y: int, alpha: int = 255) -> None:
        for yy in range(other.h):
            for xx in range(other.w):
                c = other.get(xx, yy)
                if c[3] == 0:
                    continue
                if alpha < 255:
                    c = (c[0], c[1], c[2], (c[3] * alpha) // 255)
                self.set(x + xx, y + yy, c)

    def copy(self) -> "Image":
        out = Image(self.w, self.h)
        out.px = bytearray(self.px)
        return out

    def crop(self, x: int, y: int, w: int, h: int) -> "Image":
        out = Image(w, h)
        for yy in range(h):
            for xx in range(w):
                out.set(xx, yy, self.get(x + xx, y + yy))
        return out

    def flip_h(self) -> "Image":
        out = Image(self.w, self.h)
        for y in range(self.h):
            for x in range(self.w):
                out.set(self.w - 1 - x, y, self.get(x, y))
        return out

    def flip_v(self) -> "Image":
        out = Image(self.w, self.h)
        for y in range(self.h):
            for x in range(self.w):
                out.set(x, self.h - 1 - y, self.get(x, y))
        return out

    def scale(self, factor: int) -> "Image":
        out = Image(self.w * factor, self.h * factor)
        for y in range(self.h):
            for x in range(self.w):
                out.rect(x * factor, y * factor, factor, factor, self.get(x, y))
        return out

    def shift_colors(self, dr: int, dg: int, db: int) -> None:
        for i in range(0, len(self.px), 4):
            self.px[i] = max(0, min(255, self.px[i] + dr))
            self.px[i + 1] = max(0, min(255, self.px[i + 1] + dg))
            self.px[i + 2] = max(0, min(255, self.px[i + 2] + db))

    def alpha_mul(self, factor: float) -> None:
        for i in range(3, len(self.px), 4):
            self.px[i] = int(self.px[i] * factor)

    # -- text --------------------------------------------------------------
    def text_width(self, s: str, scale: int = 1, spacing: int = 1) -> int:
        n = len(s)
        if n == 0:
            return 0
        return n * (font_mod.GLYPH_W + spacing) * scale - spacing * scale

    def text(self, s: str, x: int, y: int, color: Color = (255, 255, 255),
             scale: int = 1, spacing: int = 1, shadow: Color | None = None,
             outline: Color | None = None) -> None:
        """Draw a string; ``x`` is the left edge, ``y`` the top edge."""
        if outline is not None:
            for dx, dy in ((-scale, 0), (scale, 0), (0, -scale), (0, scale)):
                self._text_raw(s, x + dx, y + dy, outline, scale, spacing)
        if shadow is not None:
            self._text_raw(s, x + scale, y + scale, shadow, scale, spacing)
        self._text_raw(s, x, y, color, scale, spacing)

    def _text_raw(self, s: str, x: int, y: int, color: Color, scale: int, spacing: int) -> None:
        cx = x
        for ch in s.upper():
            glyph = font_mod.GLYPHS.get(ch)
            if glyph is None:
                glyph = font_mod.GLYPHS[" "]
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit == "#":
                        self.rect(cx + gx * scale, y + gy * scale, scale, scale, color)
            cx += (font_mod.GLYPH_W + spacing) * scale

    # -- encoding ----------------------------------------------------------
    def to_png(self) -> bytes:
        raw = bytearray()
        stride = self.w * 4
        prev = bytearray(stride)
        for y in range(self.h):
            row = self.px[y * stride:(y + 1) * stride]
            best = None
            best_cost = None
            for flt in (0, 1, 2):
                out = bytearray(stride)
                cost = 0
                for i in range(stride):
                    a = row[i - 4] if (flt == 1 and i >= 4) else 0
                    b = prev[i] if flt == 2 else 0
                    v = (row[i] - a - b) & 0xFF
                    out[i] = v
                    c = v if v < 128 else 256 - v
                    cost += c
                if best_cost is None or cost < best_cost:
                    best_cost = cost
                    best = (flt, out)
            raw.append(best[0])
            raw += best[1]
            prev = row
        idat = zlib.compress(bytes(raw), 9)

        def chunk(tag: bytes, data: bytes) -> bytes:
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", _crc32(tag + data)))

        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 6, 0, 0, 0))
        png += chunk(b"IDAT", idat)
        png += chunk(b"IEND", b"")
        return png


def text_image(s: str, scale: int = 2, spacing: int = 1,
               color: Color = (255, 255, 255)) -> Image:
    """A transparent image containing just the rendered string."""
    tmp = Image(8, 8)
    w = tmp.text_width(s, scale, spacing)
    h = font_mod.GLYPH_H * scale
    img = Image(max(1, w), h)
    img.text(s, 0, 0, color, scale, spacing)
    return img
