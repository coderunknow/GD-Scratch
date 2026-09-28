"""A small, readable DSL over the stock Scratch 3 block set.

Every helper here maps to one core opcode -- no extension blocks are used
anywhere, so the generated project loads in a stock Scratch 3 editor.
"""

from __future__ import annotations

import json

from .sb3 import (
    Block,
    Lit,
    ListVar,
    Menu,
    Script,
    Sub,
    Var,
    angle,
    num,
    txt,
    whole_num,
)

# --------------------------------------------------------------------------
# hats
# --------------------------------------------------------------------------


def when_flag() -> Block:
    return Block("event_whenflagclicked")


def when_key(key: str) -> Block:
    return Block("event_whenkeypressed", fields={"KEY_OPTION": key})


def when_clicked() -> Block:
    return Block("event_whenthisspriteclicked")


def when_broadcast(name: str, broadcast_id: str) -> Block:
    return Block("event_whenbroadcastreceived",
                 fields={"BROADCAST_OPTION": (name, broadcast_id)})


def as_clone() -> Block:
    return Block("control_start_as_clone")


# --------------------------------------------------------------------------
# control
# --------------------------------------------------------------------------


def forever(*body, pace: float | None = None) -> Block:
    """A ``forever`` loop.

    Scratch runs one iteration per frame *provided* something asks for a
    redraw during the frame -- see ``Runtime.redrawRequested`` and the work-time
    loop in ``Sequencer.stepThreads``. A loop whose body is pure variable
    arithmetic therefore spins hundreds of times per frame. GD-Scratch's master
    clock pins itself by moving a transparent sprite by zero pixels each tick
    (see ``game._build_game``); pass ``pace=<seconds>`` here only for a loop
    that genuinely wants to idle, remembering that ``control_wait`` consumes
    one extra frame, so a paced loop runs at half the frame rate.
    """
    blocks = list(body)
    if pace:
        blocks.append(wait(pace))
    return Block("control_forever", inputs={"SUBSTACK": Sub(blocks)})


def repeat(times, *body) -> Block:
    return Block("control_repeat", inputs={"TIMES": times, "SUBSTACK": Sub(body)})


def if_(cond, *body) -> Block:
    return Block("control_if", inputs={"CONDITION": cond, "SUBSTACK": Sub(body)})


def ifelse(cond, then_body, else_body) -> Block:
    return Block("control_if_else", inputs={
        "CONDITION": cond,
        "SUBSTACK": Sub(then_body),
        "SUBSTACK2": Sub(else_body),
    })


def wait(seconds) -> Block:
    return Block("control_wait", inputs={"DURATION": seconds})


def wait_until(cond) -> Block:
    return Block("control_wait_until", inputs={"CONDITION": cond})


def repeat_until(cond, *body) -> Block:
    return Block("control_repeat_until", inputs={"CONDITION": cond, "SUBSTACK": Sub(body)})


def stop(scope: str = "all", has_next: bool = False) -> Block:
    """scope: 'all' | 'this script' | 'other scripts in sprite'."""
    return Block(
        "control_stop",
        mutation={
            "tagName": "mutation",
            "children": [],
            "hasnext": "true" if has_next else "false",
            "value": scope,
        },
    )


def create_clone(target: str = "_myself_") -> Block:
    return Block(
        "control_create_clone_of",
        inputs={"CLONE_OPTION": Menu(Block("control_create_clone_of_menu",
                                           fields={"CLONE_OPTION": target}))},
    )


def delete_clone() -> Block:
    return Block("control_delete_this_clone")


# --------------------------------------------------------------------------
# motion
# --------------------------------------------------------------------------


def goto_xy(x, y) -> Block:
    return Block("motion_gotoxy", inputs={"X": x, "Y": y})


def change_x(dx) -> Block:
    return Block("motion_changexby", inputs={"DX": dx})


def change_y(dy) -> Block:
    return Block("motion_changeyby", inputs={"DY": dy})


def set_x(x) -> Block:
    return Block("motion_setx", inputs={"X": x})


def set_y(y) -> Block:
    return Block("motion_sety", inputs={"Y": y})


def point_direction(direction) -> Block:
    return Block("motion_pointindirection", inputs={"DIRECTION": angle(direction)
                                                    if isinstance(direction, (int, float))
                                                    else direction})


# --------------------------------------------------------------------------
# looks
# --------------------------------------------------------------------------


def show() -> Block:
    return Block("looks_show")


def hide() -> Block:
    return Block("looks_hide")


def switch_costume(name) -> Block:
    return Block(
        "looks_switchcostumeto",
        inputs={"COSTUME": Menu(Block("looks_costume", fields={"COSTUME": name}))},
    )


def next_costume() -> Block:
    return Block("looks_nextcostume")


def set_size(size) -> Block:
    return Block("looks_setsizeto", inputs={"SIZE": size})


def change_size(delta) -> Block:
    return Block("looks_changesizeby", inputs={"CHANGE": delta})


def goto_front() -> Block:
    return Block("looks_gotofrontback", fields={"FRONT_BACK": "front"})


def goto_back() -> Block:
    return Block("looks_gotofrontback", fields={"FRONT_BACK": "back"})


def set_effect(effect: str, value) -> Block:
    return Block("looks_seteffectto", fields={"EFFECT": effect}, inputs={"VALUE": value})


def change_effect(effect: str, value) -> Block:
    return Block("looks_changeeffectby", fields={"EFFECT": effect}, inputs={"CHANGE": value})


def clear_effects() -> Block:
    return Block("looks_cleargraphiceffects")


# --------------------------------------------------------------------------
# sound
# --------------------------------------------------------------------------


def play_sound(name) -> Block:
    return Block("sound_play",
                 inputs={"SOUND_MENU": Menu(Block("sound_menu",
                                                  fields={"SOUND_MENU": name}))})


def play_sound_until_done(name) -> Block:
    return Block("sound_playuntildone",
                 inputs={"SOUND_MENU": Menu(Block("sound_menu",
                                                  fields={"SOUND_MENU": name}))})


def stop_all_sounds() -> Block:
    return Block("sound_stopallsounds")


def set_volume(volume) -> Block:
    return Block("sound_setvolumeto", inputs={"VOLUME": volume})


def change_volume(delta) -> Block:
    return Block("sound_changevolumeby", inputs={"VOLUME": delta})


# --------------------------------------------------------------------------
# events
# --------------------------------------------------------------------------


def broadcast(name: str, broadcast_id: str) -> Block:
    return Block("event_broadcast", inputs={"BROADCAST_INPUT": _bcast_lit(name, broadcast_id)})


def broadcast_and_wait(name: str, broadcast_id: str) -> Block:
    return Block("event_broadcastandwait",
                 inputs={"BROADCAST_INPUT": _bcast_lit(name, broadcast_id)})


def _bcast_lit(name: str, broadcast_id: str) -> Lit:
    from .sb3 import BROADCAST

    return Lit(BROADCAST, (name, broadcast_id))


# --------------------------------------------------------------------------
# sensing
# --------------------------------------------------------------------------


def key_pressed(key: str) -> Block:
    """``key [key] pressed?`` -- reporter plus its menu shadow."""
    return Block("sensing_keypressed",
                 inputs={"KEY_OPTION": Menu(Block("sensing_keyoptions",
                                                 fields={"KEY_OPTION": key}))})


def mouse_down() -> Block:
    return Block("sensing_mousedown")


def mouse_x() -> Block:
    return Block("sensing_mousex")


def mouse_y() -> Block:
    return Block("sensing_mousey")


def touching(target: str) -> Block:
    return Block(
        "sensing_touchingobject",
        inputs={"TOUCHINGOBJECTMENU": Menu(Block("sensing_touchingobjectmenu",
                                                 fields={"TOUCHINGOBJECTMENU": target}))},
    )


def timer() -> Block:
    return Block("sensing_timer")


def reset_timer() -> Block:
    return Block("sensing_resettimer")


def x_position() -> Block:
    return Block("motion_xposition")


def y_position() -> Block:
    return Block("motion_yposition")


def direction() -> Block:
    return Block("motion_direction")


def costume_number() -> Block:
    return Block("looks_costumenumbername", fields={"NUMBER_NAME": "number"})


def size_reporter() -> Block:
    return Block("looks_size")


def answer() -> Block:
    return Block("sensing_answer")


# --------------------------------------------------------------------------
# operators
# --------------------------------------------------------------------------


def add(a, b) -> Block:
    return Block("operator_add", inputs={"NUM1": a, "NUM2": b})


def sub(a, b) -> Block:
    return Block("operator_subtract", inputs={"NUM1": a, "NUM2": b})


def mul(a, b) -> Block:
    return Block("operator_multiply", inputs={"NUM1": a, "NUM2": b})


def div(a, b) -> Block:
    return Block("operator_divide", inputs={"NUM1": a, "NUM2": b})


def rand(a, b) -> Block:
    return Block("operator_random", inputs={"FROM": a, "TO": b})


def gt(a, b) -> Block:
    return Block("operator_gt", inputs={"OPERAND1": a, "OPERAND2": b})


def lt(a, b) -> Block:
    return Block("operator_lt", inputs={"OPERAND1": a, "OPERAND2": b})


def eq(a, b) -> Block:
    return Block("operator_equals", inputs={"OPERAND1": a, "OPERAND2": b})


def and_(a, b) -> Block:
    return Block("operator_and", inputs={"OPERAND1": a, "OPERAND2": b})


def or_(a, b) -> Block:
    return Block("operator_or", inputs={"OPERAND1": a, "OPERAND2": b})


def not_(a) -> Block:
    return Block("operator_not", inputs={"OPERAND": a})


def join(a, b) -> Block:
    return Block("operator_join", inputs={"STRING1": a, "STRING2": b})


def letter_of(index, string) -> Block:
    return Block("operator_letter_of", inputs={"LETTER": index, "STRING": string})


def length_of(string) -> Block:
    return Block("operator_length", inputs={"STRING": string})


def mod(a, b) -> Block:
    return Block("operator_mod", inputs={"NUM1": a, "NUM2": b})


def round_(a) -> Block:
    return Block("operator_round", inputs={"NUM": a})


def mathop(op: str, value) -> Block:
    """op: abs | floor | ceiling | sqrt | sin | cos | tan | ..."""
    return Block("operator_mathop", fields={"OPERATOR": op}, inputs={"NUM": value})


def floor_(a) -> Block:
    return mathop("floor", a)


def ceil_(a) -> Block:
    return mathop("ceiling", a)


def abs_(a) -> Block:
    return mathop("abs", a)


def max_(a, b):
    return ifelse_block(a, b)


def ifelse_block(a, b):
    # Scratch has no max(); use the mathop-free equivalent: (a+b+|a-b|)/2
    return div(add(add(a, b), abs_(sub(a, b))), 2)


def min_(a, b):
    return div(sub(add(a, b), abs_(sub(a, b))), 2)


# --------------------------------------------------------------------------
# data (variables and lists)
# --------------------------------------------------------------------------


def set_var(variable, value) -> Block:
    return Block("data_setvariableto", fields={"VARIABLE": variable},
                 inputs={"VALUE": value})


def change_var(variable, value) -> Block:
    return Block("data_changevariableby", fields={"VARIABLE": variable},
                 inputs={"VALUE": value})


def show_var(variable) -> Block:
    return Block("data_showvariable", fields={"VARIABLE": variable})


def hide_var(variable) -> Block:
    return Block("data_hidevariable", fields={"VARIABLE": variable})


def add_to_list(item, list_ref) -> Block:
    return Block("data_addtolist", fields={"LIST": list_ref}, inputs={"ITEM": item})


def delete_of_list(index, list_ref) -> Block:
    return Block("data_deleteoflist", fields={"LIST": list_ref}, inputs={"INDEX": index})


def insert_at_list(index, item, list_ref) -> Block:
    return Block("data_insertatlist", fields={"LIST": list_ref},
                 inputs={"INDEX": index, "ITEM": item})


def replace_item(index, item, list_ref) -> Block:
    return Block("data_replaceitemoflist", fields={"LIST": list_ref},
                 inputs={"INDEX": index, "ITEM": item})


def item_of(index, list_ref) -> Block:
    return Block("data_itemoflist", fields={"LIST": list_ref}, inputs={"INDEX": index})


def item_num_of(item, list_ref) -> Block:
    return Block("data_itemnumoflist", fields={"LIST": list_ref}, inputs={"ITEM": item})


def length_of_list(list_ref) -> Block:
    return Block("data_lengthoflist", fields={"LIST": list_ref})


def list_contains(item, list_ref) -> Block:
    return Block("data_listcontainsitem", fields={"LIST": list_ref}, inputs={"ITEM": item})


def show_list(list_ref) -> Block:
    return Block("data_showlist", fields={"LIST": list_ref})


def hide_list(list_ref) -> Block:
    return Block("data_hidelist", fields={"LIST": list_ref})


# --------------------------------------------------------------------------
# custom blocks (procedures)
# --------------------------------------------------------------------------


class Proc:
    """A custom block definition living on one sprite.

    ``args`` is a list of ``(name, kind)`` where kind is ``'s'`` (string/number)
    or ``'b'`` (boolean).
    """

    def __init__(self, target, name: str, args=None, warp: bool = True):
        self.target = target
        self.name = name
        self.args = list(args or [])
        self.warp = warp
        self.arg_ids = [target.new_id("a") for _ in self.args]
        placeholders = "".join(
            f" %{a[1]}" for a in self.args
        )
        self.proccode = f"{name}{placeholders}" if self.args else name

    # -- definition --------------------------------------------------------
    def definition_mutation(self) -> dict:
        return {
            "tagName": "mutation",
            "children": [],
            "proccode": self.proccode,
            "argumentids": json.dumps(self.arg_ids),
            "argumentnames": json.dumps([a[0] for a in self.args]),
            "argumentdefaults": json.dumps(["" for _ in self.args]),
            "warp": "true" if self.warp else "false",
        }

    def head(self) -> Block:
        """The definition hat, complete with the ``custom_block`` shadow.

        The nested ``procedures_prototype`` shadow is not decoration. The VM
        resolves a call to its definition by scanning for ``procedures_definition``
        blocks and comparing ``inputs.custom_block.block``'s mutation against the
        requested proccode (``Blocks.getProcedureDefinition``). Without that
        shadow the definition is simply not found, and every call to the custom
        block silently becomes a no-op -- no error, no warning.
        """
        mutation = self.definition_mutation()
        return Block(
            "procedures_definition",
            inputs={"custom_block": Menu(Block("procedures_prototype",
                                               mutation=dict(mutation)))},
            mutation=mutation,
        )

    def define(self, *body, x: int = 0, y: int = 0, comment: str | None = None) -> Script:
        """Attach the custom block definition (and its body) to the sprite."""
        return self.target.script(self.head(), *body, x=x, y=y, comment=comment)

    # -- call --------------------------------------------------------------
    def call(self, *values) -> Block:
        if len(values) != len(self.args):
            raise ValueError(f"{self.name}: expected {len(self.args)} args, got {len(values)}")
        inputs = {}
        for arg_id, value in zip(self.arg_ids, values):
            inputs[arg_id] = value
        mutation = {
            "tagName": "mutation",
            "children": [],
            "proccode": self.proccode,
            "argumentids": json.dumps(self.arg_ids),
            "warp": "true" if self.warp else "false",
        }
        return Block("procedures_call", inputs=inputs, mutation=mutation)

    # -- argument reporters ------------------------------------------------
    def arg(self, index_or_name) -> Block:
        if isinstance(index_or_name, int):
            i = index_or_name
        else:
            i = [a[0] for a in self.args].index(index_or_name)
        name, kind = self.args[i]
        opcode = ("argument_reporter_boolean" if kind == "b"
                  else "argument_reporter_string_number")
        return Block(opcode, fields={"VALUE": name},
                     mutation={"tagName": "mutation", "children": [], "paramname": name})


# --------------------------------------------------------------------------
# convenience combinators
# --------------------------------------------------------------------------
def ge(a, b) -> Block:
    """a >= b (Scratch has no >= block)."""
    return not_(lt(a, b))


def le(a, b) -> Block:
    """a <= b."""
    return not_(gt(a, b))


def allof(*conds) -> Block:
    out = conds[0]
    for c in conds[1:]:
        out = and_(out, c)
    return out


def anyof(*conds) -> Block:
    out = conds[0]
    for c in conds[1:]:
        out = or_(out, c)
    return out


def chain(*blocks) -> list:
    """Flatten nested lists of blocks into a flat body list."""
    out = []
    for b in blocks:
        if b is None:
            continue
        if isinstance(b, list):
            out.extend(chain(*b))
        else:
            out.append(b)
    return out


def switch_costume_var(value, target, default: str) -> Block:
    """``switch costume to (value)`` keeping the dropdown as a shadow."""
    from .sb3 import Block as _B, Plugged as _P

    menu = _B("looks_costume", fields={"COSTUME": default})
    return _B("looks_switchcostumeto", inputs={"COSTUME": _P(value, menu)})


def switch_backdrop_var(value, default: str) -> Block:
    from .sb3 import Block as _B, Plugged as _P

    menu = _B("looks_backdrops", fields={"BACKDROP": default})
    return _B("looks_switchbackdropto", inputs={"BACKDROP": _P(value, menu)})


def switch_backdrop(name: str) -> Block:
    """``switch backdrop to [name]`` with a literal menu (does not wait)."""
    return Block("looks_switchbackdropto",
                 inputs={"BACKDROP": Menu(Block("looks_backdrops",
                                               fields={"BACKDROP": name}))})


def list_delete_all(list_ref) -> Block:
    return Block("data_deleteoflist", fields={"LIST": list_ref},
                 inputs={"INDEX": "all"})


def list_delete_all_ref(list_ref) -> Block:
    return list_delete_all(list_ref)
