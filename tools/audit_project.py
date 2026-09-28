#!/usr/bin/env python3
"""Static audit of a built .sb3: wiring that can never run.

    python3 tools/audit_project.py dist/GD-Scratch.sb3

Reads only ``project.json``, so it is deterministic and instant. It resolves the
shadow-compressed input forms Scratch writes (``[11, name, id]`` for broadcasts,
``[12, name, id]`` for variables, plain block ids for menu shadows) and reports:

* broadcasts declared but never sent  -- a handler that can never fire,
* broadcasts sent with no receiver,
* sounds that no block can ever play,
* per-sprite block counts,
* every ``create clone`` site,
* custom blocks defined but never called, and calls with no definition.

A finding here is a *hypothesis*. It becomes a bug only when the running project
is shown to misbehave; this tool exists to point at what to reproduce.
"""

from __future__ import annotations

import collections
import json
import sys
import zipfile

BROADCAST = 11
VARIABLE = 12


def load(path: str) -> dict:
    with zipfile.ZipFile(path) as z:
        return json.loads(z.read("project.json"))


def inputs_of(block: dict) -> dict:
    return block.get("inputs", {}) or {}


def input_elements(block: dict, name: str):
    inp = inputs_of(block).get(name)
    if not inp:
        return []
    out = []
    for element in inp[1:]:
        if isinstance(element, str):
            out.append(("block", element))
        elif isinstance(element, list) and element:
            out.append(("prim", element))
    return out


def field_of(blocks: dict, block_id: str, field: str):
    block = blocks.get(block_id)
    if not block:
        return None
    value = (block.get("fields") or {}).get(field)
    if not value:
        return None
    return value[0]


def field_id(block: dict, field: str):
    """Return the Scratch-global id in a broadcast menu field, if present."""
    value = (block.get("fields") or {}).get(field)
    if isinstance(value, (list, tuple)) and len(value) > 1:
        return value[1]
    return None


def audit(path: str) -> dict:
    prj = load(path)
    declared = {}
    for target in prj["targets"]:
        for bid, name in (target.get("broadcasts") or {}).items():
            declared[bid] = name
    name_of = {v: k for k, v in declared.items()}

    sent = collections.Counter()
    received = collections.Counter()
    played = collections.Counter()
    played_via_var = set()
    clone_sites = collections.Counter()
    calls = collections.Counter()
    defs = collections.Counter()
    blocks_per_sprite = {}
    forever_loops = collections.Counter()

    for target in prj["targets"]:
        blocks = target["blocks"]
        blocks_per_sprite[target["name"]] = sum(
            1 for b in blocks.values() if isinstance(b, dict))
        for block in blocks.values():
            if not isinstance(block, dict):
                continue
            op = block["opcode"]
            if op in ("event_broadcast", "event_broadcastandwait"):
                for kind, value in input_elements(block, "BROADCAST_INPUT"):
                    if kind == "prim" and value[0] == BROADCAST:
                        sent[value[2]] += 1
                    elif kind == "block":
                        menu = blocks.get(value)
                        if menu:
                            sent[field_id(menu, "BROADCAST_OPTION") or
                                 name_of.get(field_of(blocks, value, "BROADCAST_OPTION"), "?")] += 1
            elif op == "event_whenbroadcastreceived":
                bid = field_id(block, "BROADCAST_OPTION")
                if bid is None:
                    bid = name_of.get((block.get("fields") or {}).get(
                        "BROADCAST_OPTION", [None])[0], "?")
                received[bid] += 1
            elif op in ("sound_play", "sound_playuntildone"):
                for kind, value in input_elements(block, "SOUND_MENU"):
                    if kind == "prim" and value and value[0] == VARIABLE:
                        # the sound name comes from a variable at runtime
                        # (GD-Scratch's `track`); record the variable, since
                        # which assets it plays cannot be proven statically
                        played_via_var.add(value[1])
                        continue
                    if kind != "block":
                        continue
                    menu = blocks.get(value)
                    if not menu:
                        continue
                    name = field_of(blocks, value, "SOUND_MENU")
                    if name is not None:
                        played[name] += 1
                    elif menu.get("opcode") == "data_variable":
                        var_field = (menu.get("fields") or {}).get("VARIABLE")
                        if var_field:
                            played_via_var.add(var_field[0])
            elif op == "control_create_clone_of":
                clone_sites[target["name"]] += 1
            elif op == "control_forever":
                forever_loops[target["name"]] += 1
            elif op == "procedures_call":
                calls[(block.get("mutation") or {}).get("proccode")] += 1
            elif op == "procedures_definition":
                defs[(block.get("mutation") or {}).get("proccode")] += 1

    never_sent = sorted(name for bid, name in declared.items() if sent[bid] == 0)
    no_receiver = sorted(name for bid, name in declared.items()
                         if sent[bid] and received[bid] == 0)

    sounds = {}
    for target in prj["targets"]:
        for sound in target.get("sounds", []):
            sounds[sound["name"]] = f'{target["name"]}/{sound["name"]}'

    # A sound is "never played" only if no literal play and no variable play
    # path exists at all.
    never_played = sorted(key for name, key in sounds.items()
                          if played.get(name, 0) == 0 and not played_via_var)

    return {
        "file": path,
        "blocks": {"total": sum(blocks_per_sprite.values()),
                   "perSprite": dict(sorted(blocks_per_sprite.items()))},
        "broadcasts": {
            "declared": len(declared),
            "neverSent": never_sent,
            "sentButNoReceiver": no_receiver,
            "sendCounts": {name: sent[bid] for bid, name in sorted(declared.items())},
        },
        "sounds": {"total": len(sounds), "neverPlayed": never_played,
                   "playedViaVariable": sorted(played_via_var)},
        "cloneSites": dict(sorted(clone_sites.items())),
        "foreverLoops": dict(sorted(forever_loops.items())),
        "procedures": {"defined": len(defs),
                       "neverCalled": sorted(d for d in defs if calls[d] == 0),
                       "danglingCalls": sorted(c for c in calls if defs[c] == 0)},
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    for path in sys.argv[1:]:
        print(json.dumps(audit(path), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
