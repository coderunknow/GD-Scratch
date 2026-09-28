#!/usr/bin/env bash
# Full verification. Rebuilds both archives, then checks:
#   1. Python reference physics and level solvability
#   2. static project wiring (broadcasts, sounds, procedures)
#   3. structural validity inside the real scratch-vm
#   4. solved frame-by-frame replays and player-facing menus
#   5. clone lifecycle and repeated-effect stress behavior
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== 1. level solver / reference physics ==="
PYTHONPATH=src python3 tools/verify_levels.py

echo
echo "=== 2. build ==="
PYTHONPATH=src python3 -m gdscratch.build --out dist

echo
if [ ! -d tests/headless/node_modules ]; then
    echo "installing the scratch-vm test rig..."
    (cd tests/headless && npm ci --no-audit --no-fund)
fi

for FILE in dist/GD-Scratch.sb3 dist/GD-Scratch-TurboWarp.sb3; do
    echo
    echo "=== 3. static wiring audit: $FILE ==="
    python3 tools/audit_project.py "$FILE" | python3 -c "import json,sys; d=json.load(sys.stdin); \
print(json.dumps({'blocks': d['blocks']['total'], 'broadcasts': d['broadcasts'], \
'sounds': d['sounds'], 'procedures': d['procedures']}, indent=1)); \
assert not d['broadcasts']['neverSent'] and not d['broadcasts']['sentButNoReceiver']; \
assert not d['sounds']['neverPlayed']; \
assert not d['procedures']['neverCalled'] and not d['procedures']['danglingCalls']"

    echo
    echo "=== 4. structural audit: $FILE ==="
    # scratch-vm's minilog writes "vm warn" lines ahead of the JSON report
    (cd tests/headless && node harness.js "../../$FILE") | sed -n '/^{/,$p' |
        python3 -c "import sys,json; d=json.load(sys.stdin); \
print(json.dumps({'blocks': d['blocks'], 'assets': d['assets'], \
'problems': d['problems'], 'vmWarnings': d['vmWarnings'], \
'avgStepMs': d['avgStepMs'], 'failed': d.get('failed', False)}, indent=1)); \
sys.exit(1 if d.get('failed') else 0)"

    echo
    echo "=== 5. replay + menus + lifecycle: $FILE ==="
    for L in 1 2 3; do
        (cd tests/headless && node replay.js "../../$FILE" "../fixtures/level${L}_solution.json") |
            grep -E '^PASS|^FAIL'
    done
    (cd tests/headless && node menus.js "../../$FILE") | tail -1
    (cd tests/headless && node lifecycle.js "../../$FILE") |
        grep -E '^PASS:|^FAIL:'
done

echo
echo "all checks passed"
