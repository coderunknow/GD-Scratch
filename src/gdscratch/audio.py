"""Procedural chiptune audio: every sound effect and music loop is synthesized.

Output is 16-bit mono PCM WAV at 22.05 kHz, which stock Scratch 3 decodes
through the WebAudio API with no extension required.
"""

from __future__ import annotations

import array
import io
import math
import random
import struct
import wave

RATE = 22050


def _freq(midi: float) -> float:
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


# --- synthesis ------------------------------------------------------------
def _waveform(kind: str, phase: float) -> float:
    p = phase - math.floor(phase)
    if kind == "square":
        return 1.0 if p < 0.5 else -1.0
    if kind == "pulse":
        return 1.0 if p < 0.25 else -1.0
    if kind == "saw":
        return 2.0 * p - 1.0
    if kind == "tri":
        return 4.0 * abs(p - 0.5) - 1.0
    if kind == "sine":
        return math.sin(2 * math.pi * p)
    return 1.0 if p < 0.5 else -1.0


def tone(buf, start: float, dur: float, midi: float, vol: float = 0.3,
         kind: str = "square", attack: float = 0.004, release: float = 0.05,
         detune: float = 0.0) -> None:
    i0 = int(start * RATE)
    n = int(dur * RATE)
    f = _freq(midi)
    phase = 0.0
    step = f / RATE
    rel = max(1, int(release * RATE))
    atk = max(1, int(attack * RATE))
    for i in range(n):
        idx = i0 + i
        if idx >= len(buf):
            break
        s = _waveform(kind, phase)
        if detune:
            s = 0.6 * s + 0.4 * _waveform(kind, phase * (1.0 + detune))
        env = 1.0
        if i < atk:
            env = i / atk
        tail = n - i
        if tail < rel:
            env *= tail / rel
        buf[idx] += s * vol * env
        phase += step


def noise(buf, start: float, dur: float, vol: float = 0.3,
          decay: float = 1.0, rnd: random.Random | None = None) -> None:
    rnd = rnd or random
    i0 = int(start * RATE)
    n = int(dur * RATE)
    for i in range(n):
        idx = i0 + i
        if idx >= len(buf):
            break
        env = (1.0 - (i / n)) ** decay
        buf[idx] += (rnd.random() * 2 - 1) * vol * env


def kick(buf, start: float, vol: float = 0.5) -> None:
    i0 = int(start * RATE)
    n = int(0.14 * RATE)
    for i in range(n):
        idx = i0 + i
        if idx >= len(buf):
            break
        t = i / RATE
        f = 130 * math.exp(-t * 22) + 45
        env = (1 - i / n) ** 2
        buf[idx] += math.sin(2 * math.pi * f * t) * vol * env


def _encode(samples) -> bytes:
    peak = max((abs(s) for s in samples), default=1.0)
    gain = 0.89 / peak if peak > 0.89 else 1.0
    frames = array.array("h")
    for s in samples:
        v = int(max(-1.0, min(1.0, s * gain)) * 32767)
        frames.append(v)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames.tobytes())
    return out.getvalue()


def _buffer(seconds: float):
    return array.array("f", bytes(4 * int(seconds * RATE)))


def _meta(data: bytes) -> tuple[int, int]:
    return RATE, (len(data) - 44) // 2


def _declick(buf) -> None:
    n = int(0.004 * RATE)
    for i in range(min(n, len(buf))):
        buf[i] *= i / n
        buf[len(buf) - 1 - i] *= i / n


# --- sound effects ---------------------------------------------------------
def sfx_jump() -> bytes:
    buf = _buffer(0.18)
    i0, n = 0, int(0.13 * RATE)
    for i in range(n):
        t = i / RATE
        f = 380 * (1 + 2.6 * (t / 0.13))
        env = (1 - i / n) ** 1.4
        buf[i] += math.sin(2 * math.pi * f * t) * 0.42 * env
    noise(buf, 0.0, 0.05, 0.09, 2.0, random.Random(11))
    _declick(buf)
    return _encode(buf)


def sfx_die() -> bytes:
    buf = _buffer(0.75)
    rnd = random.Random(7)
    noise(buf, 0.0, 0.5, 0.55, 1.6, rnd)
    tone(buf, 0.0, 0.34, 45, 0.38, "saw", release=0.2)
    tone(buf, 0.06, 0.30, 38, 0.32, "square", release=0.2)
    tone(buf, 0.14, 0.34, 31, 0.30, "square", release=0.25)
    kick(buf, 0.0, 0.7)
    _declick(buf)
    return _encode(buf)


def sfx_coin() -> bytes:
    buf = _buffer(0.32)
    tone(buf, 0.0, 0.09, 88, 0.32, "square", release=0.03)
    tone(buf, 0.07, 0.20, 95, 0.30, "square", release=0.10)
    _declick(buf)
    return _encode(buf)


def sfx_portal() -> bytes:
    buf = _buffer(0.42)
    n = int(0.36 * RATE)
    for i in range(n):
        t = i / RATE
        f = 300 + 1400 * (0.5 + 0.5 * math.sin(t * 26))
        env = (1 - i / n) ** 1.2
        buf[i] += math.sin(2 * math.pi * f * t) * 0.28 * env
    noise(buf, 0.0, 0.2, 0.10, 2.0, random.Random(23))
    _declick(buf)
    return _encode(buf)


def sfx_pad() -> bytes:
    buf = _buffer(0.30)
    n = int(0.24 * RATE)
    for i in range(n):
        t = i / RATE
        f = 220 * (1 + 5.0 * (t / 0.24) ** 1.5)
        env = (1 - i / n) ** 1.1
        buf[i] += math.sin(2 * math.pi * f * t) * 0.36 * env
    _declick(buf)
    return _encode(buf)


def sfx_orb() -> bytes:
    buf = _buffer(0.26)
    tone(buf, 0.0, 0.10, 81, 0.28, "tri", release=0.04)
    tone(buf, 0.06, 0.16, 88, 0.26, "tri", release=0.08)
    _declick(buf)
    return _encode(buf)


def sfx_click() -> bytes:
    buf = _buffer(0.09)
    tone(buf, 0.0, 0.05, 84, 0.26, "square", release=0.02)
    noise(buf, 0.0, 0.02, 0.12, 2.0, random.Random(31))
    _declick(buf)
    return _encode(buf)


def sfx_select() -> bytes:
    buf = _buffer(0.22)
    tone(buf, 0.0, 0.07, 79, 0.26, "square", release=0.03)
    tone(buf, 0.05, 0.14, 86, 0.24, "square", release=0.07)
    _declick(buf)
    return _encode(buf)


def sfx_win() -> bytes:
    buf = _buffer(1.5)
    seq = [(72, 0.0), (76, 0.13), (79, 0.26), (84, 0.39), (88, 0.56), (91, 0.73)]
    for midi, at in seq:
        tone(buf, at, 0.34, midi, 0.24, "square", release=0.14)
        tone(buf, at, 0.34, midi - 12, 0.16, "tri", release=0.14)
    tone(buf, 0.9, 0.55, 96, 0.22, "square", release=0.4)
    noise(buf, 0.9, 0.35, 0.09, 1.5, random.Random(47))
    _declick(buf)
    return _encode(buf)


# --- music -----------------------------------------------------------------
# chord = (bass midi, [chord tones])
CHORDS = {
    "Am": (45, [57, 60, 64]),
    "F": (41, [53, 57, 60]),
    "C": (48, [55, 60, 64]),
    "G": (43, [55, 59, 62]),
    "Dm": (38, [50, 53, 57]),
    "Bb": (46, [58, 62, 65]),
    "Em": (40, [52, 55, 59]),
    "D": (38, [50, 54, 57]),
}


def music(bpm: int, progression: list[str], bars: int = 4, seed: int = 1,
          lead: str = "square", bass: str = "square", energy: float = 1.0,
          lead_octave: int = 12) -> bytes:
    """Render a seamlessly looping chiptune of ``bars`` bars."""
    rnd = random.Random(seed)
    beats_per_bar = 4
    sixteenths = bars * beats_per_bar * 4
    step = 60.0 / bpm / 4
    total = sixteenths * step + 0.05
    buf = _buffer(total)

    for s in range(sixteenths):
        t = s * step
        bar = s // (beats_per_bar * 4)
        beat_in_bar = (s // 4) % beats_per_bar
        six_in_beat = s % 4
        bass_midi, chord = CHORDS[progression[bar % len(progression)]]

        # drums
        if beat_in_bar in (0, 2) and six_in_beat == 0:
            kick(buf, t, 0.44 * energy)
        if beat_in_bar in (1, 3) and six_in_beat == 0:
            noise(buf, t, 0.09, 0.16 * energy, 2.5, rnd)
        if six_in_beat % 2 == 0:
            noise(buf, t, 0.03, 0.05 * energy, 3.0, rnd)

        # bass: driving eighths
        if six_in_beat % 2 == 0:
            note = bass_midi if (s // 2) % 2 == 0 else bass_midi + 12
            tone(buf, t, step * 1.8, note, 0.20 * energy, bass, release=0.03)

        # arpeggiated lead
        if not (six_in_beat == 3 and rnd.random() < 0.35):
            idx = (s * 3) % len(chord)
            note = chord[idx] + lead_octave
            if beat_in_bar == 3 and six_in_beat >= 2:
                note += 12
            tone(buf, t, step * 1.5, note, 0.115 * energy, lead, release=0.05)

        # pad on the downbeat of every other bar
        if s % (beats_per_bar * 4) == 0 and bar % 2 == 1:
            for note in chord:
                tone(buf, t, step * 6, note + 12, 0.055 * energy, "tri",
                     attack=0.02, release=0.3)

    _declick(buf)
    return _encode(buf)


def menu_music() -> bytes:
    return music(100, ["Am", "F", "C", "G"], seed=3, lead="tri", bass="tri",
                 energy=0.8)


def level_music(index: int) -> bytes:
    if index == 1:
        return music(142, ["Am", "F", "C", "G"], seed=17, energy=1.0)
    if index == 2:
        return music(158, ["Dm", "Bb", "F", "C"], seed=29, lead="pulse",
                     energy=1.05)
    return music(176, ["Em", "C", "G", "D"], seed=41, lead="pulse",
                 bass="saw", energy=1.12)


# public alias -- the sb3 asset table needs (rate, sampleCount) per sound
meta = _meta
