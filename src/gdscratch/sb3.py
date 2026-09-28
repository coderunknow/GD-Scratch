"""Scratch 3 (.sb3) project model and serializer.

The JSON layout produced here mirrors exactly what ``scratch-vm`` writes back out
(see ``scratch-vm/src/serialization/sb3.js``):

* input primitives use the numeric type tags (4 = math number, 10 = text, ...)
* input shape tags: 1 = block-is-its-own-shadow, 2 = block with no shadow
  (also used for substacks), 3 = block plus separate shadow
* fields are ``[value, id]`` pairs
* assets are stored as ``<md5>.<ext>`` inside the zip, with ``assetId`` == md5

Nothing here depends on Scratch internals that are not present in the copy of
``scratch-vm`` vendored under ``tests/headless`` which is used to validate the
result.
"""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import zipfile

# --- primitive input type tags (scratch-vm/src/serialization/sb3.js) ---------
MATH_NUM = 4
POSITIVE_NUM = 5
WHOLE_NUM = 6
INTEGER_NUM = 7
ANGLE_NUM = 8
COLOR = 9
TEXT = 10
BROADCAST = 11
VAR = 12
LIST = 13

# --- input shape tags --------------------------------------------------------
INPUT_SAME_BLOCK_SHADOW = 1
INPUT_BLOCK_NO_SHADOW = 2
INPUT_DIFF_BLOCK_SHADOW = 3


def fmt_num(value) -> str:
    """Render a number the way Scratch stores it (as a JSON string).

    Python ``repr`` for a float yields the shortest decimal that round-trips to
    the same IEEE-754 double, and JS ``parseFloat`` maps that same decimal back
    to the identical double, so numeric constants survive the trip bit-exactly.
    """
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e15:
            return str(int(value))
        return repr(value)
    return str(value)


class Lit:
    """A typed literal value used as a block input."""

    __slots__ = ("kind", "value")

    def __init__(self, kind: int, value):
        self.kind = kind
        self.value = value


def num(value) -> Lit:
    return Lit(MATH_NUM, fmt_num(value))


def positive_num(value) -> Lit:
    return Lit(POSITIVE_NUM, fmt_num(value))


def whole_num(value) -> Lit:
    return Lit(WHOLE_NUM, fmt_num(value))


def integer_num(value) -> Lit:
    return Lit(INTEGER_NUM, fmt_num(value))


def angle(value) -> Lit:
    return Lit(ANGLE_NUM, fmt_num(value))


def color(value: str) -> Lit:
    return Lit(COLOR, value)


def txt(value) -> Lit:
    return Lit(TEXT, str(value))


def broadcast(name: str, broadcast_id: str) -> Lit:
    return Lit(BROADCAST, (name, broadcast_id))


class Var:
    """Reference to a scalar variable (getter when used as an input)."""

    __slots__ = ("name", "id", "target")

    def __init__(self, name: str, var_id: str, target=None):
        self.name = name
        self.id = var_id
        self.target = target


class ListVar:
    """Reference to a list (contents reporter when used as an input)."""

    __slots__ = ("name", "id", "target")

    def __init__(self, name: str, var_id: str, target=None):
        self.name = name
        self.id = var_id
        self.target = target


def _flatten(blocks) -> list:
    """Flatten nested lists of blocks so callers can splice helper output."""
    out = []
    for b in blocks or []:
        if b is None:
            continue
        if isinstance(b, (list, tuple)):
            out.extend(_flatten(b))
        else:
            out.append(b)
    return out


class Sub:
    """A stack of blocks used as a substack (C-shaped input)."""

    __slots__ = ("blocks",)

    def __init__(self, blocks=None):
        self.blocks = _flatten(blocks)


class Menu:
    """A dropdown-menu shadow block (e.g. the menu inside ``motion_goto``)."""

    __slots__ = ("block",)

    def __init__(self, block: "Block"):
        self.block = block


class Plugged:
    """A reporter plugged into a dropdown, keeping the menu as its shadow.

    This is exactly what Scratch writes when you drag a variable over a
    dropdown (e.g. ``switch costume to (my char)``).
    """

    __slots__ = ("value", "menu")

    def __init__(self, value, menu: "Block"):
        self.value = value
        self.menu = menu


class Block:
    """A single Scratch block node."""

    __slots__ = ("opcode", "inputs", "fields", "mutation")

    def __init__(self, opcode: str, inputs=None, fields=None, mutation=None):
        self.opcode = opcode
        self.inputs = dict(inputs or {})
        self.fields = dict(fields or {})
        self.mutation = mutation


class Script:
    """A top-level stack of blocks (with an optional editor comment)."""

    __slots__ = ("blocks", "x", "y", "comment")

    def __init__(self, blocks, x: int = 0, y: int = 0, comment: str | None = None):
        self.blocks = list(blocks)
        self.x = x
        self.y = y
        self.comment = comment


class Costume:
    def __init__(self, name: str, data: bytes, ext: str, cx: float, cy: float,
                 resolution: int = 1):
        self.name = name
        self.data = data
        self.ext = ext
        self.cx = cx
        self.cy = cy
        self.resolution = resolution
        self.md5 = hashlib.md5(data).hexdigest()
        self.md5ext = f"{self.md5}.{ext}"


class Sound:
    def __init__(self, name: str, data: bytes, rate: int, sample_count: int,
                 data_format: str = "wav"):
        self.name = name
        self.data = data
        self.rate = rate
        self.sample_count = sample_count
        self.data_format = data_format
        self.md5 = hashlib.md5(data).hexdigest()
        self.md5ext = f"{self.md5}.{data_format}"


# Scratch identifiers are project-global; see Target.new_id.
_ID_COUNTER = itertools.count(1)


class Target:
    """A stage or sprite."""

    def __init__(self, name: str, is_stage: bool = False, layer_order: int = 0):
        self.name = name
        self.is_stage = is_stage
        self.layer_order = layer_order
        self.variables: dict[str, list] = {}
        self.lists: dict[str, list] = {}
        self.broadcasts: dict[str, str] = {}
        self.scripts: list[Script] = []
        self.costumes: list[Costume] = []
        self.sounds: list[Sound] = []
        self.current_costume = 0
        self.volume = 100
        self.visible = True
        self.x = 0.0
        self.y = 0.0
        self.size = 100.0
        self.direction = 90.0
        self.draggable = False
        self.rotation_style = "all around"
        # stage-only
        self.tempo = 60
        self.video_transparency = 50
        self.video_state = "on"
        self.text_to_speech_language = None
        self._var_ids = {}

    # -- variables ---------------------------------------------------------
    def new_id(self, prefix: str = "b") -> str:
        """Allocate an ID that is unique across the *whole project*.

        Scratch resolves a variable reference against the owning target's own
        variables before falling back to the stage, so a sprite-local that
        shares an ID with a stage variable silently shadows it: every
        ``state = "menu"`` test on a sprite that also declared a local would
        read the local instead. A single shared counter avoids that while
        keeping the build byte-for-byte reproducible.
        """
        return f"{prefix}{next(_ID_COUNTER)}"

    def var(self, name: str, value=0, local: bool | None = None) -> Var:
        """Declare (once) and return a scalar variable."""
        key = ("local" if (local if local is not None else not self.is_stage) else "global", name)
        if key in self._var_ids:
            vid = self._var_ids[key]
        else:
            vid = self.new_id("v")
            self._var_ids[key] = vid
            self.variables[vid] = [name, value]
        return Var(name, vid, self)

    def have_var(self, name: str, local: bool | None = None) -> bool:
        key = ("local" if (local if local is not None else not self.is_stage) else "global", name)
        return key in self._var_ids

    def lst(self, name: str, values=None) -> ListVar:
        vid = self._var_ids.get(("list", name))
        if vid is None:
            vid = self.new_id("l")
            self._var_ids[("list", name)] = vid
            self.lists[vid] = [name, list(values or [])]
        return ListVar(name, vid, self)

    def broadcast_var(self, name: str) -> str:
        """Declare a broadcast message and return its id."""
        for bid, bname in self.broadcasts.items():
            if bname == name:
                return bid
        bid = self.new_id("m")
        self.broadcasts[bid] = name
        return bid

    # -- assets ------------------------------------------------------------
    def add_costume(self, name: str, data: bytes, ext: str, cx: float, cy: float,
                    resolution: int = 2) -> Costume:
        c = Costume(name, data, ext, cx, cy, resolution)
        self.costumes.append(c)
        return c

    def add_sound(self, name: str, data: bytes, rate: int, sample_count: int) -> Sound:
        s = Sound(name, data, rate, sample_count)
        self.sounds.append(s)
        return s

    # -- scripts -----------------------------------------------------------
    def script(self, *blocks, x: int = 0, y: int = 0, comment: str | None = None) -> Script:
        s = Script(blocks, x, y, comment)
        self.scripts.append(s)
        return s

    # -- serialization -----------------------------------------------------
    def _fields(self, block: Block) -> dict:
        out = {}
        for key, value in block.fields.items():
            if isinstance(value, (Var, ListVar)):
                out[key] = [value.name, value.id]
            elif isinstance(value, tuple):
                out[key] = [value[0], value[1]]
            else:
                out[key] = [value, None]
        return out

    def _input(self, val, parent_id: str, out: dict):
        if val is None:
            return None
        if isinstance(val, Sub):
            if not val.blocks:
                return None
            first = self._emit_stack(val.blocks, parent_id, out)
            return [INPUT_BLOCK_NO_SHADOW, first]
        if isinstance(val, Menu):
            bid = self._emit_block(val.block, parent_id, out)
            out[bid]["shadow"] = True
            return [INPUT_SAME_BLOCK_SHADOW, bid]
        if isinstance(val, Plugged):
            mid = self._emit_block(val.menu, parent_id, out)
            out[mid]["shadow"] = True
            bid = self._input(val.value, parent_id, out)
            if isinstance(bid, list) and len(bid) == 2 and isinstance(bid[1], list):
                # literal: keep the plain shadowed-literal encoding
                return bid
            return [INPUT_DIFF_BLOCK_SHADOW, bid[1], mid]
        if isinstance(val, Block):
            bid = self._emit_block(val, parent_id, out)
            return [INPUT_BLOCK_NO_SHADOW, bid]
        if isinstance(val, Lit):
            if val.kind == BROADCAST:
                return [INPUT_SAME_BLOCK_SHADOW, [BROADCAST, val.value[0], val.value[1]]]
            return [INPUT_SAME_BLOCK_SHADOW, [val.kind, val.value]]
        if isinstance(val, Var):
            return [INPUT_BLOCK_NO_SHADOW, [VAR, val.name, val.id]]
        if isinstance(val, ListVar):
            return [INPUT_BLOCK_NO_SHADOW, [LIST, val.name, val.id]]
        if isinstance(val, bool):
            return [INPUT_SAME_BLOCK_SHADOW, [MATH_NUM, fmt_num(val)]]
        if isinstance(val, (int, float)):
            return [INPUT_SAME_BLOCK_SHADOW, [MATH_NUM, fmt_num(val)]]
        if isinstance(val, str):
            return [INPUT_SAME_BLOCK_SHADOW, [TEXT, val]]
        raise TypeError(f"unsupported input value: {val!r}")

    def _emit_block(self, block: Block, parent_id, out: dict) -> str:
        bid = self.new_id()
        entry = {
            "opcode": block.opcode,
            "next": None,
            "parent": parent_id,
            "inputs": {},
            "fields": self._fields(block),
            "shadow": False,
            "topLevel": False,
        }
        if block.mutation is not None:
            entry["mutation"] = block.mutation
        out[bid] = entry
        for key, val in block.inputs.items():
            enc = self._input(val, bid, out)
            if enc is not None:
                entry["inputs"][key] = enc
        return bid

    def _emit_stack(self, blocks, parent_id, out: dict):
        """Emit a vertical stack, wiring ``next`` and ``parent`` both ways."""
        ids = []
        prev = parent_id
        for b in blocks:
            bid = self._emit_block(b, prev, out)
            ids.append(bid)
            prev = bid
        for i, bid in enumerate(ids):
            out[bid]["next"] = ids[i + 1] if i + 1 < len(ids) else None
        return ids[0]

    def to_json(self) -> dict:
        blocks: dict[str, dict] = {}
        comments: dict[str, dict] = {}
        for s in self.scripts:
            if not s.blocks:
                continue
            first = self._emit_stack(s.blocks, None, blocks)
            blocks[first]["topLevel"] = True
            blocks[first]["x"] = int(s.x)
            blocks[first]["y"] = int(s.y)
            if s.comment:
                cid = self.new_id("c")
                comments[cid] = {
                    "blockId": first,
                    "x": int(s.x) + 260,
                    "y": int(s.y),
                    "width": 260,
                    "height": 120,
                    "minimized": False,
                    "text": s.comment,
                }
        obj = {
            "isStage": self.is_stage,
            "name": self.name,
            "variables": self.variables,
            "lists": self.lists,
            "broadcasts": self.broadcasts,
            "blocks": blocks,
            "comments": comments,
            "currentCostume": self.current_costume,
            "costumes": [
                {
                    "name": c.name,
                    "bitmapResolution": c.resolution,
                    "dataFormat": c.ext,
                    "assetId": c.md5,
                    "md5ext": c.md5ext,
                    "rotationCenterX": c.cx,
                    "rotationCenterY": c.cy,
                }
                for c in self.costumes
            ],
            "sounds": [
                {
                    "name": s.name,
                    "assetId": s.md5,
                    "dataFormat": s.data_format,
                    "format": "",
                    "rate": s.rate,
                    "sampleCount": s.sample_count,
                    "md5ext": s.md5ext,
                }
                for s in self.sounds
            ],
            "volume": self.volume,
            "layerOrder": self.layer_order,
        }
        if self.is_stage:
            obj["tempo"] = self.tempo
            obj["videoTransparency"] = self.video_transparency
            obj["videoState"] = self.video_state
            obj["textToSpeechLanguage"] = self.text_to_speech_language
        else:
            obj["visible"] = self.visible
            obj["x"] = self.x
            obj["y"] = self.y
            obj["size"] = self.size
            obj["direction"] = self.direction
            obj["draggable"] = self.draggable
            obj["rotationStyle"] = self.rotation_style
        return obj


class Project:
    def __init__(self, stage: Target, sprites: list[Target] | None = None,
                 vm_version: str = "3.0.300"):
        self.stage = stage
        self.sprites = list(sprites or [])
        self.monitors: list = []
        self.extensions: list = []
        self.vm_version = vm_version
        self.extra: dict = {}

    @property
    def targets(self) -> list[Target]:
        return [self.stage] + self.sprites

    def broadcast_var(self, name: str) -> str:
        """Broadcasts live on the stage so every target can see them."""
        return self.stage.broadcast_var(name)

    def to_json(self) -> dict:
        data = {
            "targets": [t.to_json() for t in self.targets],
            "monitors": self.monitors,
            "extensions": self.extensions,
            "meta": {
                "semver": "3.0.0",
                "vm": self.vm_version,
                "agent": "gd-scratch project generator",
            },
        }
        data.update(self.extra)
        return data

    def assets(self) -> dict[str, bytes]:
        out: dict[str, bytes] = {}
        for t in self.targets:
            for c in t.costumes:
                out[c.md5ext] = c.data
            for s in t.sounds:
                out[s.md5ext] = s.data
        return out

    def project_json_bytes(self) -> bytes:
        return json.dumps(self.to_json(), separators=(",", ":")).encode("utf-8")

    def save_sb3(self, path: str) -> None:
        payload = self.project_json_bytes()
        assets = self.assets()
        with open(path, "wb") as fh:
            with zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("project.json", payload)
                for name in sorted(assets):
                    zf.writestr(name, assets[name])

    def save_project_json(self, path: str) -> None:
        with open(path, "wb") as fh:
            fh.write(self.project_json_bytes())
