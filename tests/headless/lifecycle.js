/**
 * Clone-lifecycle regression and stress test.
 *
 *   node lifecycle.js <file.sb3> [--fps N]
 *
 * --fps runs the same stress coverage under a deterministic N-fps render clock
 * (see vmlib.simClock); clone populations must stay bounded at both rates.
 *
 * Reproductions:
 *  1. Start a level, then restart it repeatedly. Ground/Far/FX broadcast hats
 *     are inherited by Scratch clones; without an original-only guard, each
 *     restart makes each old clone spawn more clones until MAX_CLONES (300).
 *  2. Trigger repeated particle bursts. Without the same guard, every living
 *     FX particle responds to the next `boom` broadcast and recursively creates
 *     another full burst.
 *  3. Quit an active level to the menu. World-generation clones must retire
 *     instead of remaining active behind the menu.
 *
 * The test counts *actual scratch-vm Target instances*. This is stronger than
 * a static code/asset audit and exercises Scratch's real broadcast semantics.
 */

const {makeVM, boot, press, vars} = require('./vmlib');

const realError = console.error;
const problems = [];
console.error = (...a) => {
    problems.push(a.map(String).join(' '));
    realError('[vm:error]', ...a);
};
console.warn = () => {};

const argList = process.argv.slice(2);
const fpsIdx = argList.indexOf('--fps');
const FPS = fpsIdx !== -1 ? Number(argList[fpsIdx + 1]) : 30;
const file = argList[0];
if (!file) {
    console.log('usage: node lifecycle.js <file.sb3> [--fps N]');
    process.exit(2);
}

let failures = 0;
function check (label, ok, evidence = '') {
    if (!ok) failures += 1;
    console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}` +
        (evidence ? ` (${evidence})` : ''));
    return ok;
}

async function main () {
    const vm = makeVM();
    await boot(vm, file, FPS);
    const rt = vm.runtime;
    const step = (n = 1) => { for (let i = 0; i < n; i += 1) rt._step(); };
    const tap = key => {
        press(vm, key, true); step();
        press(vm, key, false); step();
    };
    const cloneCount = name => rt.targets.filter(
        t => !t.isOriginal && t.sprite.name === name).length;
    const totalClones = () => rt.targets.filter(t => !t.isOriginal).length;

    console.log(`clone lifecycle: ${file.split('/').pop()} @${FPS}fps`);
    vm.greenFlag();
    step(4);
    check('green flag reaches title', vars(vm).state === 'menu', vars(vm).state);

    // Open level 1 using only real key input, as a player would.
    tap('down arrow');
    tap('space');
    tap('space');
    step(12);
    check('level 1 starts', vars(vm).state === 'play', vars(vm).state);
    check('initial ground strips are bounded', cloneCount('Ground') === 4,
          `${cloneCount('Ground')} clones`);
    check('initial parallax strips are bounded', cloneCount('Far') === 2,
          `${cloneCount('Far')} clones`);

    // Repeated R is a concrete, fast reproduction: level start is broadcast
    // once per restart. If clone listeners are not guarded, population
    // multiplies at every restart. Capture both maximum and final live counts.
    let maxLive = totalClones();
    let maxGround = cloneCount('Ground');
    let maxFar = cloneCount('Far');
    for (let i = 0; i < 8; i += 1) {
        tap('r');
        step(8); // allow clone-start/retirement threads to run
        maxLive = Math.max(maxLive, totalClones());
        maxGround = Math.max(maxGround, cloneCount('Ground'));
        maxFar = Math.max(maxFar, cloneCount('Far'));
    }
    console.log(`  restart stress: live=${totalClones()}, max=${maxLive}, ` +
        `Ground max=${maxGround}, Far max=${maxFar}, runtime clone counter=${rt._cloneCounter}`);
    check('restart does not fan out environment clones',
          maxGround <= 4 && maxFar <= 2 && maxLive < 100,
          `max ${maxLive} total, Ground ${maxGround}, Far ${maxFar}`);

    // Quit and allow generation-mismatched tile/environment clones to be
    // retired. This tests the screen-exit path, not just the restart path.
    tap('q');
    step(10);
    const envAfterQuit = cloneCount('Tile') + cloneCount('Ground') + cloneCount('Far');
    check('Q returns to menu', vars(vm).state === 'menu', vars(vm).state);
    check('world clones retire on return to menu', envAfterQuit === 0,
          `${envAfterQuit} Tile/Ground/Far clones remain`);

    // Independently stress FX broadcasts. Broadcast hats on clones receive the
    // same message in Scratch; only the original FX target should spawn a burst.
    vm.greenFlag();
    step(4);
    const stage = rt.targets.find(t => t.isStage);
    const setStage = (name, value) => {
        for (const id in stage.variables) {
            if (stage.variables[id].name === name) {
                stage.variables[id].value = value;
                return;
            }
        }
        throw new Error(`missing stage variable ${name}`);
    };
    setStage('fxN', 22);
    setStage('fxAtX', 0);
    setStage('fxAtY', 0);
    let maxFx = 0;
    for (let i = 0; i < 6; i += 1) {
        rt.startHats('event_whenbroadcastreceived', {BROADCAST_OPTION: 'boom'});
        step(4);
        maxFx = Math.max(maxFx, cloneCount('FX'));
    }
    step(90);
    const remainingFx = cloneCount('FX');
    console.log(`  effect stress: peak FX=${maxFx}, remaining after drain=${remainingFx}`);
    check('each boom creates one bounded particle burst', maxFx <= 132,
          `${maxFx} FX clones peak for six 22-particle bursts`);
    check('particles clean themselves up', remainingFx === 0,
          `${remainingFx} FX clones remain after lifetime drain`);

    if (problems.length) {
        console.log('VM errors:');
        for (const p of problems.slice(0, 5)) console.log(`  ${p}`);
        failures += 1;
    }
    console.log(failures === 0 ? '\nPASS: clone lifecycle and effect stress'
        : `\nFAIL: ${failures} lifecycle check(s) failed`);
    process.exit(failures === 0 ? 0 : 1);
}

main().catch(err => {
    console.error('lifecycle.js crashed:', err && err.stack ? err.stack : err);
    process.exit(1);
});
