/**
 * Headless harness that loads a generated .sb3 into the *real* scratch-vm and
 * runs it. This is the ground truth used to prove the game works.
 *
 *   node harness.js <file.sb3> [script.json]
 *
 * script.json (optional) drives a deterministic playthrough:
 *   { "frames": 1000,
 *     "keys":   { "12": ["space"], "40": [] },      // frame -> keys held
 *     "clicks": [ { "frame": 5, "x": 0, "y": 0 } ],
 *     "watch":  ["state", "worldX"] }
 */

const fs = require('fs');
const {makeVM, boot, press: pressKey, vars: varsOf} = require('./vmlib');

const problems = [];
const warnings = [];

// scratch-vm logs through minilog onto console; capture everything it says.
const realError = console.error;
console.error = (...args) => {
    problems.push(args.map(String).join(' '));
    realError('[vm:error]', ...args);
};
console.warn = (...args) => {
    warnings.push(args.map(String).join(' '));
};

process.on('unhandledRejection', err => {
    problems.push(`unhandledRejection: ${err && err.stack ? err.stack : err}`);
});

/**
 * Opcodes that are not primitives: dropdown menus, literal placeholders and
 * the mutator shadow inside every custom-block definition. Scratch writes all
 * of these into project.json and the VM resolves them specially, so a file
 * that contains *only* these plus real primitives needs no extensions.
 */
const SHADOWS = [
    'math_number', 'math_positive_number', 'math_whole_number',
    'math_integer', 'math_angle', 'colour_picker', 'text',
    'event_broadcast_menu', 'data_variable', 'data_listcontents',
    'motion_goto_menu', 'motion_glideto_menu', 'motion_pointtowards_menu',
    'looks_costume', 'looks_backdrops', 'sound_menu', 'sound_effects_menu',
    'sound_volumemenu', 'control_create_clone_of_menu', 'control_stop_menu',
    'sensing_touchingobjectmenu', 'sensing_distancetomenu',
    'sensing_keyoptions', 'sensing_of_object_menu', 'sensing_of_property_menu',
    'operator_mathop_menu',
    // the mutator shadow nested inside `procedures_definition`; without it the
    // VM cannot resolve the definition and every call silently no-ops
    'procedures_prototype'
];

function blocksOf (vm) {
    let count = 0;
    let topLevel = 0;
    const unknown = new Set();
    const badArgs = new Set();
    const hats = Object.keys(vm.runtime._hats);

    // The argument names the VM itself expects for each opcode. A block written
    // with the wrong input name is not an error to the deserializer -- the
    // primitive just reads `undefined` and Scratch silently computes with zero.
    // (That is exactly how `operator_add` with OPERAND1/OPERAND2 instead of
    // NUM1/NUM2 turned every + - * / in the project into 0.)
    const specArgs = new Map();
    for (const info of (vm.runtime._blockInfo || [])) {
        for (const opcode in (info.blocks || {})) {
            const args = info.blocks[opcode].json && info.blocks[opcode].json.arguments;
            if (args) specArgs.set(opcode, new Set(Object.keys(args)));
        }
    }

    for (const target of vm.runtime.targets) {
        const blocks = target.blocks._blocks;
        for (const id in blocks) {
            count += 1;
            const block = blocks[id];
            if (block.topLevel) topLevel += 1;
            const opcode = block.opcode;
            const known = vm.runtime._primitives[opcode] || hats.includes(opcode) ||
                opcode === 'procedures_definition' || SHADOWS.includes(opcode);
            if (!known) unknown.add(opcode);
            const spec = specArgs.get(opcode);
            if (spec) {
                for (const name in block.inputs) {
                    if (!spec.has(name)) {
                        badArgs.add(`${opcode}.${name}`);
                    }
                }
            }
            // structural integrity checks
            for (const name in block.inputs) {
                const input = block.inputs[name];
                if (input.block && !blocks[input.block]) {
                    problems.push(`${target.name}: input ${name} of ${id} -> missing block ${input.block}`);
                }
                if (input.shadow && !blocks[input.shadow]) {
                    problems.push(`${target.name}: shadow ${name} of ${id} -> missing ${input.shadow}`);
                }
            }
            if (block.next && !blocks[block.next]) {
                problems.push(`${target.name}: next of ${id} -> missing ${block.next}`);
            }
            if (block.parent && !blocks[block.parent]) {
                problems.push(`${target.name}: parent of ${id} -> missing ${block.parent}`);
            }
        }
    }
    // every custom block that is called must resolve to a definition; a call
    // whose definition is missing is a silent no-op in the VM
    const dangling = new Set();
    for (const target of vm.runtime.targets) {
        if (!target.isOriginal) continue;
        const blocks = target.blocks;
        for (const id in blocks._blocks) {
            const block = blocks._blocks[id];
            if (block.opcode !== 'procedures_call') continue;
            const code = block.mutation && block.mutation.proccode;
            if (!blocks.getProcedureDefinition(code)) {
                dangling.add(`${target.sprite.name}: ${code}`);
            }
        }
    }
    return {count, topLevel, unknownOpcodes: [...unknown],
            unresolvableCalls: [...dangling], badInputNames: [...badArgs]};
}

/**
 * Decode every PNG / parse every WAV straight out of the zip and confirm the
 * md5 in project.json matches the bytes -- this is exactly what Scratch does
 * when it opens the file.
 */
function assetAudit (zipPath) {
    const PNG = require('pngjs').PNG;
    const JSZip = require('jszip');
    const crypto = require('crypto');
    const out = {pngs: 0, wavs: 0, bad: [], totalBytes: 0};
    return JSZip.loadAsync(fs.readFileSync(zipPath)).then(z => {
        const names = Object.keys(z.files).filter(n => n !== 'project.json');
        const chain = names.reduce((p, name) => p.then(() => z.files[name].async('nodebuffer')
            .then(buf => {
                out.totalBytes += buf.length;
                const md5 = crypto.createHash('md5').update(buf).digest('hex');
                const base = name.split('.')[0];
                if (md5 !== base) {
                    out.bad.push(`${name}: md5 mismatch (${md5})`);
                }
                if (name.endsWith('.png')) {
                    out.pngs += 1;
                    try {
                        const img = PNG.sync.read(buf);
                        if (!img.width || !img.height) out.bad.push(`${name}: empty png`);
                    } catch (e) {
                        out.bad.push(`${name}: ${e.message}`);
                    }
                } else if (name.endsWith('.wav')) {
                    out.wavs += 1;
                    if (buf.slice(0, 4).toString() !== 'RIFF' || buf.slice(8, 12).toString() !== 'WAVE') {
                        out.bad.push(`${name}: not a RIFF/WAVE file`);
                    }
                } else {
                    out.bad.push(`${name}: unexpected asset type`);
                }
            })), Promise.resolve());
        return chain.then(() => out);
    });
}

async function main () {
    const file = process.argv[2];
    if (!file) {
        console.log('usage: node harness.js <file.sb3> [script.json]');
        process.exit(2);
    }
    const script = process.argv[3] ? JSON.parse(fs.readFileSync(process.argv[3], 'utf8')) : null;
    const vm = makeVM();
    const t0 = Date.now();
    // Scratch steps every 33.33ms; the sequencer budgets 75% of that per frame.
    // start() would install a real interval timer, so drive _step() by hand.
    await boot(vm, file);
    const loadMs = Date.now() - t0;

    const report = {
        file,
        loadMs,
        targets: vm.runtime.targets.filter(t => t.isOriginal)
            .map(t => ({name: t.sprite.name, isStage: t.isStage,
                        costumes: t.sprite.costumes.length,
                        sounds: t.sprite.sounds.length})),
        blocks: blocksOf(vm),
        assets: await assetAudit(file),
    };
    // "No rendering module present" / "No audio engine present" are expected in
    // a headless VM (there is no WebGL canvas or AudioContext); everything else
    // scratch-vm complains about is a real defect.
    report.problems = problems;
    report.vmWarnings = warnings.filter(w => !/No rendering module|No audio engine/.test(w));

    const frames = (script && script.frames) || 10;
    const watch = (script && script.watch) || [];
    const keysByFrame = (script && script.keys) || {};
    const trace = [];
    let heldKeys = [];
    let stepMs = 0;

    vm.greenFlag();
    for (let f = 0; f < frames; f += 1) {
        if (keysByFrame[String(f)]) {
            const next = keysByFrame[String(f)];
            for (const k of heldKeys) {
                if (!next.includes(k)) pressKey(vm, k, false);
            }
            for (const k of next) {
                if (!heldKeys.includes(k)) pressKey(vm, k, true);
            }
            heldKeys = next;
        }
        const s0 = process.hrtime.bigint();
        vm.runtime._step();
        stepMs += Number(process.hrtime.bigint() - s0) / 1e6;
        if (watch.length) {
            const vars = varsOf(vm);
            const row = {f};
            for (const name of watch) row[name] = vars[name];
            trace.push(row);
        }
    }
    for (const k of heldKeys) pressKey(vm, k, false);

    report.frames = frames;
    report.avgStepMs = Number((stepMs / frames).toFixed(3));
    report.finalVariables = varsOf(vm);
    if (watch.length) report.trace = trace;
    if (problems.length) report.unresolvedProblems = problems;
    if (report.blocks.unknownOpcodes.length || report.blocks.unresolvableCalls.length ||
        report.blocks.badInputNames.length || problems.length) {
        report.failed = true;
    }

    if (process.env.DUMP_TRACE && watch.length) {
        fs.writeFileSync(process.env.DUMP_TRACE, JSON.stringify(trace));
    }
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    if (report.failed) process.exit(1);
}

main().catch(err => {
    realError('harness crashed:', err && err.stack ? err.stack : err);
    process.exit(1);
});
