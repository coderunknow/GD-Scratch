#!/usr/bin/env bash
# Full verification. Rebuilds both archives, then checks:
#   1. Python reference physics and level solvability
#   2. deterministic synthesized audio assets
#   3. static project wiring (broadcasts, sounds, procedures)
#   4. structural validity inside the real scratch-vm
#   5. solved frame-by-frame replays and player-facing menus (at 30 and 60 fps)
#   6. glyph-pool consistency, clone lifecycle and repeated-effect stress
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== 1. level solver / reference physics ==="
PYTHONPATH=src python3 tools/verify_levels.py

echo
echo "=== 2. synthesized audio determinism ==="
PYTHONPATH=src python3 tests/check_audio_determinism.py

echo
echo "=== 3. build ==="
PYTHONPATH=src python3 -m gdscratch.build --out dist

echo
if [ ! -d tests/headless/node_modules ]; then
    echo "installing the scratch-vm test rig..."
    (cd tests/headless && npm ci --no-audit --no-fund)
fi

for FILE in dist/GD-Scratch.sb3 dist/GD-Scratch-TurboWarp.sb3; do
    echo
    echo "=== 4. static wiring audit: $FILE ==="
    python3 tools/audit_project.py "$FILE" | python3 -c "import json,sys; d=json.load(sys.stdin); \
print(json.dumps({'blocks': d['blocks']['total'], 'broadcasts': d['broadcasts'], \
'sounds': d['sounds'], 'procedures': d['procedures']}, indent=1)); \
assert not d['broadcasts']['neverSent'] and not d['broadcasts']['sentButNoReceiver']; \
assert not d['sounds']['neverPlayed']; \
assert not d['procedures']['neverCalled'] and not d['procedures']['danglingCalls']"

    echo
    echo "=== 5. structural audit: $FILE ==="
    # scratch-vm's minilog writes "vm warn" lines ahead of the JSON report
    (cd tests/headless && node harness.js "../../$FILE") | sed -n '/^{/,$p' |
        python3 -c "import sys,json; d=json.load(sys.stdin); \
print(json.dumps({'blocks': d['blocks'], 'assets': d['assets'], \
'problems': d['problems'], 'vmWarnings': d['vmWarnings'], \
'avgStepMs': d['avgStepMs'], 'failed': d.get('failed', False)}, indent=1)); \
sys.exit(1 if d.get('failed') else 0)"

    echo
    echo "=== 6. replay + menus + lifecycle: $FILE ==="
    # replay.js runs every fixture under both the 30 fps and 60 fps
    # deterministic clocks and asserts the physics/render pacing invariants.
    for L in 1 2 3; do
        (cd tests/headless && node replay.js "../../$FILE" "../fixtures/level${L}_solution.json") |
            grep -E '^PASS|^FAIL'
    done
    (cd tests/headless && node menus.js "../../$FILE") | tail -1
    (cd tests/headless && node menus.js "../../$FILE" --fps 60) | tail -1
    (cd tests/headless && node text.js "../../$FILE") | tail -1
    (cd tests/headless && node text.js "../../$FILE" --fps 60) | tail -1
    (cd tests/headless && node lifecycle.js "../../$FILE") |
        grep -E '^PASS:|^FAIL:'
    (cd tests/headless && node lifecycle.js "../../$FILE" --fps 60) |
        grep -E '^PASS:|^FAIL:'
done

echo
echo "all checks passed"
