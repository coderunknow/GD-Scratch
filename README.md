# GD-Scratch

**Geometry Dash, built entirely out of stock Scratch 3 blocks.**

An auto-running cube, one-button jumping, spikes and gravity portals, three
hand-built levels, a title screen with records, a level select, settings, pause,
synthesised music and SFX — all of it in a single `.sb3` that loads in Scratch
3.32.1, on scratch.mit.edu, and in TurboWarp. No extensions, no hacks, no
custom runtime: `project.json` declares `"extensions": []`.

| file | what it is |
| --- | --- |
| [`dist/GD-Scratch.sb3`](dist/GD-Scratch.sb3) | the game — 1.1 MB, stock Scratch 3 blocks only |
| [`dist/GD-Scratch-TurboWarp.sb3`](dist/GD-Scratch-TurboWarp.sb3) | the same project plus the `runtimeOptions` block TurboWarp reads to run at 60 fps with interpolation. Stock Scratch ignores that key, so this file loads there too. |

## Load it

**Scratch 3.32.1 (desktop app)** — `File → Load from your computer…`, pick
`dist/GD-Scratch.sb3`, press the green flag.

**scratch.mit.edu** — sign in, `File → Create → File → Load from your computer`.

**TurboWarp** — drag `dist/GD-Scratch-TurboWarp.sb3` onto
[turbowarp.org](https://turbowarp.org). Tick "Turbo mode" off if you want the
vanilla 30 fps feel; the game is paced to run at the same speed either way.

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
2. **`tests/headless/harness.js`** — loads the built `.sb3` into the real
   `scratch-vm` and audits it the way Scratch would: every opcode must be a core
   primitive, every custom-block call must resolve to a definition, every input
   name must be one the VM actually reads, every asset's md5 must match its
   filename, every PNG and WAV must decode.
3. **`tests/headless/replay.js`** — plays each level by driving the menu with
   real key events, then replays the solver's input schedule and compares
   `frame`, `y`, `vy`, `grav` and `grounded` **frame by frame, exactly**, against
   the Python reference. A single differing frame fails the run.
4. **`tests/headless/menus.js`** — 40-odd assertions on the parts a player
   touches between levels: menu navigation and wrapping, the highlight position
   on every screen, level select, settings toggles, help, pause/resume, restart,
   quit, the win-screen input lock, mouse activation, and that the master clock
   advances exactly one tick per frame.

Last run: all three levels replayed identically (659 + 746 + 869 frames, zero
mismatches), all menu checks passed, and the audit reported zero unknown
opcodes, zero unresolvable calls, zero bad input names and zero VM warnings.

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
