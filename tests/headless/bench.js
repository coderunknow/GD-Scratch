/**
 * Repeatable benchmark + work-counter for the generated project.
 *
 *   node bench.js <file.sb3> [--json] [--runs N] [--only scenario]
 *
 * Two passes per scenario, because they measure different things and one
 * pollutes the other:
 *
 *   plain pass        wall-clock ms per `_step()`  (no instrumentation)
 *   counting pass     every primitive call, tallied per opcode, plus redraw
 *                     requests and the live target count at the end of each
 *                     frame
 *
 * Wall-clock in a sandboxed container is noisy, so each plain pass reports the
 * median of its per-frame samples as well as the mean and p95. The pass is
 * repeated `--runs` times; the report uses the median of run medians rather
 * than selecting the luckiest run. Opcode tallies are exact and
 * machine-independent, which makes them useful when timing wobbles.
 *
 * Scenarios use the same deterministic inputs as replay.js (the Python solver's
 * schedule), so two builds are always compared on identical work.
 */

const fs = require('fs');
const path = require('path');
const {makeVM, boot, press, vars} = require('./vmlib');

// scratch-vm's minilog writes its warnings to the console, which would land in
// the middle of the JSON report. Capture them instead; genuine VM errors are
// reported in the JSON, the "no rendering module" chatter is dropped.
const vmProblems = [];
const vmWarnings = [];
const real = {log: console.log, info: console.info, warn: console.warn};
const mute = () => {
    console.log = () => {};
    console.info = () => {};
};
const unmute = () => {
    console.log = real.log;
    console.info = real.info;
};
console.warn = (...a) => { vmWarnings.push(a.map(String).join(' ')); };
console.error = (...a) => { vmProblems.push(a.map(String).join(' ')); };
mute();

const args = process.argv.slice(2);
const file = args.find(a => !a.startsWith('--'));
const only = (() => {
    const i = args.indexOf('--only');
    return i === -1 ? null : args[i + 1];
})();
const runs = (() => {
    const i = args.indexOf('--runs');
    return i === -1 ? 3 : Number(args[i + 1]);
})();

if (!file) {
    console.log('usage: node bench.js <file.sb3> [--json] [--runs N] [--only name]');
    process.exit(2);
}

const FIXTURES = path.join(__dirname, '..', 'fixtures');
const fixture = level => JSON.parse(
    fs.readFileSync(path.join(FIXTURES, `level${level}_solution.json`), 'utf8'));

function instrument (vm) {
    const rt = vm.runtime;
    const counts = Object.create(null);
    let redraws = 0;
    const origRedraw = rt.requestRedraw;
    rt.requestRedraw = function (...a) { redraws += 1; return origRedraw.apply(this, a); };

    const originals = new Map();
    for (const opcode in rt._primitives) {
        const fn = rt._primitives[opcode];
        if (typeof fn !== 'function') continue;
        originals.set(opcode, fn);
        rt._primitives[opcode] = function (...a) {
            counts[opcode] = (counts[opcode] || 0) + 1;
            return fn.apply(this, a);
        };
    }
    // procedures_call is dispatched through the same table, so custom-block
    // bodies are already covered.
    return {
        snapshot () {
            return {opcodes: counts, redraws};
        },
        reset () {
            for (const k in counts) delete counts[k];
            redraws = 0;
        },
        restore () {
            for (const [opcode, fn] of originals) rt._primitives[opcode] = fn;
            rt.requestRedraw = origRedraw;
        }
    };
}

function stats (samples) {
    if (!samples.length) return {};
    const sorted = [...samples].sort((a, b) => a - b);
    const at = q => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))];
    const sum = sorted.reduce((a, b) => a + b, 0);
    return {
        frames: sorted.length,
        meanMs: +(sum / sorted.length).toFixed(3),
        medianMs: +at(0.5).toFixed(3),
        p95Ms: +at(0.95).toFixed(3),
        maxMs: +at(1).toFixed(3)
    };
}

function median (values) {
    const sorted = [...values].sort((a, b) => a - b);
    if (!sorted.length) return null;
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** Drive the menus with real keys to start `level`, exactly like replay.js. */
function enterLevel (vm, level, activate = true) {
    const rt = vm.runtime;
    vm.greenFlag();
    for (let i = 0; i < 4; i += 1) rt._step();
    const tap = key => {
        press(vm, key, true); rt._step();
        press(vm, key, false); rt._step();
    };
    tap('down arrow');                 // PLAY -> LEVEL SELECT
    tap('space');                      // open the level list
    for (let i = 1; i < level; i += 1) tap('down arrow');
    if (activate) {
        press(vm, 'space', true);
        rt._step();
        press(vm, 'space', false);
    }
}

// --- scenarios -------------------------------------------------------------

const SCENARIOS = {
    /** Idle title screen: what a player costs by simply being there. */
    menu_idle (vm) {
        const rt = vm.runtime;
        vm.greenFlag();
        for (let i = 0; i < 30; i += 1) rt._step();   // glyph pool settles
        return {frames: 60, step: () => rt._step()};
    },

    /** A full solved run of a level, minus the driving keystrokes. */
    level1_replay (vm) {
        enterLevel(vm, 1, false);
        const fx = fixture(1);
        return {_replay: vm, _level: 1, _holds: fx.holds};
    },

    level3_replay (vm) {
        enterLevel(vm, 3, false);
        const fx = fixture(3);
        return {_replay: vm, _level: 3, _holds: fx.holds};
    },

    /** Level 1 with GRAPHICS=LOW: the cheap-cosmetics preset players on
     *  weak devices would pick (far parallax hidden, half particles). */
    level1_detail_low (vm) {
        enterLevel(vm, 1, false);
        const rt = vm.runtime;
        const stage = rt.targets.find(t => t.isStage);
        for (const id in stage.variables) {
            if (stage.variables[id].name === 'detail') {
                stage.variables[id].value = 1;
            }
        }
        const fx = fixture(1);
        return {_replay: vm, _level: 1, _holds: fx.holds};
    },

    /** Restart spam: the most common thing a player does after a death. */
    stress_restart (vm) {
        enterLevel(vm, 1);
        const rt = vm.runtime;
        let i = 0;
        return {
            frames: 30 * 20,
            step () {
                if (i % 30 === 0) press(vm, 'r', true);
                if (i % 30 === 1) press(vm, 'r', false);
                rt._step();
                i += 1;
            }
        };
    },

    /** Deliberate deaths, then the automatic restart. */
    death_cycle (vm) {
        enterLevel(vm, 1);
        const rt = vm.runtime;
        const total = 12 * 60;
        let i = 0;
        return {
            frames: total,
            step () {
                // no input at all: the cube runs into the first spike and dies,
                // the game restarts it and it dies again
                rt._step();
                i += 1;
            }
        };
    },

    /** Pause/resume churn. */
    pause_cycle (vm) {
        enterLevel(vm, 1);
        const rt = vm.runtime;
        let i = 0;
        return {
            frames: 20 * 12,
            step () {
                if (i % 12 === 0) press(vm, 'p', true);
                if (i % 12 === 1) press(vm, 'p', false);
                rt._step();
                i += 1;
            }
        };
    },

    /** Back to the title screen: are the clones from the level gone? */
    menu_return (vm) {
        enterLevel(vm, 1);
        const rt = vm.runtime;
        for (let i = 0; i < 120; i += 1) rt._step();
        press(vm, 'q', true); rt._step(); press(vm, 'q', false);
        for (let i = 0; i < 30; i += 1) rt._step();
        return {frames: 60, step: () => rt._step()};
    }
};

// --- runner ----------------------------------------------------------------

async function runScenario (name, {count}) {
    const vm = makeVM();
    await boot(vm, file);
    const rt = vm.runtime;
    // Instrument *before* the flag: scratch-vm caches the primitive function on
    // each block the first time that block executes (BlockCached.initialize ->
    // runtime.getOpcodeFunction), so a wrapper installed later would be ignored
    // by every block that had already run.
    const inst = count ? instrument(vm) : null;
    const setup = SCENARIOS[name](vm);
    if (inst) inst.reset(); // exclude project boot/menu navigation from measured work
    const samples = [];
    const totals = Object.create(null);
    let redraws = 0;
    let frames = 0;
    let maxTargets = 0;
    let maxClones = 0;
    const bySpriteMax = {};
    let last = null;
    let endState = vars(vm).state;

    const observe = () => {
        const targets = rt.targets.length;
        let clones = 0;
        for (const t of rt.targets) {
            if (!t.isOriginal) clones += 1;
            bySpriteMax[t.sprite.name] = (bySpriteMax[t.sprite.name] || 0) + 0;
        }
        maxTargets = Math.max(maxTargets, targets);
        maxClones = Math.max(maxClones, clones);
        // per-sprite live counts (originals + their clones)
        const live = Object.create(null);
        for (const t of rt.targets) {
            live[t.sprite.name] = (live[t.sprite.name] || 0) + 1;
        }
        for (const k in live) {
            bySpriteMax[k] = Math.max(bySpriteMax[k] || 0, live[k]);
        }
        last = {targets, clones};
    };

    const drive = step => {
        frames += 1;
        const t0 = process.hrtime.bigint();
        step();
        endState = vars(vm).state;
        const dt = Number(process.hrtime.bigint() - t0) / 1e6;
        if (!inst) samples.push(dt);
        else {
            const snap = inst.snapshot();
            for (const k in snap.opcodes) totals[k] = (totals[k] || 0) + snap.opcodes[k];
            redraws += snap.redraws;
            inst.reset();
        }
        observe();
    };

    if (setup && setup._replay) {
        const fx = fixture(setup._level);
        press(vm, 'space', true); rt._step();
        press(vm, 'space', false);
        for (let i = 0; i < fx.holds.length; i += 1) {
            press(vm, 'space', fx.holds[i] === 1);
            drive(() => rt._step());
            endState = vars(vm).state;
            if (endState !== 'play') break;
        }
        press(vm, 'space', false);
    } else {
        for (let i = 0; i < setup.frames; i += 1) drive(setup.step);
    }
    if (setup && setup._replay) {
        const expected = fixture(setup._level);
        if (frames !== expected.holds.length || endState !== expected.expectedEvent) {
            throw new Error(`${name}: replay ended ${endState} after ${frames} steps; ` +
                `expected ${expected.expectedEvent} after ${expected.holds.length}`);
        }
    }

    const out = {scenario: name, frames, maxTargets, maxClones, endState,
                 targetsEnd: last ? last.targets : 0, bySpriteMax,
                 ...stats(samples)};
    if (inst) {
        out.opcodeTotals = totals;
        out.opcodesPerFrame = {};
        for (const [opcode, n] of Object.entries(totals)) {
            out.opcodesPerFrame[opcode] = +(n / Math.max(1, frames)).toFixed(2);
        }
        out.workPerFrame = +(Object.values(totals).reduce((a, b) => a + b, 0) /
            Math.max(1, frames)).toFixed(1);
        out.redrawsPerFrame = +(redraws / Math.max(1, frames)).toFixed(2);
        inst.restore();
    }
    return out;
}

async function main () {
    const names = only ? [only] : Object.keys(SCENARIOS);
    const report = {file: path.basename(file), sizeKB: Math.round(fs.statSync(file).size / 1024),
                    runs, scenarios: {}};
    for (const name of names) {
        const timed = [];
        for (let r = 0; r < runs; r += 1) {
            const res = await runScenario(name, {count: false});
            timed.push(res);
        }
        const best = timed.reduce((a, b) => (a.medianMs <= b.medianMs ? a : b));
        const res = await runScenario(name, {count: true});
        report.scenarios[name] = {
            frames: best.frames,
            // Median-of-run medians avoids choosing the luckiest timing run.
            medianMs: +median(timed.map(t => t.medianMs)).toFixed(3),
            meanMs: +median(timed.map(t => t.meanMs)).toFixed(3),
            p95Ms: +median(timed.map(t => t.p95Ms)).toFixed(3),
            maxMs: +Math.max(...timed.map(t => t.maxMs)).toFixed(3),
            medianAcrossRuns: timed.map(t => t.medianMs),
            maxTargets: Math.max(...timed.map(t => t.maxTargets)),
            maxClones: Math.max(...timed.map(t => t.maxClones)),
            endState: res.endState,
            targetsEnd: best.targetsEnd,
            bySpriteMax: Object.assign({}, ...Array.from(new Set(
                timed.flatMap(t => Object.keys(t.bySpriteMax))), sprite => ({
                [sprite]: Math.max(...timed.map(t => t.bySpriteMax[sprite] || 0))
            }))),
            workPerFrame: res.workPerFrame,
            redrawsPerFrame: res.redrawsPerFrame,
            opcodeTotals: res.opcodeTotals,
            opcodesPerFrame: res.opcodesPerFrame
        };
    }
    unmute();
    report.vmProblems = vmProblems;
    report.vmWarnings = vmWarnings.filter(
        w => !/No rendering module|No audio engine|^$/.test(w) &&
             !/\u001b\[/.test(w) && !/vm.warn/.test(w));
    const json = JSON.stringify(report, null, 2);
    if (args.includes('--json')) {
        // --json [path]: an optional output path may follow, but only if it
        // is not another flag (a trailing --json must not swallow it)
        const jsonIdx = args.indexOf('--json');
        const jsonNext = jsonIdx !== -1 ? args[jsonIdx + 1] : undefined;
        fs.writeFileSync(
            jsonNext && !jsonNext.startsWith('--') ? jsonNext : 'bench.json',
            json);
    }
    process.stdout.write(`${json}\n`);
}

main().catch(err => {
    console.error('bench crashed:', err && err.stack ? err.stack : err);
    process.exit(1);
});
