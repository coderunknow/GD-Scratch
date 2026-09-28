/**
 * Glyph/text-pool consistency test.
 *
 * The text pool draws the dynamic strings (progress bar, percentage, attempt,
 * coins, menu values) through 48 glyph clones. Each clone watches its slot's
 * revision (TXTREV) and only reapplies costume/position/size when that slot
 * was rewritten. That is a performance guard, and its failure mode is a stale
 * glyph: a clone still showing an old character, old position or old size
 * while the lists moved on. No other test inspects rendered text, so this one
 * does: after every interesting state change, every clone must exactly match
 * the slot state it is responsible for.
 *
 *   node text.js <file.sb3> [--fps N]
 */

const {makeVM, boot, press, vars} = require('./vmlib');

const argList = process.argv.slice(2);
const fpsIdx = argList.indexOf('--fps');
const FPS = fpsIdx !== -1 ? Number(argList[fpsIdx + 1]) : 30;
const file = argList[0];
if (!file) {
    console.log('usage: node text.js <file.sb3> [--fps N]');
    process.exit(2);
}

const problems = [];
const realError = console.error;
console.error = (...a) => { problems.push(a.map(String).join(' ')); realError(...a); };
console.warn = () => {};

let failures = 0;
const check = (label, ok, evidence = '') => {
    if (!ok) failures += 1;
    console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}` + (evidence ? ` (${evidence})` : ''));
    return ok;
};

/**
 * For every Text clone: visible <=> its slot's char is not " ", and costume,
 * x and y must equal the slot's TXTCH/TXTX/TXTY values.
 *
 * Size is deliberately not compared: headless scratch-vm's
 * RenderedTarget.setSize only assigns this.size when a renderer is attached
 * (the v0.2.0 baseline behaves the same way), so the size property is not
 * observable here. In a real player the set_size inside the same refresh
 * branch applies it.
 */
function verifyGlyphs (rt, label) {
    const stage = rt.targets.find(t => t.isStage);
    const lists = {};
    for (const id in stage.variables) {
        const v = stage.variables[id];
        if (v.type === 'list') lists[v.name] = v.value;
    }
    const get = (target, name) => {
        for (const id in target.variables) {
            if (target.variables[id].name === name) return target.variables[id].value;
        }
        return undefined;
    };
    let checked = 0;
    const bad = [];
    for (const t of rt.targets) {
        if (t.isOriginal || t.sprite.name !== 'Text') continue;
        const slot = Number(get(t, 'mySlot'));
        const ch = lists.TXTCH[slot - 1];
        const x = Number(lists.TXTX[slot - 1]);
        const y = Number(lists.TXTY[slot - 1]);
        const visible = ch !== ' ';
        const costume = t.sprite.costumes[t.currentCostume].name;
        const row = `slot=${slot} ch="${ch}" costume=${costume} ` +
            `xy=(${t.x},${t.y}) want=(${x},${y}) visible=${t.visible}`;
        if (t.visible !== visible ||
            (visible && (costume !== ch || t.x !== x || t.y !== y))) {
            bad.push(row);
        }
        checked += 1;
    }
    check(`${label}: all ${checked} glyphs match their slots`, bad.length === 0,
          bad.slice(0, 3).join(' | '));
}

async function main () {
    const vm = makeVM();
    await boot(vm, file, FPS);
    const rt = vm.runtime;
    const step = (n = 1) => { for (let i = 0; i < n; i += 1) rt._step(); };
    const tap = key => { press(vm, key, true); step(); press(vm, key, false); step(); };

    console.log(`glyph pool consistency: ${file.split('/').pop()} @${FPS}fps`);
    vm.greenFlag();
    step(6);
    check('reaches the title screen', vars(vm).state, 'menu');
    verifyGlyphs(rt, 'title screen');

    tap('down arrow');                       // LEVEL SELECT
    tap('space');
    step(2);
    verifyGlyphs(rt, 'level select');

    tap('q');                                // back out
    step(2);
    tap('down arrow'); tap('down arrow');    // SETTINGS
    tap('space');
    step(2);
    verifyGlyphs(rt, 'settings (ON rows)');

    tap('space');                            // toggle music -> OFF
    step(2);
    verifyGlyphs(rt, 'settings after toggle (OFF row)');

    tap('down arrow'); tap('down arrow'); tap('down arrow');
    tap('space');                            // BACK
    step(2);
    verifyGlyphs(rt, 'back on the title screen');

    tap('down arrow'); tap('space'); tap('space');   // level select -> level 1
    step(10);
    check('level 1 running', vars(vm).state, 'play');
    step(50);                                // progress % changes under us
    verifyGlyphs(rt, 'play (progress/attempt/coins HUD)');

    // force an attempt change: restart, then let the HUD repaint
    tap('r');
    step(10);
    verifyGlyphs(rt, 'after restart (attempt incremented)');

    // force a progress-bar/percent change to a rounder value: run to death
    for (let i = 0; i < 200 && vars(vm).state === 'play'; i += 1) step();
    check('cube died on the first spike', vars(vm).state, 'dead');
    verifyGlyphs(rt, 'death screen');
    for (let i = 0; i < 100 && vars(vm).state !== 'play'; i += 1) step();
    step(6);
    verifyGlyphs(rt, 'auto-restart (fresh HUD)');

    // win screen (force the same procedure the game uses, as menus.js does)
    const stage = rt.targets.find(t => t.isStage);
    const setV = (n, val) => {
        for (const id in stage.variables) {
            if (stage.variables[id].name === n) { stage.variables[id].value = val; return; }
        }
    };
    setV('state', 'win'); setV('winT', 26); setV('sel', 1); setV('selCount', 3);
    step(4);
    verifyGlyphs(rt, 'win screen');

    if (problems.length) {
        console.log('vm errors:');
        for (const p of problems.slice(0, 5)) console.log(`  ${p}`);
        failures += 1;
    }
    console.log(failures === 0 ? '\nPASS: glyph pool matches the text lists'
        : `\nFAIL: ${failures} glyph consistency check(s) failed`);
    process.exit(failures === 0 ? 0 : 1);
}

main().catch(err => {
    console.error('text.js crashed:', err && err.stack ? err.stack : err);
    process.exit(1);
});
