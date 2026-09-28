/**
 * Shared plumbing for the headless scratch-vm drivers.
 */

const fs = require('fs');
const VM = require('scratch-vm');
const {ScratchStorage} = require('scratch-storage');

/** Scratch's own frame rate: one `_step()` every 33.33 ms. */
const STEP_MS = 1000 / 30;

/** Keys as scratch-vm's Keyboard IO device expects them (DOM `KeyboardEvent.key`). */
const DOM_KEY = {
    'space': ' ',
    'up arrow': 'ArrowUp',
    'down arrow': 'ArrowDown',
    'left arrow': 'ArrowLeft',
    'right arrow': 'ArrowRight',
    'enter': 'Enter',
    'escape': 'Escape'
};

/** scratch-vm is a CommonJS package whose default export is the VM class. */
function VMClass () {
    return typeof VM === 'function' ? VM : (VM.VM || VM.default);
}

function makeVM () {
    const vm = new (VMClass())();
    vm.attachStorage(new ScratchStorage());
    return vm;
}

/**
 * Replace the wall clock with a simulated one advancing exactly one frame per
 * `_step()`.
 *
 * `control_wait` -- and therefore the frame pacing at the bottom of every
 * `forever` in the game -- is timed against `runtime.currentMSecs`, which
 * normally comes from `Date.now()`. Driving the VM from a tight loop would make
 * "one frame" take as long as the host happens to be busy, so a `wait 0.028`
 * would need a variable number of `_step()` calls before it expired. Advancing
 * the clock by hand makes one `_step()` == 1000/fps ms == exactly one render
 * frame, which is what lets replay.js compare the generated game against the
 * Python reference solver frame for frame.
 *
 * The game's simulation-time accumulator reads Scratch's `timer` block, which
 * scratch-vm serves from `ioDevices.clock.projectTimer()` -- and *that* is
 * derived from `runtime.currentMSecs` too (clock.js constructs its Timer with
 * `now: () => runtime.currentMSecs`). simClock alone would therefore make the
 * timer deterministic as well, but it accumulates `currentStepTime` by repeated
 * floating-point addition, so `floor(timer * 30)` occasionally strays an
 * epsilon across a tick boundary (measured: 8 off-by-one events in 2000 frames
 * at 30 fps, and systematic half-tick errors at 60 fps). To keep the headless
 * clock exact, projectTimer is stubbed directly: on the n-th `_step()` after a
 * green flag it returns `(n - 0.5) / fps` seconds. The half-frame offset keeps
 * every value exactly 0.25 ticks away from a 30 Hz boundary (these are binary-
 * exact numbers), so `floor(timer * 30)` is 1 on every frame at 30 fps and
 * alternates 0,1,0,1... at 60 fps -- with zero float luck involved. A real
 * browser clock is never float-exact either; the offset mimics a frame that
 * arrives half a frame late.
 *
 * The mapping is explicit and tested:
 *     30 fps: render frame n -> n / 30 simulated seconds
 *     60 fps: render frame n -> n / 60 simulated seconds
 */
function simClock (vm, fps = 30) {
    const rt = vm.runtime;
    rt.currentStepTime = 1000 / fps;
    let sim = 0;
    rt.updateCurrentMSecs = function () {
        sim += rt.currentStepTime;
        rt.currentMSecs = sim;
        return sim;
    };
    // Deterministic `timer` / `days since 2000` stand-in for the accumulator.
    let stepsSinceFlag = 0;
    const clock = rt.ioDevices.clock;
    clock.projectTimer = function () {
        return Math.max(0, (stepsSinceFlag - 0.5) / fps);
    };
    const rawStep = rt._step.bind(rt);
    rt._step = function () {
        stepsSinceFlag += 1;
        return rawStep();
    };
    const rawFlag = vm.greenFlag.bind(vm);
    vm.greenFlag = function () {
        stepsSinceFlag = 0;
        return rawFlag();
    };
    return rt;
}

/**
 * Emulate the one thing a WebGL renderer changes about block semantics:
 * `requestRedraw()`.
 *
 * In the browser every visual mutator on `RenderedTarget` ends with
 *
 *     if (this.renderer) { ...; if (this.visible) { ...; this.runtime.requestRedraw(); } }
 *
 * and `Sequencer.stepThreads` keeps re-running threads until either the frame's
 * work-time budget is spent *or* a redraw has been requested. That request is
 * what holds a `forever` loop to one iteration per frame. With no renderer
 * attached the branch is skipped entirely, so the same project would spin
 * hundreds of times per frame headless and behave nothing like it does on
 * scratch.mit.edu.
 *
 * This re-adds the request under exactly the same condition (`visible` and not
 * the stage), and nothing else, so the headless run is throttled the way the
 * real player throttles it.
 */
const REDRAW_METHODS = [
    'setXY', 'setDirection', 'setVisible', 'setSize', 'setEffect',
    'clearEffects', 'setCostume', 'setRotationStyle',
    'updateAllDrawableProperties'
];

function stubRenderer (vm) {
    const proto = vm.runtime.targets[0].constructor.prototype;
    for (const name of REDRAW_METHODS) {
        if (typeof proto[name] !== 'function' || proto[name].__redrawStub) continue;
        const orig = proto[name];
        const wrapped = function (...args) {
            const result = orig.apply(this, args);
            if (!this.isStage && this.visible) this.runtime.requestRedraw();
            return result;
        };
        wrapped.__redrawStub = true;
        proto[name] = wrapped;
    }
    return vm;
}

function press (vm, key, isDown) {
    vm.runtime.ioDevices.keyboard.postData({key: DOM_KEY[key] || key, isDown});
}

/**
 * Every variable on every original (non-clone) target, keyed by name.
 * Stage globals and sprite-locals share one map, so avoid reusing a name
 * across sprites if you rely on this.
 */
function vars (vm) {
    const out = {};
    for (const t of vm.runtime.targets) {
        if (!t.isOriginal) continue;
        for (const id in t.variables) {
            const v = t.variables[id];
            out[v.name] = v.value;
        }
    }
    return out;
}

/**
 * Load an .sb3 and put the VM into the deterministic test configuration:
 * renderer redraws emulated, wall clock simulated at `fps` render frames per
 * simulated second.
 */
async function boot (vm, file, fps = 30) {
    await vm.loadProject(fs.readFileSync(file));
    stubRenderer(vm);
    simClock(vm, fps);
    return vm;
}

module.exports = {STEP_MS, DOM_KEY, makeVM, stubRenderer, simClock, boot, press, vars};
