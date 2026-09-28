/**
 * Replay a Python-solved input schedule inside the real scratch-vm and prove
 * the generated game reproduces the reference physics exactly -- at any render
 * rate.
 *
 *   node replay.js <file.sb3> <fixture.json> [--fps N] [--verbose]
 *
 * The fixture comes from tools/verify_levels.py and contains the per-physics-
 * step hold schedule plus the y/vy/grounded trace that gdscratch.verify
 * produced. Every physics step is compared bit-for-bit; a single mismatch
 * fails the run.
 *
 * Without --fps the runner executes every fixture twice, under a deterministic
 * 30 fps clock and a deterministic 60 fps clock (see vmlib.simClock), and then
 * asserts the pacing invariants:
 *
 *   physics trace = simulation invariant
 *     - identical to the Python reference, step for step, at both rates
 *     - identical between the 30 fps and 60 fps runs
 *     - the same number of physics steps at both rates
 *     - no skipped step, no duplicated step, ordering preserved
 *       (every recorded step index appears exactly once, +1 each time)
 *   render trace = presentation cadence
 *     - the 60 fps run takes exactly twice as many render frames as the
 *       30 fps run for the same simulated duration / physics-step count
 *     - at 30 fps every render frame runs exactly one physics step; at 60 fps
 *       a render frame runs at most one, and exactly every other one does
 *
 * A transient-tap scenario additionally proves input latching: a key press
 * held for exactly one render frame that spans *no* physics step must still be
 * consumed -- exactly once -- by the next physics step, identically at both
 * render rates.
 *
 * Exits 0 when everything replays identically and ends in the expected event,
 * 1 otherwise.
 */

const fs = require('fs');
const {makeVM, boot, press, vars} = require('./vmlib');

const verbose = process.argv.includes('--verbose');
const args = process.argv.slice(2).filter(a => a !== '--verbose');
const fpsIdx = args.indexOf('--fps');
const onlyFps = fpsIdx !== -1 ? Number(args[fpsIdx + 1]) : null;
if (onlyFps !== null) {
    args.splice(fpsIdx, 2);
}
const [file, fixturePath] = args;

if (!file || !fixturePath) {
    console.log('usage: node replay.js <file.sb3> <fixture.json> [--fps N] [--verbose]');
    process.exit(2);
}

const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
const problems = [];
const realError = console.error;
console.error = (...a) => { problems.push(a.map(String).join(' ')); realError(...a); };

const failures = [];
const fail = msg => { failures.push(msg); console.log(`FAIL: ${msg}`); };
const JUMP_VY = 27 - 3.8;   // JUMP_V - GRAVITY: the vy a grounded jump step reports

/**
 * Drive the real menus with real keys until `level` is running, exactly as a
 * player would. Returns after the activating press has been released; the
 * replay loop owns the clock from the next render frame on.
 */
async function startLevel (vm, file, level, fps) {
    await boot(vm, file, fps);
    vm.greenFlag();

    // let setup finish and the glyph pool spawn
    for (let i = 0; i < 4; i += 1) vm.runtime._step();
    let v = vars(vm);
    if (v.state !== 'menu') {
        throw new Error(`expected state "menu" after setup, got "${v.state}"`);
    }

    const tap = key => {
        press(vm, key, true);
        vm.runtime._step();
        press(vm, key, false);
        vm.runtime._step();
    };
    tap('down arrow');                                  // PLAY -> LEVEL SELECT
    v = vars(vm);
    if (Number(v.sel) !== 2) {
        throw new Error(`first DOWN left the menu on sel=${v.sel}, wanted 2`);
    }
    tap('space');                                       // -> level select screen
    v = vars(vm);
    if (v.state !== 'select') {
        throw new Error(`LEVEL SELECT did not open (state=${v.state})`);
    }
    for (let i = 1; i < level; i += 1) tap('down arrow');
    v = vars(vm);
    if (Number(v.sel) !== level) {
        throw new Error(`level select landed on sel=${v.sel}, wanted ${level}`);
    }
    // One press, one frame, then release: the replay loop below owns the clock
    // from the very next frame.
    press(vm, 'space', true);
    vm.runtime._step();
    press(vm, 'space', false);
    v = vars(vm);
    if (v.state !== 'play' || Number(v.level) !== level) {
        throw new Error(`activating level ${level} did not start it ` +
                        `(state=${v.state}, level=${v.level})`);
    }
}

/**
 * Replay the fixture's hold schedule at one render rate.
 *
 * The schedule is indexed by *physics step*. Each render frame the driver
 * presses/releases space so that the next due physics step observes
 * holds[nextStep]; a frame that runs no physics step simply holds the key for
 * the step that will run later (that is exactly the render-rate capture the
 * game must latch).
 *
 * Records one physics-trace row per executed step (ordered), plus per-render-
 * frame step counts.
 */
async function replayAtRate (file, level, fps) {
    const vm = makeVM();
    await startLevel(vm, file, level, fps);
    const rt = vm.runtime;

    const holds = fixture.holds;
    const trace = fixture.trace;
    const physicsRows = [];          // one per physics step, in order
    const perFrameSteps = [];        // physics steps executed per render frame
    let mismatches = 0;
    let firstBad = null;
    let endState = null;
    let renderFrames = 0;

    let nextStep = 0;                // index of the next physics step to run
    let lastFrame = 0;
    while (nextStep < holds.length) {
        press(vm, 'space', holds[nextStep] === 1);
        rt._step();
        renderFrames += 1;
        const v = vars(vm);
        const frame = Number(v.frame);
        const ran = frame - lastFrame;
        perFrameSteps.push(ran);
        if (ran > 0) {
            // physics steps must never be skipped or duplicated: the frame
            // counter must advance by exactly one per recorded step
            if (ran !== 1) {
                fail(`level ${level} @${fps}fps: render frame ran ${ran} ` +
                     `physics steps (frame ${lastFrame} -> ${frame})`);
            } else {
                const got = {f: frame, y: Number(v.py), vy: Number(v.vy),
                             grav: Number(v.grav), grounded: Number(v.grounded)};
                const want = trace[frame];
                const ok = want && got.f === want.f && got.y === want.y &&
                    got.vy === want.vy && got.grav === want.grav &&
                    got.grounded === want.grounded;
                if (!ok && mismatches === 0) firstBad = {got, want};
                if (!ok) mismatches += 1;
                physicsRows.push(got);
            }
            lastFrame = frame;
            nextStep = frame;
        }
        if (v.state !== 'play') { endState = v.state; break; }
    }
    press(vm, 'space', false);
    if (endState === null) {
        rt._step();
        renderFrames += 1;
        endState = vars(vm).state;
    }
    const finalVars = vars(vm);
    if (verbose) {
        console.log(`  @${fps}fps: ${nextStep} steps in ${renderFrames} render frames, ` +
            `${mismatches} mismatches, end=${endState}`);
    }
    return {fps, physicsRows, perFrameSteps, mismatches, firstBad, endState,
            renderFrames, steps: nextStep,
            finalProgress: Number(finalVars.prog),
            coinsCollected: Number(finalVars.coins)};
}

/**
 * Transient-tap scenario: start level 1, run a few idle steps, then hold space
 * for exactly one render frame that spans no physics step (proven: the frame
 * counter must not advance while the key is down), release, and verify the
 * next physics step consumes the tap exactly once. The resulting physics
 * trace must be identical at 30 fps and 60 fps.
 */
async function tapScenario (file, fps) {
    const vm = makeVM();
    await startLevel(vm, file, 1, fps);
    const rt = vm.runtime;

    const rows = [];
    let lastF = 0;
    const record = () => {
        const v = vars(vm);
        if (v.state !== 'play') throw new Error(`left play @${fps}fps (state=${v.state})`);
        const f = Number(v.frame);
        if (f > lastF) {
            rows.push({f, y: Number(v.py), vy: Number(v.vy),
                       grounded: Number(v.grounded)});
            lastF = f;
        }
    };
    const stepOnce = () => { rt._step(); record(); };

    // run to physics step 12 with no input
    while (lastF < 12) stepOnce();
    // The frame just run executed a step, so the next render frame is a
    // no-step frame at 60 fps (a plain frame at 30 fps). Tap now: press for
    // exactly this one render frame and release before any further step.
    press(vm, 'space', true);
    stepOnce();
    const frameWhileDown = lastF;
    press(vm, 'space', false);
    stepOnce();
    if (fps === 60 && frameWhileDown !== 12) {
        fail(`tap @60fps: the 1-render-frame press already ran a physics step ` +
             `(frame ${frameWhileDown}); the scenario no longer spans no step`);
    }
    // run on to physics step 33 (render frames are the wrong unit here: at
    // 60 fps they are not 1:1 with steps)
    while (lastF < 33) stepOnce();
    const jumpSteps = rows.filter(r => r.grounded === 0 && r.vy === JUMP_VY);
    return {rows, jumpSteps, frameWhileDown};
}

async function main () {
    const level = fixture.level;
    const rates = onlyFps ? [onlyFps] : [30, 60];
    const runs = [];
    for (const fps of rates) {
        try {
            runs.push(await replayAtRate(file, level, fps));
        } catch (e) {
            fail(`level ${level} @${fps}fps crashed: ${e.message}`);
        }
    }
    if (runs.length === rates.length) {
        for (const run of runs) {
            if (run.mismatches !== 0) {
                fail(`level ${level} @${run.fps}fps does not match the Python ` +
                     `reference: ${run.mismatches} mismatched steps ` +
                     `(first: step ${run.firstBad && run.firstBad.got.f} ` +
                     `got y=${run.firstBad && run.firstBad.got.y} ` +
                     `want y=${run.firstBad && run.firstBad.want && run.firstBad.want.y})`);
            }
            if (run.endState !== fixture.expectedEvent) {
                fail(`level ${level} @${run.fps}fps ended "${run.endState}", ` +
                     `expected "${fixture.expectedEvent}"`);
            }
            // no skipped / duplicated steps: physics trace rows must be
            // consecutive integers starting at 1
            for (let i = 0; i < run.physicsRows.length; i += 1) {
                if (run.physicsRows[i].f !== i + 1) {
                    fail(`level ${level} @${run.fps}fps: physics step ordering ` +
                         `broken at row ${i} (frame ${run.physicsRows[i].f})`);
                    break;
                }
            }
            if (run.steps !== fixture.frames) {
                fail(`level ${level} @${run.fps}fps ran ${run.steps} physics ` +
                     `steps, reference took ${fixture.frames}`);
            }
        }
        if (runs.length === 2) {
            const [r30, r60] = runs;
            // physics trace is the simulation invariant: identical across rates
            if (JSON.stringify(r30.physicsRows) !== JSON.stringify(r60.physicsRows)) {
                fail(`level ${level}: 30 fps and 60 fps physics traces differ ` +
                     `(simulation must be render-rate independent)`);
            }
            if (r30.steps !== r60.steps) {
                fail(`level ${level}: step count differs across render rates ` +
                     `(${r30.steps} vs ${r60.steps})`);
            }
            // render trace is presentation cadence: 60 fps must spend exactly
            // twice as many render frames for the same simulated duration
            if (r60.renderFrames !== 2 * r30.renderFrames) {
                fail(`level ${level}: render frames 30fps=${r30.renderFrames} ` +
                     `60fps=${r60.renderFrames} (wanted exactly ` +
                     `${2 * r30.renderFrames}; a 60 fps run that does not take ` +
                     `twice the frames runs the simulation at the wrong speed)`);
            }
            // at 60 fps exactly every other render frame executes a step
            const stepFrames60 = r60.perFrameSteps.filter(n => n > 0).length;
            if (stepFrames60 !== r60.renderFrames / 2) {
                fail(`level ${level} @60fps: ${stepFrames60} of ` +
                     `${r60.renderFrames} render frames ran a physics step ` +
                     `(wanted exactly half)`);
            }
        }
    }

    // transient-tap latching coverage (level 1 flat start, both rates)
    if (!onlyFps || onlyFps === 30 || onlyFps === 60) {
        try {
            const tap30 = await tapScenario(file, 30);
            const tap60 = await tapScenario(file, 60);
            if (tap30.jumpSteps.length !== 1 || tap60.jumpSteps.length !== 1) {
                fail(`tap scenario: expected exactly one jump step, got ` +
                     `30fps=${tap30.jumpSteps.length} 60fps=${tap60.jumpSteps.length} ` +
                     `(a latched tap must be consumed exactly once)`);
            } else if (JSON.stringify(tap30.rows) !== JSON.stringify(tap60.rows)) {
                fail(`tap scenario: physics traces differ between 30 fps and ` +
                     `60 fps (transient tap was lost or duplicated)`);
            } else {
                if (verbose) {
                    console.log(`  tap consumed at step ${tap60.jumpSteps[0].f} ` +
                        `identically at both rates`);
                }
            }
        } catch (e) {
            fail(`tap scenario crashed: ${e.message}`);
        }
    }

    const report = {
        file: file.split('/').pop(),
        level,
        name: fixture.name,
        rates: runs.map(r => ({fps: r.fps, physicsSteps: r.steps,
                               renderFrames: r.renderFrames,
                               mismatches: r.mismatches, endState: r.endState})),
        expectedEvent: fixture.expectedEvent,
        finalProgress: runs.length ? runs[0].finalProgress : null,
        coinsCollected: runs.length ? runs[0].coinsCollected : null,
        coinsInLevel: fixture.coinsInLevel
    };
    if (problems.length) report.vmErrors = problems.slice(0, 5);
    console.log(JSON.stringify(report, null, 2));

    if (failures.length || problems.length) {
        console.log(`FAIL: ${fixture.name} did not replay identically at all rates`);
        process.exit(1);
    }
    const ratesTxt = runs.map(r => `${r.fps}fps:${r.steps}steps/${r.renderFrames}frames`)
        .join(', ');
    console.log(`PASS: ${fixture.name} -- physics identical to reference and ` +
                `across rates (${ratesTxt}), ended "${runs[0] && runs[0].endState}"`);
}

main().catch(err => {
    console.error('replay crashed:', err);
    process.exit(1);
});
