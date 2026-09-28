/**
 * Browser shim for scratch-audio's three CommonJS externals.
 *
 * `scratch-audio` only publishes a CommonJS bundle (`dist.js`) whose
 * `audio-context`, `minilog` and `startaudiocontext` dependencies are marked
 * as webpack externals -- they are `require()`d at load time and left out of
 * the bundle. This file puts a `module`/`exports`/`require` triple and those
 * three modules on `window` so the bundle can be dropped into a plain page
 * without running a bundler of our own.
 *
 * It must be loaded immediately before scratch-audio.js, and `player.js`
 * removes the globals straight afterwards so no other UMD bundle mistakes the
 * page for a CommonJS environment.
 */
(function () {
    'use strict';

    function noop () {}
    function logger () {
        return {debug: noop, info: noop, warn: noop, error: noop, trace: noop,
                fatal: noop, time: noop, timeEnd: noop, log: noop};
    }
    // minilog: callable factory, plus the handful of statics scratch-audio touches
    const minilog = logger;
    minilog.enable = noop;
    minilog.disable = noop;
    minilog.suggest = {deny: noop, allow: noop, clear: noop};
    minilog.defaultFormatter = 'color';
    minilog.defaultBackend = {attach: noop};
    minilog.pipe = noop;

    const shims = {
        // scratch-audio does `new AudioContext()` on this
        'audio-context': window.AudioContext || window.webkitAudioContext ||
            function UnavailableAudioContext () {
                throw new Error('Web Audio is not available in this browser');
            },
        'minilog': minilog,
        // startaudiocontext(ctx, element) resumes a suspended context on the
        // first user gesture; the real one just wires up listeners.
        'startaudiocontext': function startAudioContext (ctx, element) {
            if (!ctx || !element) return;
            const resume = () => { if (ctx.state === 'suspended' && ctx.resume) ctx.resume(); };
            ['pointerdown', 'touchstart', 'keydown'].forEach(evt =>
                element.addEventListener(evt, resume, {passive: true, once: false}));
        }
    };

    window.module = {exports: {}};
    window.exports = window.module.exports;
    window.require = function requireShim (name) {
        if (Object.prototype.hasOwnProperty.call(shims, name)) return shims[name];
        throw new Error(`scratch-audio shim: no module named "${name}"`);
    };
})();
