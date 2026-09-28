# GD-Scratch

**Geometry Dash, built entirely out of stock Scratch 3 blocks.**

An auto-running cube, one-button jumping, spikes and gravity portals, three
hand-built levels, a title screen with records, a level select, settings, pause,
synthesised music and SFX — all of it in a single `.sb3` that loads in Scratch
3.32.1, on scratch.mit.edu, and in TurboWarp. No extensions, no hacks, no
custom runtime: `project.json` declares `"extensions": []`.

**v0.2.1** makes the game frame-rate-independent and cheaper to run. The
simulation is now a fixed 30 Hz clock driven by the `timer` with an
accumulator and a catch-up cap (see below), so the game plays identically at
30 fps, at 60 fps under TurboWarp, or at any other render cadence; a
render-cadence input latch keeps taps exact at high frame rates; and per-frame
primitive work dropped 36–46% across all benchmark scenarios with identical
inputs. It also fixes a pause/resume input leak found by audit. Gameplay,
levels, physics and feel are unchanged — all three solver solutions still
replay frame-exactly. See the
[release verification report](docs/v0.2.1.md).

**v0.2.0** prioritized clone lifecycle stability and runtime reliability. That
release fixed a verified exponential clone-fanout bug on restart/effects, retired
level clones on exit, added the missing grounded-jump sound feedback, and made
noise-based sound asset generation deterministic. See the
[release verification report](docs/v0.2.0.md).

| file | what it is |
| --- | --- |
| [`dist/GD-Scratch.sb3`](dist/GD-Scratch.sb3) | the game — 1.1 MB, stock Scratch 3 blocks only |
| [`dist/GD-Scratch-TurboWarp.sb3`](dist/GD-Scratch-TurboWarp.sb3) | the same project plus the `runtimeOptions` block TurboWarp reads to run at 60 fps with interpolation. Stock Scratch ignores that key, so this file loads there too. |

## Load it

**Scratch 3.32.1 (desktop app)** — `File → Load from your computer…`, pick
`dist/GD-Scratch.sb3`, press the green flag.

**scratch.mit.edu** — sign in, `File → Create → File → Load from your computer`.

**TurboWarp** — drag `dist/GD-Scratch-TurboWarp.sb3` onto
[turbowarp.org](https://turbowarp.org). The TurboWarp file asks for 60 fps
rendering with interpolation; "Turbo mode" on or off, the game runs at the
same speed — only rendering smoothness changes (see below).

## Frame rate & pacing

The visible game runs off a **fixed 30 Hz simulation clock**, not off the
render loop. Every rendered frame the project reads the Scratch `timer`,
accumulates the elapsed simulation time, and runs however many 30 Hz physics
steps are due (0–2 at a smooth 30 fps, exactly 2 per frame at a locked 60 fps).
Consequences:

- **Render-rate independence.** 30 fps and 60 fps (and anything else) play
  identically: same scroll speed, same jump arcs, same countdowns, same music
  timing. Only smoothness differs. All three levels' solver solutions are
  frame-exact at both 30 and 60 fps in the automated tests.
- **Catch-up cap.** At most 3 physics steps run per rendered frame and any
  larger backlog is dropped. A stalled tab or a device slower than ~10 fps
  effective slows the game down uniformly instead of teleporting the cube
  after the stall.
- **Input latch.** Taps are registered when a render frame sees them and
  consumed by exactly one physics step, so a tap shorter than a frame at
  60 fps is never lost and never double-counted. Holding jump to bounce on
  landing works exactly as always.

## Controls

| key | action |
| --- | --- |
| `space` / `up` / click | jump — hold it to jump again the instant you land |
| `up` / `down` | move the menu highlight |
| `space` / `enter` / click | pick a menu entry |
| `P` | pause / resume |
| `R` | restart the level |
| `Q` | quit to the title screen |
| `M` | music on / off |

## The levels

Each level is a text map compiled into a string variable, and each one has been
solved to 100% by a breadth-first search over the exact physics the Scratch
project implements:

| | name | width | length | inputs on the optimal run | solver result |
| --- | --- | --- | --- | --- | --- |
| 1 | STEREO SUNRISE | 225 | 22.0 s / 659 frames | 25 | 100%, win |
| 2 | NEON RUSH | 254 | 24.9 s / 746 frames | 28 | 100%, win |
| 3 | GRAVITY FLUX | 300 | 29.0 s / 869 frames | 22 | 100%, win |

Level 3 introduces gravity portals that flip the cube to the ceiling, so the
optimal run needs fewer jumps than level 2 despite being the longest.

## How it is built

Nothing here is hand-assembled in the Scratch editor. A Python package emits the
whole project — sprites, costumes, sounds, scripts — as a `.sb3`:

```
src/gdscratch/
  png.py     RGBA image + PNG encoder (no Pillow needed)
  font.py    69-glyph 5x7 bitmap font
  art.py     every costume and backdrop, drawn pixel by pixel
  audio.py   22.05 kHz mono WAV synthesiser for the music and SFX
  sb3.py     the .sb3 project model: targets, variables, blocks, zip writer
  ops.py     a small DSL over the stock Scratch 3 block set
  levels.py  the level maps and the reference physics
  verify.py  the same physics as a step function, plus a BFS solver
  game.py    the actual game, written in the DSL
  build.py   CLI that writes dist/*.sb3
```

```sh
PYTHONPATH=src python3 -m gdscratch.build --out dist
```

The level maps live in `levels.py` as plain text (`#` block, `^` spike, `P` pad,
`O` orb, `C` coin, `G`/`N` portals, `F` finish), which is also what
`verify.py` solves and what the generated project reads at runtime, character
by character.

## Verification

`tests/run_all.sh` runs everything:

```sh
./tests/run_all.sh          # needs npm (Node) for the scratch-vm rig
```

1. **`tools/verify_levels.py`** — solves all three levels against the reference
   physics and asserts each one reaches 100%.
2. **`tests/check_audio_determinism.py`** — synthesizes the declared sounds twice
   and compares WAV bytes to catch accidental use of unseeded randomness.
3. **`tests/headless/harness.js`** — loads the built `.sb3` into the real
   `scratch-vm` and audits it the way Scratch would: every opcode must be a core
   primitive, every custom-block call must resolve to a definition, every input
   name must be one the VM actually reads, every asset's md5 must match its
   filename, every PNG and WAV must decode.
4. **`tests/headless/replay.js`** — plays each level by driving the menu with
   real key events, then replays the solver's input schedule and compares
   `frame`, `y`, `vy`, `grav` and `grounded` **frame by frame, exactly**, against
   the Python reference. A single differing frame fails the run.
5. **`tests/headless/menus.js`** — menu navigation and wrapping, highlight
   positions, level select, settings toggles, help, pause/resume, restart, quit,
   the win-screen input lock, mouse activation, jump SFX playback, and exactly
   one master-clock tick per frame.
6. **`tests/headless/lifecycle.js`** — restarts a level eight times, quits to the
   menu and stresses repeated particle bursts. It counts live `scratch-vm`
   targets to catch clone fan-out, stale level scenery and effects that fail to
   clean up.
7. **`tests/headless/bench.js`** — repeatable menu/gameplay/restart/death/pause
   workloads. Reports median-of-runs step timing, opcode work per frame,
   redraws, and peak live clone/target counts. Use the same archive and options
   for comparisons; headless timings are host-dependent.
8. **`tools/audit_project.py`** — static wiring inventory for broadcasts,
   sounds, clone sites and forever loops. Its findings are leads to investigate,
   not runtime bug reports.

For v0.2.0, the three solver schedules still replay identically (659 + 746 +
869 frames, zero physics mismatches), menu and lifecycle checks pass, and the
VM audit reports no unknown opcodes, unresolvable calls, bad input names or
runtime errors. See [`docs/v0.2.0.md`](docs/v0.2.0.md) for the verified fixes,
benchmark methodology and before/after results.

## Notes on making it actually run in Scratch

Four behaviours of the Scratch 3 runtime decide whether a generated project
works, and none of them produce an error message when you get them wrong. They
are handled in the generator and covered by the tests above.

**A custom block without its mutator shadow is a silent no-op.**
`procedures_definition` must carry a nested `procedures_prototype` shadow in a
`custom_block` input. `Blocks.getProcedureDefinition` resolves a call by
comparing *that* mutation's proccode; without it the definition is never found
and `procedures_call` does nothing at all — no warning, no error. The harness
fails the build if any call is unresolvable.

**Arithmetic blocks take `NUM1`/`NUM2`, comparisons take `OPERAND1`/`OPERAND2`.**
`operator_add` with `OPERAND1` reads `undefined`, casts it to 0, and every
`+ - * /` in the project silently evaluates to zero. The harness now validates
every input name in the project against the argument list the VM itself
declares.

**IDs are project-global, not per-sprite.**
A variable reference resolves against the owning target's own variables first.
Give a sprite-local the same ID as a stage variable and every test of that stage
variable on that sprite quietly reads the local instead.

**A `forever` loop is only one iteration per frame if something asks for a
redraw.**
`Sequencer.stepThreads` keeps re-running threads until the frame's work-time
budget is spent, and the only thing that ends it early is
`runtime.requestRedraw()` — which `RenderedTarget` calls only for a sprite that
is both visible and attached to a renderer. A loop of pure variable arithmetic
therefore spins hundreds of times per frame. The master clock sprite is a
transparent 1×1 pixel that moves by zero every tick, purely to request that
redraw; that is what holds the whole game to one tick per frame. (`control_wait`
also requests a redraw, but it costs an extra frame per iteration, so it would
halve the tick rate.)

Related: `when [escape] key pressed` can never fire — the keyboard IO device
maps every DOM key name longer than one character to `""` and drops it, and
Escape is not in Scratch's key menu. `Q` is used instead.

## Browser preview

`preview/` is a small player (scratch-vm + scratch-render + scratch-audio +
scratch-storage) that runs the built archives:

```sh
(cd tests/headless && npm ci)     # once, for the scratch-* browser bundles
python3 preview/serve.py --port 8600
```

It serves everything from inside the repository, so it needs no network access
once the npm dependencies are installed. The bundles themselves stay out of git.
