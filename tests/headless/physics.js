/**
 * Physics edge cases that the solver replays never touch.
 *
 * replay.js walks the three fixture solutions frame by frame, but those paths
 * roll past almost every interactive cell: they hit pads and (on level 3)
 * portals and three coins -- and never a coin on levels 1/2 and never a blue
 * ring anywhere. This file drives two hand-built level 1 schedules through the
 * real VM and compares them against the Python reference (verify.py) trace
 * recorded when the schedules were designed:
 *
 *   coin run: fixture holds + one extra tap on step 115. The cube is inside
 *     the coin cell (col 35, row 1) on steps 115, 116 and 117 -- three
 *     consecutive physics steps -- so the GOT bookkeeping must collect the
 *     coin exactly once.
 *
 *   orb run: fixture holds + a ground-jump tap on step 469 and a fresh tap on
 *     step 474, the first step the cube is airborne inside the ring cell
 *     (col 154, row 2). The ring must re-launch with vy = ORB_V = 25 exactly
 *     on that step (a plain jump decays 8.0 -> 4.2 there instead).
 *
 * Both schedules still finish the level ("win" on step 659), so the whole
 * run can be compared end to end. All numbers below were produced by
 * `python3 -c` against src/gdscratch/verify.py on the same fixture; if the
 * Scratch side diverges from the reference these checks fail.
 *
 *   node physics.js <file.sb3> [--fps N]
 *
 * The scenario is defined in physics steps; under --fps N it runs under the
 * deterministic N-fps clock and must behave identically.
 */

const fs = require('fs');
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
    console.log('usage: node physics.js <file.sb3> [--fps N]');
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

// reference traces from verify.py (frames 112..129 / 470..485, step 1)
const COIN_FRAMES = [112, 129];
const COIN_Y = [-105, -105, -105, -81.8, -62.4, -46.8, -35, -27, -22.8,
    -22.4, -25.8, -33, -44, -58.8, -77.4, -99.8, -105, -105];
const COIN_VY = [0, 0, 0, 23.2, 19.4, 15.6, 11.8, 8, 4.2,
    0.4, -3.4, -7.2, -11, -14.8, -18.6, -22.4, 0, 0];
const ORB_FRAMES = [470, 495];
const ORB_Y = [-62.4, -46.8, -35, -27, -22.8, -1.6, 15.8, 29.4, 39.2, 45.2,
    47.4, 45.8, 40.4, 31.2, 18.2, 1.4, -19.2, -43.2, -67.2, -91.2,
    -105, -105, -105, -105, -105, -105];
const ORB_VY = [19.4, 15.6, 11.8, 8, 25, 21.2, 17.4, 13.6, 9.8, 6,
    2.2, -1.6, -5.4, -9.2, -13, -16.8, -20.6, -24, -24, -24,
    0, 0, 0, 0, 0, 0];

async function runSchedule (vm, name, holds, extra) {
    const rt = vm.runtime;
    const gv = n => vars(vm)[n];
    // a previous schedule can end mid-press; release everything first
    press(vm, 'space', false);
    press(vm, 'up arrow', false);
    press(vm, 'down arrow', false);
    vm.greenFlag();
    for (let i = 0; i < 4; i += 1) rt._step();
    // activate level 1 the way replay.js does: press, one frame, release,
    // NO trailing frame -- the replay loop owns the clock from here on
    press(vm, 'space', true);
    rt._step();
    press(vm, 'space', false);
    if (gv('state') !== 'play') {
        check(`${name}: level 1 started`, gv('state'), 'play');
        return null;
    }
    const trace = {};
    let down = false;
    while (Number(gv('frame')) < holds.length) {
        // key the input to the next due physics step, whatever the render
        // rate runs (replay.js drives the fixture schedules the same way)
        const nextStep = Number(gv('frame')) + 1;
        const want = holds[nextStep - 1] === 1;
        if (want !== down) {
            press(vm, 'space', want);
            down = want;
        }
        rt._step();
        if (Number(gv('frame')) === nextStep && gv('state') === 'play') {
            trace[nextStep] = {y: Number(gv('py')), vy: Number(gv('vy'))};
        }
        if (gv('state') !== 'play') break;         // died or won this step
    }
    const endState = gv('state');
    const endFrame = Number(gv('frame'));
    for (const [f, v] of Object.entries(extra)) {
        if (holds[f - 1] !== v) {
            check(`${name}: schedule encodes step ${f}`, holds[f - 1], v);
        }
    }
    return {trace, endState, endFrame, gv};
}

function compareWindow (name, trace, frames, ys, vys) {
    const [f0, f1] = frames;
    let bad = 0;
    for (let f = f0; f <= f1; f += 1) {
        const got = trace[f];
        const wy = ys[f - f0];
        const wv = vys[f - f0];
        if (!got ||
            Math.abs(got.y - wy) > 1e-9 ||
            Math.abs(got.vy - wv) > 1e-9) {
            bad += 1;
            if (bad <= 3) {
                console.log(`      step ${f}: ` +
                    `y=${got ? got.y : 'n/a'} (want ${wy}) ` +
                    `vy=${got ? got.vy : 'n/a'} (want ${wv})`);
            }
        }
    }
    check(`${name}: y/vy match the Python reference, steps ${f0}-${f1}`,
        bad, 0);
}

async function main () {
    const base =
        JSON.parse(fs.readFileSync(
            `${__dirname}/../fixtures/level1_solution.json`)).holds;

    const vm = makeVM();
    await boot(vm, file, FPS);
    console.log(`${file.split('/').pop()} @${FPS}fps`);

    console.log('coin idempotence (3-step overlap collects once)');
    const coinHolds = base.slice();
    coinHolds[115 - 1] = 1;
    const coin = await runSchedule(vm, 'coin', coinHolds, {115: 1});
    compareWindow('coin', coin.trace, COIN_FRAMES, COIN_Y, COIN_VY);
    check('coin collected exactly once despite 3-step overlap',
        coin.gv('coins'), 1);
    // the cell key is the join of rr*1000 and cc ("1000"+"35"), not the
    // arithmetic sum -- still unique per cell since cc never has leading
    // zeros and stays under 1000
    check('GOT holds the single cell key for row 1, col 35',
        JSON.stringify(coin.gv('GOT')), '["100035"]');
    check('run still wins on step 659',
        `${coin.endState}@${coin.endFrame}`, 'win@659');

    console.log('blue ring needs a fresh press inside the cell');
    const orbHolds = base.slice();
    orbHolds[469 - 1] = 1;
    orbHolds[474 - 1] = 1;
    const orb = await runSchedule(vm, 'orb', orbHolds, {469: 1, 474: 1});
    compareWindow('orb', orb.trace, ORB_FRAMES, ORB_Y, ORB_VY);
    check('ring re-launches with vy=25 on step 474',
        orb.trace[474] ? orb.trace[474].vy : 'n/a', 25);
    check('run still wins on step 659',
        `${orb.endState}@${orb.endFrame}`, 'win@659');

    console.log('block corner forgiveness (v0.2.1 rule, both sides)');
    // fixture holds + one extra tap on step 271: the cube falls onto a block
    // corner with its bottom 2.4 px below the surface at step 282. The old
    // rule killed there (pre-fix dist: die@283); the reference now snaps it
    // onto the surface and the run still wins on step 659.
    const cornerHolds = base.slice();
    cornerHolds[271 - 1] = 1;
    const corner = await runSchedule(vm, 'corner', cornerHolds, {271: 1});
    {
        const rows = [];
        for (let f = 278; f <= 292; f += 1) rows.push(corner.trace[f]);
        const want = [
            [-25.8, -3.4], [-33, -7.2], [-44, -11], [-58.8, -14.8],
            [-77.4, -18.6], [-75, 0], [-75, 0], [-75, 0], [-75, 0],
            [-75, 0], [-75, 0], [-75, 0], [-75, 0], [-75, 0], [-78.8, -3.8]];
        let bad = 0;
        rows.forEach((r, i) => {
            if (!r || Math.abs(r.y - want[i][0]) > 1e-9 ||
                Math.abs(r.vy - want[i][1]) > 1e-9) bad += 1;
        });
        check('corner clip matches the Python reference, steps 278-292',
            bad, 0);
        check('the corner clip lands instead of killing (grounded at 283)',
            corner.trace[283] ? corner.trace[283].y : 'no trace (dead)',
            -75);
        check('the forgiven run still wins on step 659',
            `${corner.endState}@${corner.endFrame}`, 'win@659');
    }

    if (problems.length) {
        failures += 1;
        console.log(`FAIL: ${problems.length} runtime error(s):`);
        for (const p of problems) console.log(`  ${p}`);
        return;
    }
    if (failures) {
        console.log(`FAIL: ${failures} check(s) failed`);
        process.exit(1);
    }
    console.log('PASS: coin and ring physics match the Python reference');
}

main().catch(e => {
    console.log('FAIL: ' + e.message);
    process.exit(1);
});
