/**
 * Minimal player for a generated .sb3: scratch-vm + scratch-render +
 * scratch-audio + scratch-storage, wired up by hand the way scratch-gui does.
 */
(function () {
    'use strict';

    // scratch-audio's CommonJS shim installed these; take the engine back off
    // and clear them so nothing else mistakes the page for Node.
    const AudioEngine = window.module && window.module.exports;
    delete window.module;
    delete window.exports;
    delete window.require;

    const statusEl = document.getElementById('status');
    const canvas = document.getElementById('stage');
    const flagBtn = document.getElementById('greenflag');
    const stopBtn = document.getElementById('stop');
    const turboBtn = document.getElementById('turbo');

    const PROJECTS = [
        {label: 'stock Scratch build', file: '/dist/GD-Scratch.sb3'},
        {label: 'TurboWarp build', file: '/dist/GD-Scratch-TurboWarp.sb3'}
    ];

    function fail (message) {
        statusEl.classList.remove('gone');
        statusEl.textContent = message;
    }

    // The UMD globals do not all have the same shape: scratch-vm and
    // scratch-render export their class directly, while scratch-storage
    // exports a namespace object holding the class.
    const StorageClass = window.ScratchStorage &&
        (window.ScratchStorage.ScratchStorage || window.ScratchStorage);

    const missing = [];
    if (typeof window.VirtualMachine !== 'function') missing.push('scratch-vm');
    if (typeof window.ScratchRender !== 'function') missing.push('scratch-render');
    if (typeof StorageClass !== 'function') missing.push('scratch-storage');
    if (typeof AudioEngine !== 'function') missing.push('scratch-audio');
    if (missing.length) {
        fail(`the preview bundles are missing: ${missing.join(', ')}. ` +
             'Run `npm ci` in tests/headless, then restart preview/serve.py.');
        return;
    }

    const vm = new window.VirtualMachine();
    vm.attachStorage(new StorageClass());
    vm.attachRenderer(new window.ScratchRender(canvas));
    vm.attachAudioEngine(new AudioEngine());

    // --- input ---------------------------------------------------------
    // scratch-vm's IO devices do not listen to the DOM themselves; the host
    // application forwards events to them.
    const BLOCKED = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' ', 'Enter']);
    function postKey (event, isDown) {
        if (BLOCKED.has(event.key)) event.preventDefault();
        vm.runtime.ioDevices.keyboard.postData({key: event.key, isDown});
    }
    window.addEventListener('keydown', e => { if (!e.repeat) postKey(e, true); });
    window.addEventListener('keyup', e => postKey(e, false));

    function postMouse (event, isDown) {
        const rect = canvas.getBoundingClientRect();
        vm.runtime.ioDevices.mouse.postData({
            x: event.clientX - rect.left,
            y: event.clientY - rect.top,
            canvasWidth: rect.width,
            canvasHeight: rect.height,
            isDown
        });
    }
    canvas.addEventListener('pointerdown', e => { canvas.setPointerCapture(e.pointerId); postMouse(e, true); });
    canvas.addEventListener('pointerup', e => postMouse(e, false));
    canvas.addEventListener('pointermove', e => { if (e.buttons) postMouse(e, undefined); });

    // --- controls ------------------------------------------------------
    flagBtn.addEventListener('click', () => { canvas.focus(); vm.greenFlag(); });
    stopBtn.addEventListener('click', () => vm.stopAll());
    turboBtn.addEventListener('click', () => {
        vm.setTurboMode(!vm.runtime.turboMode);
        turboBtn.textContent = `turbo: ${vm.runtime.turboMode ? 'on' : 'off'}`;
    });

    async function load (which) {
        statusEl.classList.remove('gone');
        statusEl.textContent = `loading ${PROJECTS[which].label}\u2026`;
        flagBtn.disabled = stopBtn.disabled = turboBtn.disabled = true;
        try {
            const res = await fetch(PROJECTS[which].file);
            if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
            await vm.loadProject(await res.arrayBuffer());
            vm.start();
            vm.greenFlag();
            statusEl.classList.add('gone');
        } catch (err) {
            fail(`could not load ${PROJECTS[which].file}: ${err.message}`);
            return;
        }
        flagBtn.disabled = stopBtn.disabled = turboBtn.disabled = false;
    }

    // A tiny switcher so both shipped archives can be tried side by side.
    const bar = document.getElementById('bar');
    const picker = document.createElement('button');
    let which = 0;
    picker.textContent = `file: ${PROJECTS[0].label}`;
    picker.addEventListener('click', async () => {
        which = (which + 1) % PROJECTS.length;
        picker.textContent = `file: ${PROJECTS[which].label}`;
        vm.stopAll();
        await load(which);
    });
    bar.appendChild(picker);

    load(0);
    window.__gdScratchVM = vm;   // handy from the devtools console
})();
