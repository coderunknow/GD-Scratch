/**
 * Menu / pause / settings conformance test.
 *
 * replay.js proves the physics; this proves the parts of the game a player
 * touches before and between levels. Every case here is a regression test for
 * something that was actually broken while the project was being built:
 *
 *   - the menu highlight not following the selection (variable ID collision),
 *   - arrow presses being swallowed or firing several times (frame pacing),
 *   - LEVEL SELECT falling through and starting level 1 (state read live
 *     inside a chain of ifs),
 *   - P being unable to pause (same fall-through, as two sequential ifs),
 *   - the win screen accepting input before its lock expired.
 *
 *   node menus.js <file.sb3> [--fps N]
 *
 * With --fps the whole scenario runs under a deterministic N-fps render clock
 * (see vmlib.simClock). The death countdown and win input lock are wall-clock
 * paced (42 / 26 physics steps), so at 60 fps they must last twice as many
 * render frames as at 30 fps; the checks below compute their expected render-
 * frame durations from the fps under test.
 */

const {makeVM, boot, press, vars} = require('./vmlib');

const problems = [];
const realError = console.error;
console.error = (...a) => { problems.push(a.map(String).join(' ')); realError(...a); };
console.warn = () => {};

const argList = process.argv.slice(2);
const fpsIdx = argList.indexOf('--fps');
const FPS = fpsIdx !== -1 ? Number(argList[fpsIdx + 1]) : 30;
const file = argList[0];
if (!file) {
    console.log('usage: node menus.js <file.sb3> [--fps N]');
    process.exit(2);
}

let failures = 0;
function check (label, got, want) {
    const ok = String(got) === String(want);
    if (!ok) failures += 1;
    console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}: ${got}` +
                (ok ? '' : ` (wanted ${want})`));
    return ok;
}

async function main () {
    const vm = makeVM();
    await boot(vm, file, FPS);
    const rt = vm.runtime;
    const playedSounds = [];
    const playSound = rt._primitives.sound_play;
    rt._primitives.sound_play = function (args, util) {
        playedSounds.push(String(args.SOUND_MENU));
        return playSound.call(this, args, util);
    };

    // count master-clock invocations so the frame rate itself is under test
    let ticks = 0;
    // optionally capture the jump input the *first* `step play` after arming
    // actually consumed -- this is the only way to observe a stale edge that
    // lives for exactly one step
    let stepPlayCapture = null;
    let captureArm = false;
    const call = rt._primitives.procedures_call;
    rt._primitives.procedures_call = function (args, util) {
        if (args.mutation.proccode === 'tick') ticks += 1;
        if (captureArm && args.mutation.proccode === 'step play') {
            const stg = rt.targets.find(t => t.isStage);
            const gv = n => {
                for (const id in stg.variables) {
                    if (stg.variables[id].name === n) return stg.variables[id].value;
                }
                return undefined;
            };
            stepPlayCapture = {held: gv('held'), jumpEdge: gv('jumpEdge')};
            captureArm = false;
        }
        return call.call(rt._primitives.procedures_call, args, util);
    };

    // count music restarts: the looping music thread calls stop-all-sounds
    // exactly once per `music` broadcast
    let musicRestarts = 0;
    const stopAll = rt._primitives.sound_stopallsounds;
    rt._primitives.sound_stopallsounds = function (args, util) {
        musicRestarts += 1;
        return stopAll.call(this, args, util);
    };

    const stageList = name => {
        const stg = rt.targets.find(t => t.isStage);
        for (const id in stg.variables) {
            const v = stg.variables[id];
            if (v.name === name && v.type === 'list') return v.value;
        }
        return undefined;
    };

    const local = (sprite, name) => {
        for (const t of rt.targets) {
            if (t.sprite.name !== sprite) continue;
            for (const id in t.variables) {
                if (t.variables[id].name === name) return t.variables[id].value;
            }
        }
        return undefined;
    };

    const step = (n = 1) => { for (let i = 0; i < n; i += 1) rt._step(); };
    const tap = key => { press(vm, key, true); step(); press(vm, key, false); step(); };
    const selY = () => local('Sel', 'rowY');

    console.log(`${file.split('/').pop()} @${FPS}fps`);
    vm.greenFlag();
    step(4);

    console.log('title screen');
    check('state after green flag', vars(vm).state, 'menu');
    check('selection starts on PLAY', vars(vm).sel, 1);
    check('PLAY row highlight y', selY(), 30);
    check('menu has four rows', vars(vm).selCount, 4);

    console.log('master clock');
    ticks = 0;
    step(30);
    check('ticks in 30 frames', ticks, 30);

    console.log('menu navigation');
    tap('down arrow');
    check('DOWN moves to LEVEL SELECT', vars(vm).sel, 2);
    check('LEVEL SELECT row highlight y', selY(), -2);
    tap('down arrow');
    check('one press moves exactly one row', vars(vm).sel, 3);
    tap('down arrow');
    check('and again', vars(vm).sel, 4);
    tap('down arrow');
    check('DOWN wraps to the top', vars(vm).sel, 1);
    tap('up arrow');
    check('UP wraps to the bottom', vars(vm).sel, 4);
    tap('up arrow'); tap('up arrow');
    check('two UPs land on LEVEL SELECT', vars(vm).sel, 2);

    console.log('level select');
    tap('space');
    check('LEVEL SELECT opens its own screen', vars(vm).state, 'select');
    check('level select has three rows', vars(vm).selCount, 3);
    check('starts on level 1', vars(vm).sel, 1);
    check('level 1 highlight y', selY(), 64);
    tap('down arrow'); tap('down arrow');
    check('DOWN twice lands on level 3', vars(vm).sel, 3);
    check('level 3 highlight y', selY(), -28);

    console.log('Q backs out of a submenu');
    tap('q');
    check('state', vars(vm).state, 'menu');

    console.log('settings');
    for (let i = 0; i < 3; i += 1) tap('down arrow');   // PLAY -> SETTINGS
    tap('space');
    check('SETTINGS opens', vars(vm).state, 'settings');
    check('music starts on', vars(vm).musicOn, 1);
    check('sfx starts on', vars(vm).sfxOn, 1);
    const selTarget = rt.targets.find(t => t.sprite.name === 'Sel');
    // the settings value pill reaches to stage x=162; only the wide highlight
    // costume covers it (v0.2.1 fix). currentCostume is 0-based.
    check('the highlight switches to the wide costume',
        selTarget.currentCostume, 1);
    for (let i = 0; i < 7; i += 1) tap('down arrow');   // full cycle -> row 1
    check('seven rows: DOWN wraps past BACK to MUSIC', vars(vm).sel, 1);
    tap('space');
    check('row 1 toggles music off', vars(vm).musicOn, 0);
    tap('space');
    check('and back on', vars(vm).musicOn, 1);
    tap('down arrow'); tap('space');
    check('row 2 toggles sfx off', vars(vm).sfxOn, 0);
    tap('space');
    check('row 2 toggles sfx back on', vars(vm).sfxOn, 1);
    tap('down arrow'); tap('space');
    check('row 3 toggles particles off', vars(vm).fxOn, 0);
    tap('space');
    check('row 3 toggles particles back on', vars(vm).fxOn, 1);
    tap('down arrow'); tap('space');
    check('row 4 toggles low latency off', vars(vm).lowLatency, 0);
    tap('space');
    check('row 4 toggles low latency back on', vars(vm).lowLatency, 1);
    tap('down arrow'); tap('space');
    check('row 5 cycles graphics HIGH -> LOW', vars(vm).detail, 1);
    tap('space');
    check('then LOW -> ULTRA', vars(vm).detail, 2);
    tap('space');
    check('then ULTRA -> HIGH', vars(vm).detail, 0);
    tap('down arrow'); tap('space');
    check('row 6 toggles the fps overlay on', vars(vm).showFps, 1);
    tap('space');
    check('and back off', vars(vm).showFps, 0);
    tap('down arrow');
    check('row 7 is BACK', vars(vm).sel, 7);
    tap('space');
    check('BACK returns to the title screen', vars(vm).state, 'menu');
    check('the highlight is narrow again off settings',
        selTarget.currentCostume, 0);
    tap('m');
    check('M toggles music anywhere', vars(vm).musicOn, 0);
    tap('m');
    check('and back', vars(vm).musicOn, 1);

    console.log('how to play');
    tap('down arrow'); tap('down arrow');
    tap('space');
    check('HOW TO PLAY opens', vars(vm).state, 'help');
    tap('space');
    check('and closes back to the title screen', vars(vm).state, 'menu');

    console.log('pause');
    tap('space');                                       // PLAY -> level 1
    check('level started', vars(vm).state, 'play');
    tap('r');                                           // deterministic grounded spawn
    step(2);
    const jumpSoundsBefore = playedSounds.filter(name => name === 'sfx jump').length;
    tap('space');                                       // fresh grounded jump press
    step(2);
    check('a grounded jump plays its SFX',
        playedSounds.filter(name => name === 'sfx jump').length > jumpSoundsBefore,
        true);
    step(10);
    tap('p');
    check('P pauses', vars(vm).state, 'pause');
    // The master clock and the key hat are separate threads, so the level may
    // have taken one last step on the frame P landed. Compare from here.
    const frameAtPause = Number(vars(vm).frame);
    step(20);
    check('the clock stops stepping the level', vars(vm).frame, frameAtPause);
    tap('down arrow');
    check('the pause menu navigates', vars(vm).sel, 2);
    tap('up arrow');
    check('and back', vars(vm).sel, 1);
    tap('space');
    check('RESUME returns to play', vars(vm).state, 'play');
    step(4);
    check('and the level runs again',
        Number(vars(vm).frame) > frameAtPause, true);
    tap('p');
    check('P pauses again', vars(vm).state, 'pause');
    tap('p');
    check('and P resumes again', vars(vm).state, 'play');

    console.log('restart');
    step(5);
    tap('r');
    // the clock is already running again by the time we look, so allow the
    // frame or two that elapsed between the restart and the check
    check('R restarts the level', Number(vars(vm).frame) <= 2, true);
    check('attempt counter increments', Number(vars(vm).attempt) >= 2, true);

    console.log('pause/resume input hygiene');
    step(4);
    tap('p');
    check('P pauses (hygiene setup)', vars(vm).state, 'pause');
    step(3);                          // the P press/release settles
    stepPlayCapture = null;
    captureArm = true;
    tap('space');                     // resume with the same key that jumps
    check('space resumes from pause', vars(vm).state, 'play');
    // at 60 fps the resume frame may run no physics step; wait for the first
    // one so the capture always reflects the step that resumed play
    for (let i = 0; i < 10 && stepPlayCapture === null; i += 1) step();
    captureArm = false;
    check(`the first play step after resume saw no jump input ` +
          `(got ${JSON.stringify(stepPlayCapture)})`,
          stepPlayCapture !== null &&
          Number(stepPlayCapture.held) === 0 &&
          Number(stepPlayCapture.jumpEdge) === 0,
          true);
    step(3);
    check(`the cube did not jump on resume ` +
          `(py=${vars(vm).py} grounded=${vars(vm).grounded})`,
          Number(vars(vm).py) === -105 && Number(vars(vm).grounded) === 1,
          true);

    tap('p');
    check('P pauses again (mouse setup)', vars(vm).state, 'pause');
    step(2);
    rt.ioDevices.mouse.postData({isDown: true, x: 0, y: 0});
    step();
    rt.ioDevices.mouse.postData({isDown: false, x: 0, y: 0});
    check('a mouse click activates the pause RESUME row', vars(vm).state, 'play');

    console.log('keys during death');
    for (let i = 0; i < 200 && vars(vm).state === 'play'; i += 1) step();
    check('the cube died', vars(vm).state, 'dead');
    const bestsBefore = stageList('BESTS');
    tap('p');
    check('P is ignored while dead', vars(vm).state, 'dead');
    tap('r');
    step(2);
    check('R during death restarts at once', vars(vm).state, 'play');
    check(`the death recorded a best progress (BESTS[1]=${bestsBefore[0]})`,
          Number(bestsBefore[0]) > 0, true);

    console.log('music restarts with the level');
    const restartsBefore = musicRestarts;
    tap('r');
    step(6);
    check(`restarting the level restarts the music ` +
          `(${restartsBefore} -> ${musicRestarts})`,
          musicRestarts > restartsBefore, true);

    // --- helpers for navigating settings from inside a run ---------------
    // note: scratch-vm has no isClone property here; isOriginal is the flag
    const clonesOf = name =>
        rt.targets.filter(t => t.sprite.name === name && !t.isOriginal).length;
    const menuRow = row => {            // title only: land on menu row
        const downs = (row - Number(vars(vm).sel) + 4) % 4;
        for (let i = 0; i < downs; i += 1) tap('down arrow');
    };
    const quitToTitle = () => {         // play -> pause -> QUIT
        tap('p');
        tap('down arrow'); tap('down arrow');               // row 3 QUIT
        tap('space');
        check('Q via pause menu returns to the title', vars(vm).state, 'menu');
    };
    const setSetting = (row, presses) => {   // title -> settings row -> title
        menuRow(4);
        tap('space');                        // open SETTINGS
        check(`SETTINGS opened for row ${row}`, vars(vm).state, 'settings');
        const downs = (row - Number(vars(vm).sel) + 7) % 7;
        for (let i = 0; i < downs; i += 1) tap('down arrow');
        for (let i = 0; i < presses; i += 1) tap('space');
        for (let i = 0; i < (7 - row) % 7; i += 1) tap('down arrow');
        tap('space');                        // BACK
        check(`settings row ${row} set, back at the title`,
            vars(vm).state, 'menu');
    };
    const freshRun = () => {            // title -> level 1, grounded
        menuRow(1);
        tap('space');
        check('level 1 running (fresh run)', vars(vm).state, 'play');
        step(3);
    };

    console.log('graphics settings apply to the live level');
    quitToTitle();
    setSetting(5, 1);                   // GRAPHICS HIGH -> LOW
    freshRun();
    step(8);
    check('GRAPHICS LOW retires the parallax clones', clonesOf('Far'), 0);
    quitToTitle();
    setSetting(5, 2);                   // LOW -> HIGH (two presses)
    freshRun();
    step(8);
    check('GRAPHICS HIGH keeps both parallax clones', clonesOf('Far'), 2);
    quitToTitle();
    setSetting(5, 2);                   // HIGH -> ULTRA (two presses)
    freshRun();
    for (let i = 0; i < 120 && vars(vm).state === 'play'; i += 1) step();
    step(2);
    check('the cube died (ULTRA particle setup)', vars(vm).state, 'dead');
    check('ULTRA draws no particles at all', clonesOf('FX'), 0);
    tap('r');                           // leave the death screen first
    step(2);
    quitToTitle();
    setSetting(5, 1);                   // ULTRA -> HIGH
    freshRun();
    for (let i = 0; i < 120 && vars(vm).state === 'play'; i += 1) step();
    step(2);
    check('the cube died (HIGH particle setup)', vars(vm).state, 'dead');
    check('HIGH draws the full burst', clonesOf('FX') > 0, true);
    tap('r');                           // leave the death screen
    step(2);

    console.log('the fps overlay');
    quitToTitle();
    setSetting(6, 1);                   // SHOW FPS on
    freshRun();
    step(20);                           // > the 0.5 s meter window
    const txtch = stageList('TXTCH');
    const overlay = txtch.slice(48, 54).join('').trim();
    check(`the overlay reads "${overlay}"`,
          overlay.startsWith('FPS '), true);
    quitToTitle();

    console.log('low latency input semantics');
    setSetting(4, 1);                   // LOW LATENCY off
    freshRun();
    {
        // find a render frame that runs no physics step (only exists above
        // 30 fps); the frame after it steps, so idle frames recur every
        // second frame from there on
        let idleFound = false;
        for (let g = 0; g < 6 && !idleFound; g += 1) {
            const f = Number(vars(vm).frame);
            step();
            idleFound = Number(vars(vm).frame) === f;
        }
        const py0 = Number(vars(vm).py);
        if (idleFound) {
            step();                     // burn the stepping frame; next idles
            press(vm, 'space', true); step(); press(vm, 'space', false);
            step(2);
            check('LOW LATENCY off drops a tap made between steps',
                Number(vars(vm).py) === py0 &&
                Number(vars(vm).grounded) === 1, true);
        } else {
            // 30 fps: every frame steps; a spanning tap must still jump
            tap('space'); step(2);
            check('LOW LATENCY off keeps 30 Hz sampling semantics',
                Number(vars(vm).py) > py0, true);
        }
    }
    quitToTitle();
    setSetting(4, 1);                   // toggle back on
    freshRun();
    {
        let idleFound = false;
        for (let g = 0; g < 6 && !idleFound; g += 1) {
            const f = Number(vars(vm).frame);
            step();
            idleFound = Number(vars(vm).frame) === f;
        }
        const py0 = Number(vars(vm).py);
        if (idleFound) {
            step();                     // burn the stepping frame; next idles
            press(vm, 'space', true); step(); press(vm, 'space', false);
            let jumped = false;
            for (let i = 0; i < 3; i += 1) {
                step();
                if (Number(vars(vm).py) > py0) { jumped = true; break; }
            }
            check('LOW LATENCY on consumes the same tap exactly once',
                jumped, true);
        } else {
            tap('space'); step(2);
            check('LOW LATENCY on jumps (30 fps)',
                Number(vars(vm).py) > py0, true);
        }
    }

    console.log('Q mid-level');
    step(5);
    tap('q');
    check('Q returns to the title screen', vars(vm).state, 'menu');

    console.log('win screen input lock');
    tap('space');                                       // back into level 1
    step(4);
    // jump straight to the win screen through the same procedure the level uses
    const stage = rt.targets.find(t => t.isStage);
    const setV = (n, val) => {
        for (const id in stage.variables) {
            if (stage.variables[id].name === n) { stage.variables[id].value = val; return; }
        }
    };
    setV('state', 'win'); setV('winT', 26); setV('sel', 1); setV('selCount', 3);
    step(2);
    tap('r');
    check('R is ignored on the win screen', vars(vm).state, 'win');
    tap('space');
    check('input is ignored while winT is running', vars(vm).state, 'win');
    // The lock is paced in physics steps: measure how many render frames the
    // remaining lock takes and require it to scale with the frame rate.
    const lockStart = Number(vars(vm).winT);
    let lockFrames = 0;
    for (let i = 0; i < 200 && Number(vars(vm).winT) >= 1; i += 1) { step(); lockFrames += 1; }
    const wantLock = Math.round(lockStart * FPS / 30);
    check(`the win lock lasts ~${wantLock} render frames at ${FPS} fps ` +
          `(${lockFrames} observed)`,
          Math.abs(lockFrames - wantLock) <= 2, true);
    tap('space');
    check('and accepted once it expires', vars(vm).state !== 'win', true);

    console.log('death countdown pacing');
    // Level 1 is open again after the win screen advanced to level 2 -- go
    // back to level 1 through the level select so the first spike is known.
    vm.greenFlag();
    step(4);
    tap('space');                                       // PLAY
    check('level 1 running', vars(vm).state, 'play');
    // no input at all: the cube hits the first spike and dies
    let deathFrames = -1;
    let restartFrames = -1;
    let seen = 0;
    for (let i = 0; i < 400; i += 1) {
        step();
        const st = vars(vm).state;
        if (st === 'dead' && deathFrames < 0) deathFrames = seen;
        if (st !== 'dead' && deathFrames >= 0) { restartFrames = seen; break; }
        seen += 1;
    }
    check('the cube died on the first spike', deathFrames >= 0, true);
    // 42 physics steps of countdown: 42 * FPS/30 render frames (+/- 2 for the
    // frame the death landed on)
    const wantDead = Math.round(42 * FPS / 30);
    const deadSpan = restartFrames >= 0 ? restartFrames - deathFrames : -1;
    check(`the death countdown lasts ~${wantDead} render frames at ${FPS} fps`,
          Math.abs(deadSpan - wantDead) <= 2, true);
    check('the level auto-restarted', vars(vm).state, 'play');

    console.log('mouse activation');
    vm.greenFlag();
    step(4);
    rt.ioDevices.mouse.postData({isDown: true, x: 0, y: 0});
    step();
    rt.ioDevices.mouse.postData({isDown: false, x: 0, y: 0});
    check('a click on PLAY starts level 1', vars(vm).state, 'play');

    if (problems.length) {
        console.log('vm errors:');
        for (const p of problems.slice(0, 5)) console.log(`  ${p}`);
        failures += 1;
    }

    console.log(failures === 0 ? '\nPASS: menus, pause and settings all behave'
        : `\nFAIL: ${failures} check(s) failed`);
    process.exit(failures === 0 ? 0 : 1);
}

main().catch(err => {
    console.error('menus.js crashed:', err && err.stack ? err.stack : err);
    process.exit(1);
});
