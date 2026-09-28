/**
 * Replay a Python-solved input schedule inside the real scratch-vm and prove
 * the generated game reproduces the reference physics exactly.
 *
 *   node replay.js <file.sb3> <fixture.json> [--verbose]
 *
 * The fixture comes from tools/verify_levels.py and contains the per-frame
 * hold schedule plus the y/vy/grounded trace that gdscratch.verify produced.
 * Every frame is compared bit-for-bit; a single mismatch fails the run.
 *
 * Exits 0 when the whole level replays identically and ends in the expected
 * event, 1 otherwise.
 */

const fs = require('fs');
const {makeVM, boot, press, vars} = require('./vmlib');

const verbose = process.argv.includes('--verbose');
const args = process.argv.slice(2).filter(a => a !== '--verbose');
const [file, fixturePath] = args;

if (!file || !fixturePath) {
    console.log('usage: node replay.js <file.sb3> <fixture.json> [--verbose]');
    process.exit(2);
}

const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
const problems = [];
const realError = console.error;
console.error = (...a) => { problems.push(a.map(String).join(' ')); realError(...a); };

async function main () {
    const vm = makeVM();
    // One _step() == exactly one 33.33ms frame == exactly one game tick.
    await boot(vm, file);

    const level = fixture.level;
    vm.greenFlag();

    // let setup finish and the glyph pool spawn
    for (let i = 0; i < 4; i += 1) vm.runtime._step();
    let v = vars(vm);
    if (v.state !== 'menu') {
        console.log(`FAIL: expected state "menu" after setup, got "${v.state}"`);
        process.exit(1);
    }

    // Drive the real menus with the real keys: main menu row 2 is LEVEL
    // SELECT, whose rows are the three levels.
    const tap = key => {
        press(vm, key, true);
        vm.runtime._step();
        press(vm, key, false);
        vm.runtime._step();
    };
    tap('down arrow');                                  // PLAY -> LEVEL SELECT
    v = vars(vm);
    if (Number(v.sel) !== 2) {
        console.log(`FAIL: first DOWN left the menu on sel=${v.sel}, wanted 2`);
        process.exit(1);
    }
    tap('space');                                       // -> level select screen
    v = vars(vm);
    if (v.state !== 'select') {
        console.log(`FAIL: LEVEL SELECT did not open (state=${v.state})`);
        process.exit(1);
    }
    for (let i = 1; i < level; i += 1) tap('down arrow');
    v = vars(vm);
    if (Number(v.sel) !== level) {
        console.log(`FAIL: level select landed on sel=${v.sel}, wanted ${level}`);
        process.exit(1);
    }
    // One press, one frame, then release *without* stepping: the replay loop
    // below owns the clock from the very next frame, which has to be frame 1.
    press(vm, 'space', true);
    vm.runtime._step();
    press(vm, 'space', false);
    v = vars(vm);
    if (v.state !== 'play' || Number(v.level) !== level) {
        console.log(`FAIL: activating level ${level} did not start it ` +
                    `(state=${v.state}, level=${v.level})`);
        process.exit(1);
    }

    // replay the solved schedule, comparing every frame
    const holds = fixture.holds;
    const trace = fixture.trace;
    let mismatches = 0;
    let firstBad = null;
    let endState = null;

    for (let i = 0; i < holds.length; i += 1) {
        press(vm, 'space', holds[i] === 1);
        vm.runtime._step();
        v = vars(vm);
        const got = {f: Number(v.frame), y: Number(v.py), vy: Number(v.vy),
                     grav: Number(v.grav), grounded: Number(v.grounded)};
        const want = trace[i + 1];
        const ok = want && got.f === want.f && got.y === want.y &&
                   got.vy === want.vy && got.grav === want.grav &&
                   got.grounded === want.grounded;
        if (!ok && mismatches === 0) firstBad = {i, got, want};
        if (!ok) mismatches += 1;
        if (verbose && i % 60 === 0) {
            console.log(`  frame ${got.f}: y=${got.y} vy=${got.vy} grav=${got.grav}`);
        }
        if (v.state !== 'play') { endState = v.state; break; }
    }
    press(vm, 'space', false);
    if (endState === null) {
        vm.runtime._step();
        endState = vars(vm).state;
    }

    const report = {
        file: file.split('/').pop(),
        level,
        name: fixture.name,
        framesReplayed: holds.length,
        mismatches,
        endState,
        expectedEvent: fixture.expectedEvent,
        finalProgress: Number(vars(vm).prog),
        coinsCollected: Number(vars(vm).coins),
        coinsInLevel: fixture.coinsInLevel
    };
    if (firstBad) report.firstMismatch = firstBad;
    if (problems.length) report.vmErrors = problems.slice(0, 5);

    console.log(JSON.stringify(report, null, 2));

    const passed = mismatches === 0 && problems.length === 0 &&
        endState === fixture.expectedEvent;
    if (!passed) {
        console.log(`FAIL: ${fixture.name} did not replay identically`);
        process.exit(1);
    }
    console.log(`PASS: ${fixture.name} -- ${holds.length} frames identical, ` +
                `ended "${endState}", ${report.coinsCollected}/${report.coinsInLevel} coins`);
}

main().catch(err => {
    console.error('replay crashed:', err);
    process.exit(1);
});
