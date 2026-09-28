"""Assembly of the whole Scratch project.

Coordinate system
-----------------
Stage is 480x360, origin at the centre, +y up. A level cell ``(col, row)``
covers world x ``[col*CELL, col*CELL+CELL)`` and world y
``[GY + row*CELL, GY + (row+1)*CELL)``. The camera is fixed and the world
scrolls: something at world x ``wx`` is drawn at ``wx - worldX``.

``step play`` below is a line-by-line transcription of ``gdscratch.verify.step``
(one 30 Hz physics step). The master clock no longer runs one physics step per
rendered frame: each frame it computes how many whole 30 Hz ticks elapsed on
the Scratch timer and runs that many steps (capped, excess time dropped), so
the simulation runs at the same speed under Scratch's 30 fps and TurboWarp's
60 fps. ``tests/headless/replay.js`` drives the generated project inside
scratch-vm with a solved input schedule under deterministic 30 fps and 60 fps
clocks and compares every physics step against the Python model, so the two
cannot silently drift apart.

Only stock Scratch 3 blocks are used, so the project loads unchanged in
scratch.mit.edu and in the Scratch 3.32.1 app.
"""

from __future__ import annotations

from . import art
from . import audio
from . import levels
from . import ops as o
from .sb3 import Project, Target

# --- physics constants (single source of truth: levels.py) ------------------
CELL = levels.CELL
HALF = levels.HALF
GY = levels.GY
CEIL_Y = levels.CEIL_Y
ROWS = levels.ROWS
PLAYER_X = levels.PLAYER_X
SPEED = levels.SPEED
CORNER = levels.CORNER_FORGIVE
GRAVITY = levels.GRAVITY
JUMP_V = levels.JUMP_V
PAD_V = levels.PAD_V
ORB_V = levels.ORB_V
MAX_FALL = levels.MAX_FALL
SPIKE_INSET_X = levels.SPIKE_INSET_X
SPIKE_H = levels.SPIKE_H
ROT_PER_FRAME = levels.ROT_PER_FRAME

EPS = 0.000001          # landing tolerance, same as verify.step
PORTAL_TRIGGER = 6.0    # px into a portal column before it fires
PAD_TRIGGER = 14.0      # how close to a pad counts as touching it
OOB = 210.0             # this far out of the world is death

# simulation pacing: at most this many 30 Hz physics steps run per rendered
# frame. 60 fps rendering needs at most 1; 2-3 absorb jitter. Simulation time
# beyond the cap is dropped (never fast-forwarded), so a stalled tab catches
# up by at most SIM_CAP steps and then resumes in real time.
SIM_CAP = 3

# --- presentation layout ----------------------------------------------------
TEXT_SLOTS = 56         # glyph clones; only values that change use them.
                        # v0.2.2: 48 -> 56 so the settings values (which spend
                        # slots 1..25) and the optional FPS overlay (49..54,
                        # clear of the play HUD's 1..46) fit one pool.
ADV = 12.0              # px per glyph at size 100
BAR_LEN = 16            # progress-bar cells
SPAWN_AHEAD = 300.0     # px of level kept materialised past the right edge
DESPAWN_X = -280.0      # tiles retire once this far off the left edge

SETTINGS_LABELS = ["MUSIC", "SOUND EFFECTS", "PARTICLES", "LOW LATENCY",
                   "GRAPHICS", "SHOW FPS", "BACK"]
HELP_LINES = [
    "SPACE OR UP OR CLICK TO JUMP",
    "HOLD IT TO JUMP AGAIN ON LANDING",
    "YELLOW PAD LAUNCHES YOU HIGHER",
    "BLUE RING PRESS WHILE IN MID AIR",
    "PORTALS FLIP YOUR GRAVITY",
    "GRAB EVERY COIN YOU CAN",
    "P PAUSE   R RESTART   Q QUIT TO MENU",
    "CLEAR ALL THREE LEVELS",
]

# y of each selectable row per screen; must match the artwork in art.py
SEL_Y = {
    "menu": [30, -2, -34, -66],
    "select": [64, 18, -28],
    "settings": [84, 54, 24, -6, -36, -66, -96],
    "pause": [20, -14, -48],
    "win": [-36, -70, -104],
}
SEL_COUNT = {"menu": 4, "select": 3, "settings": 7, "pause": 3, "help": 1,
             "win": 3}
SETTINGS_VAL_Y = [84, 54, 24, -6, -36, -66]
DETAIL_NAMES = {0: "HIGH", 1: "LOW", 2: "ULTRA"}
SELECT_ROW_Y = SEL_Y["select"]


class Ctx:
    """Shared handles: the stage, its variables, lists and broadcasts."""

    def __init__(self, prj: Project):
        self.p = prj
        self.stage = prj.stage
        self._v: dict = {}
        self._l: dict = {}
        self._b: dict = {}

    def v(self, name, value=0):
        if name not in self._v:
            self._v[name] = self.stage.var(name, value)
        return self._v[name]

    def l(self, name, values=None):
        if name not in self._l:
            self._l[name] = self.stage.lst(name, values)
        return self._l[name]

    def b(self, name):
        if name not in self._b:
            self._b[name] = self.stage.broadcast_var(name)
        return self._b[name]


# ---------------------------------------------------------------------------
# Scratch has no >= / <= block and no if/else *reporter*, so both are spelled
# out here instead of being faked with boolean arithmetic.
# ---------------------------------------------------------------------------
def le(a, b):
    return o.not_(o.gt(a, b))


def ge(a, b):
    return o.not_(o.lt(a, b))


def either(out, cond, a, b):
    """``set out to (cond ? a : b)`` with a real if/else stack block."""
    return o.ifelse(cond, [o.set_var(out, a)], [o.set_var(out, b)])


# ---------------------------------------------------------------------------
def build_project(turbo: bool = False) -> Project:
    """Build the whole game. ``turbo`` emits the 60fps-tuned variant."""
    prj = Project(Target("Stage", is_stage=True, layer_order=0))
    if turbo:
        # TurboWarp reads runtimeOptions; stock Scratch ignores unknown keys.
        prj.extra["runtimeOptions"] = {"fps": 60, "interpolation": True,
                                       "fencing": True, "miscLimits": True}
    ctx = Ctx(prj)
    _declare(ctx)
    _build_stage(ctx)
    _build_game(ctx)
    _build_player(ctx)
    _build_tile(ctx)
    _build_ground(ctx)
    _build_far(ctx)
    _build_fx(ctx)
    _build_hud(ctx)
    _build_sel(ctx)
    _build_text(ctx)
    _build_sound(ctx)
    return prj


# ---------------------------------------------------------------------------
def _declare(ctx: Ctx):
    V = ctx.v
    V("state", "menu")
    V("level", 1)
    V("gen", 0)
    V("attempt", 0)

    # physics -- names mirror verify.State
    V("frame", 0)
    V("worldX", 0.0)
    V("px", PLAYER_X)
    V("py", GY + HALF)
    V("vy", 0.0)
    V("grounded", 1)
    V("grav", 1.0)
    V("held", 0)
    V("jumpEdge", 0)
    V("died", 0)
    V("won", 0)
    V("prevY", 0.0)
    V("rot", 0.0)

    # fixed-30 Hz simulation pacing. The master tick derives `now30`, the
    # whole number of 30 Hz ticks since the green flag, from the deterministic
    # Scratch timer; `due` physics steps run this rendered frame (capped), and
    # `stepsRun` tells the scenery clones how far to scroll.
    V("now30", 0)
    V("lastTick", 0)
    V("due", 0)
    V("stepsRun", 0)

    # render-rate input capture: `raw` is the jump key/mouse sampled once per
    # rendered frame, `tapLatch` holds presses that happened entirely between
    # two physics steps until a step consumes them.
    V("raw", 0)
    V("rawPrev", 0)
    V("tapLatch", 0)

    # collision scan scratch space
    V("c0", 0)
    V("c1", 0)
    V("r0", 0)
    V("r1", 0)
    V("cc", 0)
    V("rr", 0)
    V("ch", ".")
    V("x0", 0.0)
    V("x1", 0.0)
    V("y0", 0.0)
    V("y1", 0.0)
    V("rowCursor", 0)
    V("rowStride", 0)
    V("pxEdge", 0.0)
    V("colX", 0.0)
    V("portalX", 0.0)
    V("portalOK", 0)
    V("finOK", 0)
    V("launchV", 0.0)
    V("hasLaunch", 0)
    V("portalTo", 0.0)
    V("hasPortal", 0)
    V("usedOrb", 0)

    # level payload, one set of variables per level
    V("LVL", "")
    V("W", 0)
    V("FINX", 0.0)
    V("coinTotal", 0)
    for i, lv in enumerate(levels.LEVELS, 1):
        V(f"DATA{i}", lv.flat)
        V(f"WIDE{i}", lv.width)
        V(f"CTOT{i}", lv.coins())
        V(f"FINX{i}", lv.finish_col() * CELL)

    # progression + settings
    V("coins", 0)
    V("prog", 0)
    V("coinsTotal", 0)
    V("musicOn", 1)
    V("sfxOn", 1)
    V("fxOn", 1)
    # v0.2.2 settings. `lowLatency` keeps the render-cadence tap latch on
    # (CBF-style); off, taps must span a physics step (30 Hz sampling).
    # `detail` scales cosmetics: 0 HIGH, 1 LOW (far parallax hidden, half
    # particles), 2 ULTRA (far parallax hidden, no particles). `showFps`
    # draws a live render-fps readout in play.
    V("lowLatency", 1)
    V("detail", 0)
    V("showFps", 0)
    V("fpsShow", "")
    V("fpsStr", "")
    V("fpsN", 0)
    V("fpsT", 0.0)
    ctx.l("BESTS", [0, 0, 0])
    ctx.l("BCOINS", [0, 0, 0])
    ctx.l("GOT")

    # ui / presentation
    V("sel", 1)
    V("selCount", 4)
    V("screenFrom", "")
    V("track", "music0")
    V("deadT", 0)
    V("winT", 0)
    V("shakeT", 0)
    V("shakeX", 0)
    V("shakeY", 0)
    V("filled", -1)
    V("spawnCol", 0)
    V("spawnHi", 0)
    V("mDown", 0)
    V("mPrev", 0)
    V("kUpPrev", 0)
    V("kDownPrev", 0)
    V("kAct", 0)
    V("kActPrev", 0)
    V("tSlot", 0)
    V("tI", 0)
    V("tX", 0.0)
    V("tLen", 0)
    V("tSize", 100)
    V("barStr", "")
    # per-slot text revision: bumped on every put text/clear text so glyph
    # clones can go idle when nothing they draw has changed
    V("tRev", 0)
    # last strings painted at the fixed HUD slots; put text is skipped while
    # the value has not changed
    V("progStr", "")
    V("attStr", "")
    V("coinStr", "")
    V("fxAtX", 0.0)
    V("fxAtY", 0.0)
    V("fxN", 0)

    ctx.l("TXTCH", [" "] * TEXT_SLOTS)
    ctx.l("TXTX", [0] * TEXT_SLOTS)
    ctx.l("TXTY", [0] * TEXT_SLOTS)
    ctx.l("TXTS", [100] * TEXT_SLOTS)
    ctx.l("TXTREV", [-1] * TEXT_SLOTS)


# ---------------------------------------------------------------------------
def _build_stage(ctx: Ctx):
    st = ctx.stage
    st.add_costume("menu", art.screen_menu(), "png", 240, 180, 1)
    st.add_costume("select",
                   art.screen_select([f"{lv.index}  {lv.name}" for lv in levels.LEVELS]),
                   "png", 240, 180, 1)
    st.add_costume("settings", art.screen_settings(SETTINGS_LABELS), "png", 240, 180, 1)
    st.add_costume("help", art.screen_help(HELP_LINES), "png", 240, 180, 1)
    st.add_costume("pause", art.screen_pause(), "png", 240, 180, 1)
    st.add_costume("win", art.screen_win(), "png", 240, 180, 1)
    for i in (1, 2, 3):
        st.add_costume(f"bg{i}", art.backdrop(art.THEMES[i], i), "png", 240, 180, 1)


# ---------------------------------------------------------------------------
# Game: invisible controller owning the master clock, physics and menus.
# ---------------------------------------------------------------------------
def _build_game(ctx: Ctx):
    g = Target("Game", layer_order=1)
    # Deliberately *shown* with a transparent pixel: the tick below moves this
    # sprite by zero pixels every frame purely so that `setXY` asks the runtime
    # for a redraw. That request is what makes Scratch's sequencer stop early
    # and run each thread exactly once per frame; without it the master loop
    # would spin hundreds of times per frame and every input edge would be
    # consumed before the next frame began.
    g.add_costume("blank", art.blank_pixel(), "png", 1, 1, 2)
    ctx.p.sprites.append(g)
    V = ctx.v

    setup = o.Proc(g, "setup")
    start_level = o.Proc(g, "start level", [("n", "s")])
    load_data = o.Proc(g, "load data", [("n", "s")])
    read_input = o.Proc(g, "read input")
    begin_step_input = o.Proc(g, "begin step input")
    tick = o.Proc(g, "tick")
    step_play = o.Proc(g, "step play")
    scan_portals = o.Proc(g, "scan portals")
    scan_tiles = o.Proc(g, "scan tiles")
    handle_cell = o.Proc(g, "handle cell")
    die = o.Proc(g, "die")
    win_level = o.Proc(g, "win level")
    record_best = o.Proc(g, "record best")
    menu_tick = o.Proc(g, "menu tick")
    move_sel = o.Proc(g, "move selection", [("delta", "s")])
    activate = o.Proc(g, "activate")
    goto_screen = o.Proc(g, "goto screen", [("screen", "s")])
    paint = o.Proc(g, "paint")
    paint_hud = o.Proc(g, "paint hud")
    set_prog = o.Proc(g, "set progress")
    text = o.Proc(g, "put text", [("slot", "s"), ("str", "s"), ("x", "s"),
                              ("y", "s"), ("size", "s")])
    text_r = o.Proc(g, "put text right", [("slot", "s"), ("str", "s"), ("x", "s"),
                                   ("y", "s"), ("size", "s")])
    clear_text = o.Proc(g, "clear text")
    boom = o.Proc(g, "boom", [("x", "s"), ("y", "s"), ("n", "s")])

    # ---------------- setup ----------------
    setup.define(
        o.hide(),
        o.switch_backdrop("menu"),
        o.set_var(V("attempt"), 0),
        o.set_var(V("gen"), 0),
        o.set_var(V("musicOn"), 1),
        o.set_var(V("sfxOn"), 1),
        o.set_var(V("fxOn"), 1),
        o.set_var(V("lowLatency"), 1),
        o.set_var(V("detail"), 0),
        o.set_var(V("showFps"), 0),
        o.set_var(V("fpsShow"), ""),
        o.set_var(V("fpsStr"), ""),
        o.set_var(V("fpsN"), 0),
        o.set_var(V("fpsT"), 0.0),
        o.set_var(V("coinsTotal"), 0),
        # the simulation clock and the input latch start clean on every flag
        o.set_var(V("lastTick"), 0),
        o.set_var(V("due"), 0),
        o.set_var(V("stepsRun"), 0),
        o.set_var(V("raw"), 0),
        o.set_var(V("rawPrev"), 0),
        o.set_var(V("tapLatch"), 0),
        o.list_delete_all(ctx.l("GOT")),
        o.replace_item(1, 0, ctx.l("BESTS")),
        o.replace_item(2, 0, ctx.l("BESTS")),
        o.replace_item(3, 0, ctx.l("BESTS")),
        o.replace_item(1, 0, ctx.l("BCOINS")),
        o.replace_item(2, 0, ctx.l("BCOINS")),
        o.replace_item(3, 0, ctx.l("BCOINS")),
        o.broadcast("music", ctx.b("music")),
        goto_screen.call("menu"),
        comment="Runs once when the green flag is clicked.",
    )

    # ---------------- level loading ----------------
    n = start_level.arg(0)
    start_level.define(
        o.change_var(V("gen"), 1),
        o.set_var(V("level"), n),
        o.change_var(V("attempt"), 1),
        load_data.call(n),
        o.list_delete_all(ctx.l("GOT")),
        # verify.initial_state()
        o.set_var(V("frame"), 0),
        o.set_var(V("worldX"), 0.0),
        o.set_var(V("px"), PLAYER_X),
        o.set_var(V("py"), GY + HALF),
        o.set_var(V("vy"), 0.0),
        o.set_var(V("grounded"), 1),
        o.set_var(V("grav"), 1.0),
        o.set_var(V("held"), 0),
        o.set_var(V("jumpEdge"), 0),
        # no press made before/while opening the level may leak into play: a
        # tap latched for the menus must not jump the cube on step one
        o.set_var(V("raw"), 0),
        o.set_var(V("rawPrev"), 0),
        o.set_var(V("tapLatch"), 0),
        o.set_var(V("died"), 0),
        o.set_var(V("won"), 0),
        o.set_var(V("coins"), 0),
        o.set_var(V("prog"), 0),
        o.set_var(V("rot"), 0.0),
        o.set_var(V("hasLaunch"), 0),
        o.set_var(V("hasPortal"), 0),
        o.set_var(V("usedOrb"), 0),
        o.set_var(V("shakeT"), 0),
        o.set_var(V("filled"), -1),
        # force the optional FPS readout to repaint even if its string is
        # unchanged (the settings screen shares its text slot)
        o.set_var(V("fpsStr"), ""),
        o.set_var(V("spawnCol"), 0),
        o.set_var(V("state"), "play"),
        o.set_var(V("track"), o.join("music", n)),
        o.switch_backdrop_var(o.join("bg", n), "bg1"),
        o.broadcast("level start", ctx.b("level start")),
        o.broadcast("music", ctx.b("music")),
        o.broadcast("sfx select", ctx.b("sfx select")),
        paint.call(),
        comment="Load level n and reset the physics to verify.initial_state().",
    )

    # Scratch has no if/else reporter, so the per-level payload is picked with
    # three guarded writes instead of one expression.
    ln = load_data.arg(0)
    load_data.define(
        o.if_(o.eq(ln, 1),
              o.set_var(V("LVL"), V("DATA1")),
              o.set_var(V("W"), V("WIDE1")),
              o.set_var(V("coinTotal"), V("CTOT1")),
              o.set_var(V("FINX"), V("FINX1"))),
        o.if_(o.eq(ln, 2),
              o.set_var(V("LVL"), V("DATA2")),
              o.set_var(V("W"), V("WIDE2")),
              o.set_var(V("coinTotal"), V("CTOT2")),
              o.set_var(V("FINX"), V("FINX2"))),
        o.if_(o.eq(ln, 3),
              o.set_var(V("LVL"), V("DATA3")),
              o.set_var(V("W"), V("WIDE3")),
              o.set_var(V("coinTotal"), V("CTOT3")),
              o.set_var(V("FINX"), V("FINX3"))),
    )

    # ---------------- input ----------------
    # Render-rate capture only. The jump input is *sampled* here, once per
    # rendered frame; presses that begin and end between two physics steps are
    # latched in `tapLatch` so no transient tap can be lost at high render
    # rates. Gameplay semantics are applied per physics step by
    # `begin step input`, which each due step calls exactly once.
    read_input.define(
        either(V("raw"),
               o.anyof(o.anyof(o.key_pressed("space"), o.key_pressed("up arrow")),
                       o.mouse_down()),
               1, 0),
        o.if_(o.allof(o.eq(V("raw"), 1), o.eq(V("rawPrev"), 0)),
              o.set_var(V("tapLatch"), 1)),
        # LOW LATENCY off = classic 30 Hz sampling: taps must span a physics
        # step to count (saves nothing measurable; it is a preference).
        o.if_(o.eq(V("lowLatency"), 0),
              o.set_var(V("tapLatch"), 0)),
        o.set_var(V("rawPrev"), V("raw")),
    )

    # Per-physics-step input consumption: the step sees the key as held if it
    # is down now *or* a tap was latched since the previous step; the edge
    # (needed by orbs) is exactly the latch. Consuming clears it, so a single
    # tap can never drive two steps.
    begin_step_input.define(
        either(V("held"), o.gt(o.add(V("raw"), V("tapLatch")), 0), 1, 0),
        either(V("jumpEdge"), o.eq(V("tapLatch"), 1), 1, 0),
        o.set_var(V("tapLatch"), 0),
    )

    # ---------------- master tick ----------------
    in_menu = o.anyof(o.anyof(o.eq(V("st"), "menu"),
                              o.eq(V("st"), "select")),
                      o.anyof(o.eq(V("st"), "settings"),
                              o.anyof(o.eq(V("st"), "help"),
                                      o.eq(V("st"), "pause"))))
    tick.define(
        # Snapshot the screen once, at the top. `step play` can kill the player
        # or finish the level, and the branches below would then see the *new*
        # screen in the very same tick -- a death would immediately start
        # counting down deadT, a win would immediately lose a frame of its
        # input lock. Every state test in this procedure reads the snapshot.
        o.set_var(V("st"), V("state")),
        either(V("mDown"), o.mouse_down(), 1, 0),
        either(V("kAct"), o.anyof(o.key_pressed("space"), o.key_pressed("enter")),
               1, 0),
        read_input.call(),

        # ---- fixed 30 Hz simulation pacing ----
        # now30 = whole 30 Hz ticks since the green flag, from the Scratch
        # timer (floor of timer*30; the timer is a deterministic test clock in
        # the headless rig and the real runtime clock in a player). `due` is
        # how many of those ticks have not been simulated yet. The clock keeps
        # running in menus and during pauses, so no debt piles up while the
        # simulation is not stepping. Anything more than SIM_CAP ticks behind
        # is dropped, never fast-forwarded.
        o.set_var(V("now30"), o.floor_(o.mul(o.timer(), 30))),
        o.set_var(V("due"), o.sub(V("now30"), V("lastTick"))),
        o.set_var(V("lastTick"), V("now30")),
        # render-fps meter (SHOW FPS): counted over ~0.5 s windows of real
        # rendered frames; this is the host's render cadence, not sim speed
        o.change_var(V("fpsN"), 1),
        o.if_(o.gt(o.sub(o.timer(), V("fpsT")), 0.5),
              o.set_var(V("fpsShow"),
                        o.join("FPS ", o.round_(
                            o.div(V("fpsN"), o.sub(o.timer(), V("fpsT")))))),
              o.set_var(V("fpsT"), o.timer()),
              o.set_var(V("fpsN"), 0)),
        o.if_(o.gt(V("due"), SIM_CAP), o.set_var(V("due"), SIM_CAP)),
        o.set_var(V("stepsRun"), 0),
        # due is already capped at SIM_CAP, so this loop is bounded
        o.repeat(V("due"),
                 o.change_var(V("stepsRun"), 1),
                 # fresh snapshot per step: a step that dies or wins must not
                 # let the *next* due step run against a stale screen
                 o.set_var(V("st"), V("state")),
                 o.if_(o.eq(V("st"), "play"),
                       begin_step_input.call(),
                       step_play.call()),
                 o.if_(o.eq(V("st"), "dead"),
                       o.change_var(V("deadT"), -1),
                       o.if_(o.lt(V("deadT"), 1), start_level.call(V("level")))),
                 o.if_(o.eq(V("st"), "win"), o.change_var(V("winT"), -1)),
                 # screen shake is a timed effect: it decays in physics steps
                 # so it lasts the same wall time at any render rate
                 o.if_(o.gt(V("shakeT"), 0),
                       o.set_var(V("shakeX"), o.rand(-4, 4)),
                       o.set_var(V("shakeY"), o.rand(-3, 3)),
                       o.change_var(V("shakeT"), -1))),

        # the win screen ignores input for winT steps so the player cannot
        # instantly skip past it
        o.if_(o.anyof(in_menu,
                      o.allof(o.eq(V("st"), "win"), o.lt(V("winT"), 1))),
              menu_tick.call()),
        # clear the shake offsets only once the shake is over; on rendered
        # frames that run no physics step the last offsets must persist
        o.if_(o.lt(V("shakeT"), 1),
              o.set_var(V("shakeX"), 0),
              o.set_var(V("shakeY"), 0)),
        o.set_var(V("mPrev"), V("mDown")),
        either(V("kUpPrev"), o.key_pressed("up arrow"), 1, 0),
        either(V("kDownPrev"), o.key_pressed("down arrow"), 1, 0),
        either(V("kActPrev"), o.anyof(o.key_pressed("space"),
                                      o.key_pressed("enter")), 1, 0),
        # Ask for a redraw so this loop stays at exactly one iteration per
        # frame -- see the note on _build_game.
        o.set_x(o.x_position()),
    )

    # ---------------- one physics frame ----------------
    step_play.define(
        o.change_var(V("frame"), 1),
        o.change_var(V("worldX"), SPEED),
        o.set_var(V("px"), o.add(V("worldX"), PLAYER_X)),

        # 1. jump, but only while resting on something
        o.if_(o.allof(o.eq(V("grounded"), 1), o.eq(V("held"), 1)),
              o.set_var(V("vy"), o.mul(JUMP_V, V("grav"))),
              o.set_var(V("grounded"), 0),
              o.broadcast("sfx jump", ctx.b("sfx jump"))),
        # 2. gravity
        o.set_var(V("vy"), o.sub(V("vy"), o.mul(GRAVITY, V("grav")))),
        # 3. terminal speed, kept under CELL so nothing can tunnel
        o.if_(o.lt(V("vy"), -MAX_FALL), o.set_var(V("vy"), -MAX_FALL)),
        o.if_(o.gt(V("vy"), MAX_FALL), o.set_var(V("vy"), MAX_FALL)),
        # 4. integrate
        o.set_var(V("prevY"), V("py")),
        o.set_var(V("py"), o.add(V("py"), V("vy"))),
        # 5. floor / ceiling
        o.if_(o.allof(o.eq(V("grav"), 1), le(o.sub(V("py"), HALF), GY)),
              o.set_var(V("py"), GY + HALF),
              o.set_var(V("vy"), 0.0),
              o.set_var(V("grounded"), 1)),
        o.if_(o.allof(o.eq(V("grav"), -1), ge(o.add(V("py"), HALF), CEIL_Y)),
              o.set_var(V("py"), CEIL_Y - HALF),
              o.set_var(V("vy"), 0.0),
              o.set_var(V("grounded"), 1)),

        # rotation is presentation only, so it sits outside the verified part
        o.ifelse(o.eq(V("grounded"), 1),
                 [either(V("rot"), o.eq(V("grav"), 1), 0.0, 180.0)],
                 [o.set_var(V("rot"),
                            o.mod(o.add(V("rot"), o.mul(ROT_PER_FRAME, V("grav"))),
                                  360))]),

        # 6a. portals are full-height gates: any row of the column counts
        o.set_var(V("hasPortal"), 0),
        o.set_var(V("portalTo"), 0.0),
        o.set_var(V("usedOrb"), 0),
        o.set_var(V("c0"), o.floor_(o.div(o.sub(V("px"), HALF), CELL))),
        o.set_var(V("c1"), o.floor_(o.div(o.add(V("px"), HALF), CELL))),
        scan_portals.call(),
        # 6b. tiles
        o.set_var(V("hasLaunch"), 0),
        o.set_var(V("launchV"), 0.0),
        o.set_var(V("r0"), o.floor_(o.div(o.sub(o.sub(V("py"), HALF), GY), CELL))),
        o.set_var(V("r1"), o.floor_(o.div(o.sub(o.add(V("py"), HALF), GY), CELL))),
        scan_tiles.call(),
        # 7. deferred launch / portal
        o.if_(o.eq(V("hasLaunch"), 1),
              o.set_var(V("vy"), V("launchV")),
              o.set_var(V("grounded"), 0)),
        o.if_(o.allof(o.eq(V("hasPortal"), 1),
                      o.not_(o.eq(V("portalTo"), V("grav")))),
              o.set_var(V("grav"), V("portalTo")),
              o.set_var(V("grounded"), 0),
              o.set_var(V("shakeT"), 6),
              o.broadcast("sfx portal", ctx.b("sfx portal"))),
        # 8. fell out of the world
        o.if_(o.anyof(o.lt(V("py"), -OOB), o.gt(V("py"), OOB)),
              o.set_var(V("died"), 1)),
        # 9. resolve
        o.if_(o.eq(V("died"), 1), die.call()),
        o.if_(o.allof(o.eq(V("died"), 0), o.eq(V("won"), 1)), win_level.call()),
        # 10. hud, if we are still running
        o.if_(o.eq(V("state"), "play"), paint_hud.call()),
        comment="Literal transcription of verify.step(); do not reorder.",
    )

    # Portals are full-height gates and the finish line is a full-height
    # column: their trigger conditions do not depend on the row, so those
    # comparisons are hoisted per column. The LVL string is row-major, so the
    # per-row letter index just advances by W+1 instead of being recomputed.
    # The visit order (columns left to right, rows top to bottom) and every
    # condition are exactly verify.step's.
    scan_portals.define(
        o.set_var(V("rowStride"), o.add(V("W"), 1)),
        o.set_var(V("pxEdge"), o.add(V("px"), HALF)),
        o.set_var(V("cc"), V("c0")),
        o.repeat(o.add(o.sub(V("c1"), V("c0")), 1),
                 o.set_var(V("colX"), o.mul(V("cc"), CELL)),
                 o.set_var(V("portalX"), o.add(V("colX"), PORTAL_TRIGGER)),
                 either(V("portalOK"), o.gt(V("pxEdge"), V("portalX")), 1, 0),
                 either(V("finOK"), ge(V("px"), V("colX")), 1, 0),
                 o.set_var(V("rowCursor"), o.add(V("cc"), 1)),
                 o.set_var(V("rr"), 0),
                 o.repeat(ROWS,
                          o.set_var(V("ch"), o.letter_of(V("rowCursor"), V("LVL"))),
                          o.if_(o.allof(o.anyof(o.eq(V("ch"), "G"),
                                                o.eq(V("ch"), "N")),
                                        o.eq(V("portalOK"), 1)),
                                o.set_var(V("hasPortal"), 1),
                                either(V("portalTo"), o.eq(V("ch"), "G"), -1.0, 1.0)),
                          o.if_(o.allof(o.eq(V("ch"), "F"), o.eq(V("finOK"), 1)),
                                o.set_var(V("won"), 1)),
                          o.change_var(V("rowCursor"), V("rowStride")),
                          o.change_var(V("rr"), 1)),
                 o.change_var(V("cc"), 1)),
    )

    # Tiles: same visit order and conditions as verify.step. x0/x1 depend only
    # on the column, the letter index advances by W+1 per row, and y0/y1
    # advance by one cell height per row, so nothing is recomputed per cell.
    scan_tiles.define(
        o.set_var(V("rowStride"), o.add(V("W"), 1)),
        o.set_var(V("cc"), V("c0")),
        o.repeat(o.add(o.sub(V("c1"), V("c0")), 1),
                 o.set_var(V("x0"), o.mul(V("cc"), CELL)),
                 o.set_var(V("x1"), o.add(V("x0"), CELL)),
                 o.set_var(V("rowCursor"),
                           o.add(o.add(o.mul(V("rowStride"), V("r0")),
                                       V("cc")), 1)),
                 o.set_var(V("y0"), o.add(GY, o.mul(V("r0"), CELL))),
                 o.set_var(V("rr"), V("r0")),
                 o.repeat(o.add(o.sub(V("r1"), V("r0")), 1),
                          o.set_var(V("ch"), o.letter_of(V("rowCursor"), V("LVL"))),
                          o.set_var(V("y1"), o.add(V("y0"), CELL)),
                          handle_cell.call(),
                          o.change_var(V("rowCursor"), V("rowStride")),
                          o.change_var(V("y0"), CELL),
                          o.change_var(V("rr"), 1)),
                 o.change_var(V("cc"), 1)),
    )

    yover = o.allof(o.lt(o.sub(V("py"), HALF), V("y1")),
                    o.lt(V("y0"), o.add(V("py"), HALF)))
    handle_cell.define(
        # ---- solid block: land on the near face, die on any other hit.
        # Corner forgiveness (v0.2.2, owner-directed): a fall may start up to
        # CORNER px past the surface and still snap on top.
        o.if_(o.eq(V("ch"), "#"),
              o.if_(yover,
                    o.ifelse(o.eq(V("grav"), 1),
                             [o.ifelse(o.allof(
                                 ge(o.sub(V("prevY"), HALF), o.sub(V("y1"), CORNER)),
                                 le(V("vy"), 0)),
                                 [o.set_var(V("py"), o.add(V("y1"), HALF)),
                                  o.set_var(V("vy"), 0.0),
                                  o.set_var(V("grounded"), 1)],
                                 [o.set_var(V("died"), 1)])],
                             [o.ifelse(o.allof(
                                 le(o.add(V("prevY"), HALF), o.add(V("y0"), CORNER)),
                                 ge(V("vy"), 0)),
                                 [o.set_var(V("py"), o.sub(V("y0"), HALF)),
                                  o.set_var(V("vy"), 0.0),
                                  o.set_var(V("grounded"), 1)],
                                 [o.set_var(V("died"), 1)])]))),
        # ---- spikes (hitbox narrower than the art, like real GD)
        o.if_(o.eq(V("ch"), "^"),
              o.if_(o.allof(
                  o.lt(o.sub(V("py"), HALF), o.add(V("y0"), SPIKE_H)),
                  o.lt(V("y0"), o.add(V("py"), HALF)),
                  o.lt(o.add(V("x0"), SPIKE_INSET_X), o.add(V("px"), HALF)),
                  o.lt(o.sub(V("px"), HALF), o.sub(V("x1"), SPIKE_INSET_X))),
                  o.set_var(V("died"), 1))),
        o.if_(o.eq(V("ch"), "v"),
              o.if_(o.allof(
                  o.lt(o.sub(V("py"), HALF), V("y1")),
                  o.lt(o.sub(V("y1"), SPIKE_H), o.add(V("py"), HALF)),
                  o.lt(o.add(V("x0"), SPIKE_INSET_X), o.add(V("px"), HALF)),
                  o.lt(o.sub(V("px"), HALF), o.sub(V("x1"), SPIKE_INSET_X))),
                  o.set_var(V("died"), 1))),
        # ---- yellow pad
        o.if_(o.eq(V("ch"), "P"),
              o.if_(o.allof(
                  o.lt(o.sub(V("py"), HALF), o.add(V("y0"), PAD_TRIGGER)),
                  o.lt(V("y0"), o.add(V("py"), HALF)),
                  le(o.mul(V("vy"), V("grav")), 0)),
                  o.set_var(V("launchV"), o.mul(PAD_V, V("grav"))),
                  o.set_var(V("hasLaunch"), 1),
                  o.broadcast("sfx pad", ctx.b("sfx pad")))),
        # ---- blue ring: needs a fresh press, at most one per frame
        o.if_(o.eq(V("ch"), "O"),
              o.if_(o.allof(o.eq(V("jumpEdge"), 1), o.eq(V("usedOrb"), 0), yover),
                    o.set_var(V("usedOrb"), 1),
                    o.set_var(V("launchV"), o.mul(ORB_V, V("grav"))),
                    o.set_var(V("hasLaunch"), 1),
                    o.broadcast("sfx orb", ctx.b("sfx orb")),
                    boom.call(o.add(o.add(V("x0"), HALF), o.mul(-1, V("worldX"))),
                              o.add(V("y0"), HALF), 6))),
        # ---- coin
        o.if_(o.eq(V("ch"), "C"),
              o.if_(o.allof(yover,
                            o.not_(o.list_contains(_cell_key(ctx), ctx.l("GOT")))),
                    o.add_to_list(_cell_key(ctx), ctx.l("GOT")),
                    o.change_var(V("coins"), 1),
                    o.broadcast("sfx coin", ctx.b("sfx coin")),
                    boom.call(o.add(o.add(V("x0"), HALF), o.mul(-1, V("worldX"))),
                              o.add(V("y0"), HALF), 5))),
    )

    # ---------------- death / victory ----------------
    die.define(
        o.set_var(V("state"), "dead"),
        o.set_var(V("deadT"), 42),
        o.set_var(V("shakeT"), 16),
        set_prog.call(),
        record_best.call(),
        o.broadcast("sfx die", ctx.b("sfx die")),
        boom.call(o.sub(V("px"), V("worldX")), V("py"), 22),
    )

    win_level.define(
        o.set_var(V("state"), "win"),
        o.set_var(V("prog"), 100),
        o.set_var(V("winT"), 26),
        o.set_var(V("sel"), 1),
        o.set_var(V("selCount"), 3),
        o.set_var(V("track"), "music0"),
        record_best.call(),
        o.switch_backdrop("win"),
        o.broadcast("sfx win", ctx.b("sfx win")),
        paint.call(),
    )

    record_best.define(
        o.if_(o.gt(V("prog"), o.item_of(V("level"), ctx.l("BESTS"))),
              o.replace_item(V("level"), V("prog"), ctx.l("BESTS"))),
        o.if_(o.gt(V("coins"), o.item_of(V("level"), ctx.l("BCOINS"))),
              o.replace_item(V("level"), V("coins"), ctx.l("BCOINS"))),
        o.set_var(V("coinsTotal"),
                  o.add(o.item_of(1, ctx.l("BCOINS")),
                        o.add(o.item_of(2, ctx.l("BCOINS")),
                              o.item_of(3, ctx.l("BCOINS"))))),
    )

    # ---------------- menus ----------------
    menu_tick.define(
        # activate on a fresh click or a fresh space/enter press
        o.if_(o.allof(o.eq(V("mDown"), 1), o.eq(V("mPrev"), 0)), activate.call()),
        o.if_(o.allof(o.eq(V("kAct"), 1), o.eq(V("kActPrev"), 0)), activate.call()),
        o.if_(o.allof(o.key_pressed("up arrow"), o.eq(V("kUpPrev"), 0)),
              move_sel.call(-1)),
        o.if_(o.allof(o.key_pressed("down arrow"), o.eq(V("kDownPrev"), 0)),
              move_sel.call(1)),
    )

    move_sel.define(
        o.set_var(V("sel"), o.add(V("sel"), move_sel.arg(0))),
        o.if_(o.gt(V("sel"), V("selCount")), o.set_var(V("sel"), 1)),
        o.if_(o.lt(V("sel"), 1), o.set_var(V("sel"), V("selCount"))),
        o.broadcast("sfx click", ctx.b("sfx click")),
    )

    activate.define(
        o.set_var(V("mPrev"), 1),
        # Snapshot: `goto screen` rewrites `state`, and the chain below is a
        # run of plain ifs. Reading `state` live made opening LEVEL SELECT fall
        # straight through into the `state = "select"` branch and start level 1
        # in the same frame.
        o.set_var(V("actSt"), V("state")),
        o.broadcast("sfx select", ctx.b("sfx select")),
        o.if_(o.eq(V("actSt"), "menu"),
              o.if_(o.eq(V("sel"), 1), start_level.call(1)),
              o.if_(o.eq(V("sel"), 2), goto_screen.call("select")),
              o.if_(o.eq(V("sel"), 3), goto_screen.call("help")),
              o.if_(o.eq(V("sel"), 4), goto_screen.call("settings"))),
        o.if_(o.eq(V("actSt"), "select"), start_level.call(V("sel"))),
        o.if_(o.eq(V("actSt"), "help"), goto_screen.call("menu")),
        o.if_(o.eq(V("actSt"), "settings"),
              o.if_(o.eq(V("sel"), 1),
                    o.set_var(V("musicOn"), o.sub(1, V("musicOn"))),
                    o.broadcast("music", ctx.b("music"))),
              o.if_(o.eq(V("sel"), 2), o.set_var(V("sfxOn"), o.sub(1, V("sfxOn")))),
              o.if_(o.eq(V("sel"), 3), o.set_var(V("fxOn"), o.sub(1, V("fxOn")))),
              o.if_(o.eq(V("sel"), 4),
                    o.set_var(V("lowLatency"), o.sub(1, V("lowLatency")))),
              o.if_(o.eq(V("sel"), 5),
                    o.ifelse(o.eq(V("detail"), 2),
                             [o.set_var(V("detail"), 0)],
                             [o.change_var(V("detail"), 1)])),
              o.if_(o.eq(V("sel"), 6),
                    o.set_var(V("showFps"), o.sub(1, V("showFps")))),
              o.if_(o.eq(V("sel"), 7), goto_screen.call("menu")),
              paint.call()),
        o.if_(o.eq(V("actSt"), "pause"),
              o.if_(o.eq(V("sel"), 1),
                    o.set_var(V("state"), "play"),
                    o.set_var(V("tapLatch"), 0),
                    o.set_var(V("track"), o.join("music", V("level"))),
                    o.switch_backdrop_var(o.join("bg", V("level")), "bg1")),
              o.if_(o.eq(V("sel"), 2), start_level.call(V("level"))),
              o.if_(o.eq(V("sel"), 3), goto_screen.call("menu"))),
        o.if_(o.eq(V("actSt"), "win"),
              o.if_(o.eq(V("sel"), 1),
                    o.ifelse(o.lt(V("level"), 3),
                             [start_level.call(o.add(V("level"), 1))],
                             [goto_screen.call("menu")])),
              o.if_(o.eq(V("sel"), 2), start_level.call(V("level"))),
              o.if_(o.eq(V("sel"), 3), goto_screen.call("menu"))),
    )

    gs = goto_screen.arg(0)
    goto_screen.define(
        # Invalidate world/environment clones when backing out of a run. The
        # clone loops retire objects by comparing their creation generation.
        # Without this, Q from pause/win/death leaves level scenery animating
        # behind the menu until the next level happens to start.
        o.set_var(V("screenFrom"), V("state")),
        o.if_(o.anyof(o.eq(V("screenFrom"), "play"),
                      o.anyof(o.eq(V("screenFrom"), "dead"),
                              o.anyof(o.eq(V("screenFrom"), "pause"),
                                      o.eq(V("screenFrom"), "win")))),
              o.change_var(V("gen"), 1)),
        o.set_var(V("state"), gs),
        o.set_var(V("sel"), 1),
        o.set_var(V("track"), "music0"),
        o.switch_backdrop_var(gs, "menu"),
        paint.call(),
        *_sel_count(ctx, gs),
    )

    # ---------------- painting ----------------
    paint.define(
        clear_text.call(),
        o.if_(o.eq(V("state"), "play"), paint_hud.call()),
        o.if_(o.eq(V("state"), "menu"),
              text.call(1, o.join(o.join("BEST ", o.item_of(1, ctx.l("BESTS"))),
                                  o.join("%   COINS ", V("coinsTotal"))),
                        -110, -130, 100)),
        o.if_(o.eq(V("state"), "select"), *_paint_select(ctx, text_r)),
        o.if_(o.eq(V("state"), "settings"), *_paint_settings(ctx, text_r)),
        o.if_(o.eq(V("state"), "win"), *_paint_win(ctx, text)),
    )

    paint_hud.define(
        set_prog.call(),
        # the bar only needs rebuilding when a whole cell flips over
        o.set_var(V("tI"), o.floor_(o.div(o.mul(V("prog"), BAR_LEN), 100))),
        o.if_(o.not_(o.eq(V("tI"), V("filled"))),
              o.set_var(V("filled"), V("tI")),
              o.set_var(V("barStr"), ""),
              o.set_var(V("tSlot"), 1),
              o.repeat(BAR_LEN,
                       o.ifelse(o.le(V("tSlot"), V("filled")),
                                [o.set_var(V("barStr"), o.join(V("barStr"), "{"))],
                                [o.set_var(V("barStr"), o.join(V("barStr"), "}"))]),
                       o.change_var(V("tSlot"), 1)),
              text.call(1, V("barStr"), -96, 140, 100)),
        # the other three values rarely change from one frame to the next:
        # skip the put text (and the glyph refresh it triggers) until the
        # string actually differs from what is on screen
        o.if_(o.not_(o.eq(o.join(V("prog"), "%"), V("progStr"))),
              o.set_var(V("progStr"), o.join(V("prog"), "%")),
              text_r.call(1 + BAR_LEN, V("progStr"), 232, 140, 110)),
        o.if_(o.not_(o.eq(o.join("ATTEMPT ", V("attempt")), V("attStr"))),
              o.set_var(V("attStr"), o.join("ATTEMPT ", V("attempt"))),
              text_r.call(8 + BAR_LEN, V("attStr"), 232, 166, 100)),
        o.if_(o.not_(o.eq(o.join(o.join("COINS ", V("coins")),
                                 o.join("/", V("coinTotal"))), V("coinStr"))),
              o.set_var(V("coinStr"), o.join(o.join("COINS ", V("coins")),
                                             o.join("/", V("coinTotal")))),
              text.call(22 + BAR_LEN, V("coinStr"), -232, -164, 100)),
        # optional render-fps readout (SHOW FPS setting), top right
        o.if_(o.allof(o.eq(V("showFps"), 1), o.gt(o.length_of(V("fpsShow")), 0),
                      o.not_(o.eq(V("fpsShow"), V("fpsStr")))),
              o.set_var(V("fpsStr"), V("fpsShow")),
              text_r.call(49, V("fpsStr"), 232, 190, 100)),
    )

    set_prog.define(
        o.set_var(V("prog"),
                  o.mathop("floor",
                           o.mul(100, o.div(o.sub(V("px"), PLAYER_X),
                                            o.sub(V("FINX"), PLAYER_X))))),
        o.if_(o.lt(V("prog"), 0), o.set_var(V("prog"), 0)),
        o.if_(o.gt(V("prog"), 100), o.set_var(V("prog"), 100)),
    )

    # ---------------- text helpers ----------------
    # Each put text bumps the global text revision and stamps it into every
    # slot it touches. Glyph clones watch their slot's revision and only do
    # work when the slot they draw has actually been rewritten, which lets the
    # 48-clone pool go idle while the screen is static.
    text.define(
        o.set_var(V("tSlot"), text.arg(0)),
        o.set_var(V("tX"), text.arg(2)),
        o.set_var(V("tSize"), text.arg(4)),
        o.set_var(V("tLen"), o.length_of(text.arg(1))),
        o.change_var(V("tRev"), 1),
        o.set_var(V("tI"), 1),
        o.repeat(V("tLen"),
                 o.replace_item(V("tSlot"), o.letter_of(V("tI"), text.arg(1)),
                                ctx.l("TXTCH")),
                 o.replace_item(V("tSlot"), V("tX"), ctx.l("TXTX")),
                 o.replace_item(V("tSlot"), text.arg(3), ctx.l("TXTY")),
                 o.replace_item(V("tSlot"), V("tSize"), ctx.l("TXTS")),
                 o.replace_item(V("tSlot"), V("tRev"), ctx.l("TXTREV")),
                 o.change_var(V("tSlot"), 1),
                 o.change_var(V("tI"), 1),
                 o.change_var(V("tX"), o.mul(o.div(V("tSize"), 100), ADV))),
    )

    text_r.define(
        # right-aligned: back up one glyph width per character, then draw
        o.set_var(V("tLen"), o.length_of(text_r.arg(1))),
        o.set_var(V("tSize"), text_r.arg(4)),
        o.set_var(V("tX"), o.sub(text_r.arg(2),
                                 o.mul(o.mul(V("tLen"), o.div(V("tSize"), 100)),
                                       ADV))),
        text.call(text_r.arg(0), text_r.arg(1), V("tX"), text_r.arg(3), V("tSize")),
    )

    clear_text.define(
        o.change_var(V("tRev"), 1),
        o.set_var(V("tSlot"), 1),
        o.repeat(TEXT_SLOTS,
                 o.replace_item(V("tSlot"), " ", ctx.l("TXTCH")),
                 o.replace_item(V("tSlot"), V("tRev"), ctx.l("TXTREV")),
                 o.change_var(V("tSlot"), 1)),
    )

    boom.define(
        # GRAPHICS LOW halves every burst; ULTRA skips particles entirely
        # (the Particles toggle still overrides both).
        o.if_(o.allof(o.eq(V("fxOn"), 1), o.lt(V("detail"), 2)),
              o.set_var(V("fxAtX"), boom.arg(0)),
              o.set_var(V("fxAtY"), boom.arg(1)),
              o.ifelse(o.eq(V("detail"), 1),
                       [o.set_var(V("fxN"),
                                  o.mathop("ceiling",
                                           o.div(boom.arg(2), 2)))],
                       [o.set_var(V("fxN"), boom.arg(2))]),
              o.broadcast("boom", ctx.b("boom"))),
    )

    # ---------------- top-level scripts ----------------
    g.script(o.when_flag(),
             setup.call(),
             o.forever(tick.call()),
             x=30, y=30,
             comment="Master clock. One loop iteration == one Scratch frame.")

    g.script(o.when_key("p"),
             # if/else, not two ifs: as two sequential ifs the first one would
             # set state to "pause" and the second would immediately read that
             # back and undo it, so P could never actually pause.
             o.ifelse(o.eq(V("state"), "play"),
                      [o.set_var(V("state"), "pause"),
                       o.set_var(V("sel"), 1),
                       o.set_var(V("selCount"), 3),
                       o.set_var(V("track"), "music0"),
                       o.switch_backdrop("pause")],
                      [o.if_(o.eq(V("state"), "pause"),
                             o.set_var(V("state"), "play"),
                             # the space/enter press that resumed (or any tap
                             # made while paused) must not reach the sim: a
                             # latched edge here would phantom-jump or trigger
                             # an orb on the first step back
                             o.set_var(V("tapLatch"), 0),
                             o.set_var(V("track"), o.join("music", V("level"))),
                             o.switch_backdrop_var(o.join("bg", V("level")),
                                                   "bg1"))]),
             x=900, y=30)

    g.script(o.when_key("r"),
             o.if_(o.anyof(o.eq(V("state"), "play"),
                           o.anyof(o.eq(V("state"), "dead"),
                                   o.eq(V("state"), "pause"))),
                   start_level.call(V("level"))),
             x=1180, y=30)

    # Q, not Escape: scratch-vm's Keyboard IO device maps every DOM key whose
    # name is longer than one character to "" and drops it, so an "escape" hat
    # can never fire -- and Escape is not in Scratch's key dropdown anyway.
    g.script(o.when_key("q"),
             o.if_(o.not_(o.eq(V("state"), "menu")), goto_screen.call("menu")),
             x=1420, y=30,
             comment="Q backs out of every screen, not just the level: without "
                     "it there was no way off LEVEL SELECT but to pick a level.")

    g.script(o.when_key("m"),
             o.set_var(V("musicOn"), o.sub(1, V("musicOn"))),
             o.broadcast("music", ctx.b("music")),
             o.if_(o.eq(V("state"), "settings"), paint.call()),
             x=1660, y=30)
    return g


# ---------------------------------------------------------------------------
def _cellchar(ctx):
    """letter ((rr * (W + 1)) + cc + 1) of LVL"""
    idx = o.add(o.add(o.mul(ctx.v("rr"), o.add(ctx.v("W"), 1)), ctx.v("cc")), 1)
    return o.letter_of(idx, ctx.v("LVL"))


def _cell_key(ctx):
    """Stable per-cell id, used to remember coins already collected."""
    return o.join(o.mul(ctx.v("rr"), 1000), ctx.v("cc"))


def _sel_count(ctx, state_arg):
    """selCount depends on which screen is showing; no if/else reporter needed."""
    V = ctx.v
    return [o.set_var(V("selCount"), 1)] + [
        o.if_(o.eq(state_arg, name), o.set_var(V("selCount"), count))
        for name, count in SEL_COUNT.items()
    ]


def _paint_select(ctx, text_r):
    return [text_r.call(1 + i * 6,
                        o.join(o.item_of(i + 1, ctx.l("BESTS")), "%"),
                        156, SELECT_ROW_Y[i], 110)
            for i in range(3)]


def _paint_settings(ctx, text_r):
    V = ctx.v
    out = []
    rows = ("musicOn", "sfxOn", "fxOn", "lowLatency", "showFps")
    for i, var in enumerate(rows):
        out.append(o.ifelse(o.eq(V(var), 1),
                            [text_r.call(1 + i * 4, "ON", 156,
                                         SETTINGS_VAL_Y[i], 100)],
                            [text_r.call(1 + i * 4, "OFF", 156,
                                         SETTINGS_VAL_Y[i], 100)]))
    for i, name in ((0, "HIGH"), (1, "LOW"), (2, "ULTRA")):
        out.append(o.if_(o.eq(V("detail"), i),
                         text_r.call(21, name, 156, SETTINGS_VAL_Y[5], 100)))
    return out


def _paint_win(ctx, text):
    V = ctx.v
    return [
        text.call(1, o.join(o.join("COINS  ", V("coins")),
                            o.join(" / ", V("coinTotal"))), 148, 52, 110),
        text.call(12, o.join("TIME  ", o.join(o.mathop(
            "floor", o.div(V("frame"), 30)), "S")), 158, 26, 110),
    ]


# ---------------------------------------------------------------------------
def _build_player(ctx: Ctx):
    s = Target("Player", layer_order=5)
    for i in (1, 2, 3):
        s.add_costume(f"cube{i}", art.player_cube(art.THEMES[i]), "png", 30, 30, 2)
    s.add_costume("ghost", art.player_ghost(art.THEMES[1]), "png", 30, 30, 2)
    s.x = PLAYER_X
    s.y = GY + HALF
    ctx.p.sprites.append(s)
    V = ctx.v
    s.var("dirTmp", 90)

    s.script(o.when_flag(),
             o.hide(),
             o.set_size(100),
             o.clear_effects(),
             o.forever(
                 o.ifelse(o.eq(V("state"), "play"),
                          [o.show(),
                           o.switch_costume_var(o.join("cube", V("level")), s,
                                                "cube1"),
                           o.set_effect("ghost", 0)],
                          [o.ifelse(o.eq(V("state"), "dead"),
                                    [o.show(),
                                     o.switch_costume("ghost"),
                                     o.set_effect("ghost", 35)],
                                    [o.hide()])]),
                 o.goto_xy(o.add(PLAYER_X, V("shakeX")),
                           o.add(V("py"), V("shakeY"))),
                 # direction 90 means "no rotation"; +180 when inverted
                 o.set_var(s.var("dirTmp"), o.add(90, V("rot"))),
                 o.if_(o.eq(V("grav"), -1), o.change_var(s.var("dirTmp"), 180)),
                 o.point_direction(s.var("dirTmp"))),
             x=30, y=30,
             comment="Presentation only: reads py/rot/grav written by Game.")
    return s


# ---------------------------------------------------------------------------
# Tile costumes are named after the level character they draw, so
# ``switch costume to (ch)`` needs no lookup table at runtime. Rotation centres
# sit at the *bottom* centre of each cell so one y formula fits every tile.
# ---------------------------------------------------------------------------
TILE_ART = {
    "#": ("tile_block", (30, 60)),
    "^": ("tile_spike_up", (30, 60)),
    "v": ("tile_spike_down", (30, 60)),
    "P": ("tile_pad", (30, 60)),
    "O": ("tile_orb", (30, 60)),
    "C": ("tile_coin", (30, 60)),
    "G": ("tile_portal", (30, 180)),
    "N": ("tile_portal", (30, 180)),
    "F": ("tile_finish", (12, 420)),
}


def _build_tile(ctx: Ctx):
    s = Target("Tile", layer_order=4)
    for ch, (fn, center) in TILE_ART.items():
        theme = dict(art.THEMES[1])
        if ch == "G":
            theme["accent"] = (255, 120, 240, 255)
        elif ch == "N":
            theme["accent"] = (90, 200, 255, 255)
        s.add_costume(ch, getattr(art, fn)(theme), "png", center[0], center[1], 2)
    s.visible = False
    ctx.p.sprites.append(s)
    V = ctx.v

    # sprite-local: makeClone() duplicates them, so every clone keeps its own
    for name in ("tCol", "tRow", "tChar", "tGen"):
        s.var(name, 0)

    spawn_tick = o.Proc(s, "spawn tick")
    spawn_column = o.Proc(s, "spawn column")

    spawn_tick.define(
        o.set_var(V("spawnHi"),
                  o.floor_(o.div(o.add(V("worldX"), SPAWN_AHEAD), CELL))),
        # worldX only moves on physics steps, so most rendered frames have
        # nothing new to materialise; skip the whole scan when the spawner is
        # caught up (or the level is fully spawned)
        o.if_(o.allof(le(V("spawnCol"), V("spawnHi")),
                      o.lt(V("spawnCol"), o.add(V("W"), 2))),
              o.repeat(8,
                       o.if_(o.allof(le(V("spawnCol"), V("spawnHi")),
                                     o.lt(V("spawnCol"), o.add(V("W"), 2))),
                             spawn_column.call(),
                             o.change_var(V("spawnCol"), 1)))),
    )

    spawn_column.define(
        o.set_var(V("cc"), V("spawnCol")),
        o.set_var(V("rr"), 0),
        o.repeat(ROWS,
                 o.set_var(V("ch"), _cellchar(ctx)),
                 # the finish flag is one tall costume, so only row 0 draws it
                 o.if_(o.allof(o.not_(o.eq(V("ch"), ".")),
                               o.not_(o.allof(o.eq(V("ch"), "F"),
                                              o.gt(V("rr"), 0)))),
                       o.set_var(s.var("tCol"), V("cc")),
                       o.set_var(s.var("tRow"), V("rr")),
                       o.set_var(s.var("tChar"), V("ch")),
                       o.set_var(s.var("tGen"), V("gen")),
                       o.goto_xy(o.sub(o.add(o.mul(V("cc"), CELL), HALF),
                                       V("worldX")),
                                 o.add(GY, o.mul(V("rr"), CELL))),
                       o.switch_costume_var(V("ch"), s, "#"),
                       o.create_clone("_myself_")),
                 o.change_var(V("rr"), 1)),
        comment="tCol/tRow/tChar/tGen are copied into each clone at creation.",
    )

    s.script(o.when_flag(),
             o.hide(),
             o.forever(o.if_(o.eq(V("state"), "play"), spawn_tick.call())),
             x=30, y=30)

    s.script(o.as_clone(),
             o.show(),
             o.forever(
                 o.if_(o.not_(o.eq(s.var("tGen"), V("gen"))), o.delete_clone()),
                 # scroll left by exactly the distance the world scrolled this
                 # frame: SPEED per physics step. Tiles are born at
                 # (tCol*CELL + HALF) - worldX, and worldX grows by SPEED per
                 # step, so decrementing by SPEED*stepsRun per rendered frame
                 # keeps every tile aligned with its cell (all values are
                 # integer-valued floats, so nothing drifts).
                 o.if_(o.gt(V("stepsRun"), 0),
                       o.change_x(o.mul(-SPEED, V("stepsRun")))),
                 o.if_(o.lt(o.x_position(), DESPAWN_X), o.delete_clone())),
             x=430, y=30,
             comment="y and costume were fixed by the parent before cloning.")
    return s


# ---------------------------------------------------------------------------
def _build_ground(ctx: Ctx):
    s = Target("Ground", layer_order=3)
    for i in (1, 2, 3):
        th = art.THEMES[i]
        s.add_costume(f"floor{i}", art.ground_strip(th, 480, 120), "png", 480, 0, 2)
        s.add_costume(f"ceil{i}", art.ground_strip(th, 480, 120, flip=True),
                      "png", 480, 240, 2)
    s.visible = False
    ctx.p.sprites.append(s)
    V = ctx.v
    s.var("wGen", 0)
    s.var("isClone", 0)

    s.script(o.when_flag(), o.hide(), o.set_var(s.var("isClone"), 0), x=30, y=30)

    # Broadcast hats are inherited by clones in Scratch. Only the original
    # controller may respond: otherwise every live strip clone also spawns
    # four more strips on every restart (exponential clone growth).
    s.script(o.when_broadcast("level start", ctx.b("level start")),
             o.if_(o.eq(s.var("isClone"), 0),
                   o.set_var(s.var("wGen"), V("gen")),
                   o.switch_costume_var(o.join("floor", V("level")), s, "floor1"),
                   o.goto_xy(0, GY), o.create_clone("_myself_"),
                   o.goto_xy(480, GY), o.create_clone("_myself_"),
                   o.switch_costume_var(o.join("ceil", V("level")), s, "ceil1"),
                   o.goto_xy(0, CEIL_Y), o.create_clone("_myself_"),
                   o.goto_xy(480, CEIL_Y), o.create_clone("_myself_")),
             x=30, y=120,
             comment="Only the original responds; clones must not fan out broadcasts.")

    s.script(o.as_clone(),
             o.set_var(s.var("isClone"), 1),
             o.show(),
             o.forever(
                 o.if_(o.not_(o.eq(s.var("wGen"), V("gen"))), o.delete_clone()),
                 # one world-scroll per physics step keeps the floor locked to
                 # the tiles at any render rate
                 o.change_x(o.mul(-SPEED, V("stepsRun"))),
                 o.if_(o.lt(o.x_position(), -480), o.change_x(960))),
             x=430, y=120)
    return s


def _build_far(ctx: Ctx):
    s = Target("Far", layer_order=2)
    for i in (1, 2, 3):
        th = art.THEMES[i]
        s.add_costume(f"far{i}", art.parallax_layer(th, "near", th["seed"]),
                      "png", 480, 360, 2)
    s.visible = False
    ctx.p.sprites.append(s)
    V = ctx.v
    s.var("wGen", 0)
    s.var("isClone", 0)

    s.script(o.when_flag(), o.hide(), o.set_var(s.var("isClone"), 0), x=30, y=30)

    s.script(o.when_broadcast("level start", ctx.b("level start")),
             o.if_(o.eq(s.var("isClone"), 0),
                   o.set_var(s.var("wGen"), V("gen")),
                   o.switch_costume_var(o.join("far", V("level")), s, "far1"),
                   # GRAPHICS LOW/ULTRA skips the parallax layer entirely
                   o.if_(o.eq(V("detail"), 0),
                         o.goto_xy(0, 0), o.create_clone("_myself_"),
                         o.goto_xy(480, 0), o.create_clone("_myself_"))),
             x=30, y=120,
             comment="Only the original responds; clones must not fan out broadcasts.")

    s.script(o.as_clone(),
             o.set_var(s.var("isClone"), 1),
             o.show(),
             o.forever(
                 # GRAPHICS LOW/ULTRA retires the parallax live as well
                 o.if_(o.gt(V("detail"), 0), o.delete_clone()),
                 o.if_(o.not_(o.eq(s.var("wGen"), V("gen"))), o.delete_clone()),
                 o.change_x(o.mul(-4, V("stepsRun"))),
                 o.if_(o.lt(o.x_position(), -480), o.change_x(960))),
             x=330, y=120,
             comment="Slower than the ground, which is what sells the depth. "
                     "Moves one parallax step per physics step.")
    return s


# ---------------------------------------------------------------------------
def _build_fx(ctx: Ctx):
    s = Target("FX", layer_order=6)
    s.add_costume("spark", art.fx_spark(10), "png", 10, 10, 2)
    s.add_costume("shard", art.fx_shard(12), "png", 12, 12, 2)
    s.add_costume("ring", art.fx_ring(28), "png", 28, 28, 2)
    s.visible = False
    ctx.p.sprites.append(s)
    V = ctx.v
    for name in ("pVx", "pVy", "pLife", "pSize", "pName",
                 "myVx", "myVy", "myLife"):
        s.var(name, 0)
    s.var("isClone", 0)

    s.script(o.when_flag(), o.hide(), o.set_var(s.var("isClone"), 0), x=30, y=30)

    # Particle clones inherit broadcast hats too. Restrict the burst factory
    # to the original so each boom creates exactly fxN particles, not a cascade.
    s.script(o.when_broadcast("boom", ctx.b("boom")),
             o.if_(o.eq(s.var("isClone"), 0),
                   o.set_var(V("tI"), 1),
                   o.repeat(V("fxN"),
                            o.set_var(s.var("pVx"), o.div(o.rand(-90, 90), 10)),
                            o.set_var(s.var("pVy"), o.div(o.rand(-20, 110), 10)),
                            o.set_var(s.var("pLife"), o.rand(14, 30)),
                            o.set_var(s.var("pSize"), o.rand(70, 130)),
                            # first particle of every burst is the shockwave ring
                            o.set_var(s.var("pName"), "spark"),
                            o.if_(o.eq(o.rand(1, 3), 3),
                                  o.set_var(s.var("pName"), "shard")),
                            o.if_(o.eq(V("tI"), 1), o.set_var(s.var("pName"), "ring")),
                            o.switch_costume_var(s.var("pName"), s, "spark"),
                            o.goto_xy(o.add(V("fxAtX"), o.div(o.rand(-12, 12), 2)),
                                      o.add(V("fxAtY"), o.div(o.rand(-12, 12), 2))),
                            o.create_clone("_myself_"),
                            o.change_var(V("tI"), 1))),
             x=30, y=120,
             comment="Only the original handles boom; effects do not recurse.")

    s.script(o.as_clone(),
             o.set_var(s.var("isClone"), 1),
             o.set_var(s.var("myVx"), s.var("pVx")),
             o.set_var(s.var("myVy"), s.var("pVy")),
             o.set_var(s.var("myLife"), s.var("pLife")),
             o.set_size(s.var("pSize")),
             o.set_effect("ghost", 0),
             o.show(),
             o.repeat_until(o.lt(s.var("myLife"), 1),
                            o.change_x(s.var("myVx")),
                            o.change_y(s.var("myVy")),
                            o.change_var(s.var("myVy"), -0.55),
                            o.change_var(s.var("myLife"), -1),
                            o.change_size(-3),
                            o.change_effect("ghost", 3)),
             o.delete_clone(),
             x=430, y=120)
    return s


# ---------------------------------------------------------------------------
def _build_hud(ctx: Ctx):
    s = Target("Hud", layer_order=7)
    for i in (1, 2, 3):
        lv = levels.LEVELS[i - 1]
        s.add_costume(f"lv{i}", art.hud_name(f"{i}  {lv.name}", art.THEMES[i]),
                      "png", 200, 22, 2)
    s.add_costume("bar", art.ui_bar(208, 16), "png", 208, 16, 2)
    s.visible = False
    ctx.p.sprites.append(s)
    V = ctx.v
    s.var("role", 0)
    s.var("myRole", 0)

    s.script(o.when_flag(),
             o.hide(),
             o.set_var(s.var("role"), 1), o.create_clone("_myself_"),
             o.set_var(s.var("role"), 2), o.create_clone("_myself_"),
             x=30, y=30)

    s.script(o.as_clone(),
             o.set_var(s.var("myRole"), s.var("role")),
             o.forever(
                 o.ifelse(o.eq(V("state"), "play"),
                          [o.show(),
                           o.ifelse(o.eq(s.var("myRole"), 1),
                                    [o.switch_costume_var(
                                        o.join("lv", V("level")), s, "lv1"),
                                     o.goto_xy(-140, 166)],
                                    [o.switch_costume("bar"),
                                     o.goto_xy(0, 140)])],
                          [o.hide()])),
             x=330, y=30)
    return s


def _build_sel(ctx: Ctx):
    s = Target("Sel", layer_order=8)
    s.add_costume("sel", art.ui_selector(250, 26), "png", 250, 26, 2)
    # the settings rows carry a value pill out to stage x=162, so that screen
    # gets a wider highlight; 250 px would stop mid-pill (v0.2.2 fix)
    s.add_costume("selWide", art.ui_selector(360, 26), "png", 360, 26, 2)
    s.visible = False
    ctx.p.sprites.append(s)
    V = ctx.v
    s.var("rowY", 0)
    # costume mirror: only switch (and dirty the renderer) when the screen
    # kind actually changed, instead of every frame
    s.var("selMode", 0)

    on_menu = o.anyof(o.anyof(o.eq(V("state"), "menu"),
                              o.eq(V("state"), "select")),
                      o.anyof(o.eq(V("state"), "settings"),
                              o.anyof(o.eq(V("state"), "pause"),
                                      o.eq(V("state"), "win"))))
    s.script(o.when_flag(),
             o.hide(),
             o.forever(
                 o.ifelse(on_menu,
                          [o.show(),
                           o.ifelse(o.eq(V("state"), "settings"),
                                    [o.if_(o.eq(s.var("selMode"), 0),
                                           o.switch_costume("selWide"),
                                           o.set_var(s.var("selMode"), 1))],
                                    [o.if_(o.eq(s.var("selMode"), 1),
                                           o.switch_costume("sel"),
                                           o.set_var(s.var("selMode"), 0))]),
                           *_sel_y_chain(ctx, s)],
                          [o.hide()])),
             x=30, y=30,
             comment="The highlight follows the selected row on every screen.")
    return s


def _sel_y_chain(ctx, s):
    """Position the menu highlight.

    Every screen's selectable rows are evenly spaced, so instead of testing
    state x selection in a 16-branch chain each frame, per screen the row y is
    `base - step * (sel - 1)`, derived here from SEL_Y itself. The visible
    result is identical; the per-frame cost drops from ~16 comparisons to 5.
    """
    V = ctx.v
    blocks = [o.set_var(s.var("rowY"), 0)]
    for screen, ys in SEL_Y.items():
        assert all(ys[i] - ys[i + 1] == ys[0] - ys[1] for i in range(len(ys) - 1)), \
            f"{screen}: rows are not evenly spaced"
        base, step = ys[0], ys[0] - ys[1]
        blocks.append(o.if_(
            o.eq(V("state"), screen),
            o.set_var(s.var("rowY"),
                      o.sub(base, o.mul(step, o.sub(V("sel"), 1))))))
    blocks.append(o.goto_xy(0, s.var("rowY")))
    return blocks


# ---------------------------------------------------------------------------
# Runtime text. Every static label is baked into a backdrop; this pool only
# draws the values that change (percentages, attempts, coins, ON/OFF).
# ---------------------------------------------------------------------------
def _build_text(ctx: Ctx):
    s = Target("Text", layer_order=9)
    glyphs = art.glyph_images()
    s.add_costume("space", glyphs["space"], "png", 0, 14, 2)
    for name in sorted(glyphs):
        if name != "space":
            s.add_costume(name, glyphs[name], "png", 0, 14, 2)
    s.visible = False
    s.rotation_style = "don't rotate"
    ctx.p.sprites.append(s)
    for name in ("nextSlot", "mySlot", "myChar", "myRev"):
        s.var(name, 0)

    s.script(o.when_flag(),
             o.hide(),
             o.set_var(s.var("nextSlot"), 1),
             o.repeat(TEXT_SLOTS,
                      o.create_clone("_myself_"),
                      o.change_var(s.var("nextSlot"), 1)),
             x=30, y=30,
             comment="Fixed pool; each clone keeps the slot number it was born with.")

    s.script(o.as_clone(),
             o.set_var(s.var("mySlot"), s.var("nextSlot")),
             o.set_var(s.var("myChar"), "?"),
             o.forever(
                 # only touch costume/position/size when this slot's text was
                 # rewritten (TXTREV[slot] != myRev); otherwise the clone is a
                 # no-op this frame
                 o.if_(o.not_(o.eq(o.item_of(s.var("mySlot"), ctx.l("TXTREV")),
                                   s.var("myRev"))),
                       o.set_var(s.var("myRev"),
                                 o.item_of(s.var("mySlot"), ctx.l("TXTREV"))),
                       o.set_var(s.var("myChar"),
                                 o.item_of(s.var("mySlot"), ctx.l("TXTCH"))),
                       o.ifelse(o.eq(s.var("myChar"), " "),
                                [o.hide()],
                                [o.show(),
                                 o.switch_costume_var(s.var("myChar"), s, "A")]),
                       o.goto_xy(o.item_of(s.var("mySlot"), ctx.l("TXTX")),
                                 o.item_of(s.var("mySlot"), ctx.l("TXTY"))),
                       o.set_size(o.item_of(s.var("mySlot"), ctx.l("TXTS"))))),
             x=330, y=30)
    return s


# ---------------------------------------------------------------------------
def _build_sound(ctx: Ctx):
    s = Target("Sound", layer_order=10)
    s.add_costume("dot", art.ui_dot(2), "png", 2, 2, 2)
    s.visible = False
    ctx.p.sprites.append(s)
    V = ctx.v

    for name, data in _sounds():
        rate, frames = audio.meta(data)
        s.add_sound(name, data, rate, frames)

    s.script(o.when_flag(), o.hide(), x=30, y=30)

    s.script(o.when_broadcast("music", ctx.b("music")),
             o.stop_all_sounds(),
             o.forever(
                 o.ifelse(o.eq(V("musicOn"), 1),
                          [o.play_sound_until_done_var(V("track"), "music0")],
                          [o.wait(0.25)])),
             x=30, y=120,
             comment="One looping thread; 'play until done' parks the thread "
                     "until the track finishes, so the repeats stay gapless. "
                     "The track name is kept in `track` by the state "
                     "transitions (start level, screens, pause, win), so the "
                     "loop body no longer re-derives it every iteration.")

    x = 430
    for msg in ("sfx jump", "sfx die", "sfx coin", "sfx portal", "sfx pad",
                "sfx orb", "sfx click", "sfx select", "sfx win"):
        s.script(o.when_broadcast(msg, ctx.b(msg)),
                 o.if_(o.eq(V("sfxOn"), 1), o.play_sound(msg)),
                 x=x, y=120)
        x += 260
    return s


def _sounds():
    yield "sfx jump", audio.sfx_jump()
    yield "sfx die", audio.sfx_die()
    yield "sfx coin", audio.sfx_coin()
    yield "sfx portal", audio.sfx_portal()
    yield "sfx pad", audio.sfx_pad()
    yield "sfx orb", audio.sfx_orb()
    yield "sfx click", audio.sfx_click()
    yield "sfx select", audio.sfx_select()
    yield "sfx win", audio.sfx_win()
    yield "music0", audio.menu_music()
    for i in (1, 2, 3):
        yield f"music{i}", audio.level_music(i)
