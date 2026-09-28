/**
 * Differential fuzz: the real VM against the Python reference on random
 * inputs the solver fixtures never visit (random deaths, corner clips,
 * portal misses, pad/orb interactions).
 *
 * Schedules and expected traces come from tools/fuzz_ref.py, which derives
 * them from gdscratch.verify -- the same reference the fixtures use, so there
 * is no second implementation to drift. Each case replays a seeded bursty
 * hold schedule from a fresh level start and compares, per physics step, the
 * cube's y/vy/grounded/grav plus the final event (run-prefix / die / win).
 *
 *   node fuzz.js <file.sb3> [--fps N] [--seeds-per-level N]
 *
 * The default 6 seeds per level keep run_all.sh fast; the v0.2.1 audit ran
 * 150 seeds per level with zero mismatches (docs/v0.2.1.md).
 */

const {execFileSync} = require('child_process');
const path = require('path');
const {makeVM, boot, press, vars} = require('./vmlib');

const argList = process.argv.slice(2);
const fpsIdx = argList.indexOf('--fps');
const FPS = fpsIdx !== -1 ? Number(argList[fpsIdx + 1]) : 30;
const splIdx = argList.indexOf('--seeds-per-level');
const SEEDS = splIdx !== -1 ? Number(argList[splIdx + 1]) : 6;
const baseIdx = argList.indexOf('--seed-base');
const SEED_BASE = baseIdx !== -1 ? Number(argList[baseIdx + 1]) : 7000;
const frmIdx = argList.indexOf('--frames');
const FRAMES_USER = frmIdx !== -1 ? Number(argList[frmIdx + 1]) : null;
const file = argList[0];
if (!file) {
    console.log('usage: node fuzz.js <file.sb3> [--fps N] [--seeds-per-level N]');
    process.exit(2);
}

const FRAMES = 400;
const seeds = [];
for (let i = 1; i <= SEEDS; i += 1) seeds.push(SEED_BASE + i * 37);

let failures = 0;
function check (label, got, want) {
    const ok = String(got) === String(want);
    if (!ok) failures += 1;
    console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}` +
                (ok ? '' : `: ${got} (wanted ${want})`));
    return ok;
}

async function main () {
    const vm = makeVM();
    await boot(vm, file, FPS);
    console.log(`${file.split('/').pop()} @${FPS}fps, ` +
                `${SEEDS} seeds/level, ${FRAMES} steps/case`);
    const rt = vm.runtime;
    const gv = n => vars(vm)[n];
    const tap = key => {
        press(vm, key, true);
        rt._step();
        press(vm, key, false);
        rt._step();
    };
    const startLevel = level => {
        // a case can end mid-press (death while holding); scratch-vm keeps
        // io keys down across greenFlag, so force-release before restarting
        press(vm, 'space', false);
        press(vm, 'up arrow', false);
        press(vm, 'down arrow', false);
        vm.greenFlag();
        for (let i = 0; i < 4; i += 1) rt._step();
        tap('down arrow');                       // PLAY -> LEVEL SELECT
        tap('space');
        for (let i = 1; i < level; i += 1) tap('down arrow');
        press(vm, 'space', true);
        rt._step();
        press(vm, 'space', false);
        if (gv('state') !== 'play') {
            throw new Error(`level ${level} did not start (${gv('state')})`);
        }
    };

    let cases = 0;
    let stepsCompared = 0;
    for (let level = 1; level <= 3; level += 1) {
        const out = execFileSync('python3', [
            'tools/fuzz_ref.py', '--level', String(level),
            '--frames', String(FRAMES_USER || FRAMES), '--seeds', seeds.join(','),
        ], {cwd: path.join(__dirname, '../..'),
            env: {...process.env, PYTHONPATH: 'src'}, maxBuffer: 1 << 27});
        const ref = JSON.parse(out.toString());
        ref.frames = FRAMES_USER || FRAMES;
        for (const c of ref.cases) {
            startLevel(level);
            let down = false;
            let bad = '';
            // Drive by the observed frame counter (like physics.js): a 60 fps
            // render frame can run no physics step, so the input for step N
            // must stay on the key until step N actually runs; the game's
            // latch covers the render-only frames.
            for (;;) {
                const done = Number(gv('frame'));
                if (done >= c.trace.length) break;
                const want = c.holds[done] === 1;
                if (want !== down) {
                    press(vm, 'space', want);
                    down = want;
                }
                rt._step();
                const f = Number(gv('frame'));
                if (f === done) continue;      // frame ran no physics step
                if (gv('state') !== 'play') {
                    if (f !== c.frame) {
                        bad = `ended ${gv('state')} at step ${f} ` +
                              `(reference ran to ${c.frame})`;
                    }
                    break;
                }
                const w = c.trace[f - 1];
                const y = Number(gv('py'));
                const vy = Number(gv('vy'));
                const gr = Number(gv('grounded'));
                const gv2 = Number(gv('grav'));
                if (Math.abs(y - w[0]) > 1e-6 || Math.abs(vy - w[1]) > 1e-6 ||
                    gr !== w[2] || gv2 !== w[3]) {
                    bad = `step ${f}: y=${y} vy=${vy} g=${gr} v=${gv2} ` +
                          `want y=${w[0]} vy=${w[1]} g=${w[2]} v=${w[3]}`;
                    break;
                }
                stepsCompared += 1;
            }
            cases += 1;
            if (!bad) {
                const endState = gv('state');
                const refEvent = c.event === 'run' ? 'play' : c.event;
                if (c.event !== 'run' && endState !== refEvent && c.frame >= c.trace.length) {
                    // died/won exactly on the last compared step
                    if (!(endState === 'dead' && c.event === 'die') &&
                        !(endState === 'win' && c.event === 'win')) {
                        bad = `ended ${endState}, reference ${c.event}`;
                    }
                }
            }
            check(`L${level} seed ${c.seed}: ${bad || 'trace matches'}`,
                  bad, '');
        }
    }
    console.log(`${cases} schedules, ${stepsCompared} physics steps compared`);
    if (failures) {
        console.log(`FAIL: ${failures} check(s) failed`);
        process.exit(1);
    }
    console.log('PASS: VM matches the Python reference on random inputs');
}

main().catch(e => {
    console.log('FAIL: ' + e.message);
    process.exit(1);
});
