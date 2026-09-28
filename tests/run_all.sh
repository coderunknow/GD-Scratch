#!/usr/bin/env bash
# Full verification. Rebuilds both archives, then checks them three ways:
#   1. the Python level solver against its own reference physics
#   2. a structural audit of the .sb3 inside the real scratch-vm
#   3. the solved input schedule replayed frame by frame, plus the menus
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
    echo "=== 3. structural audit: $FILE ==="
    # scratch-vm's minilog writes "vm warn" lines ahead of the JSON report
    (cd tests/headless && node harness.js "../../$FILE") | sed -n '/^{/,$p' |
        python3 -c "import sys,json; d=json.load(sys.stdin); \
print(json.dumps({'blocks': d['blocks'], 'assets': d['assets'], \
'problems': d['problems'], 'vmWarnings': d['vmWarnings'], \
'avgStepMs': d['avgStepMs'], 'failed': d.get('failed', False)}, indent=1)); \
sys.exit(1 if d.get('failed') else 0)"

    echo
    echo "=== 4. replay + menus: $FILE ==="
    for L in 1 2 3; do
        (cd tests/headless && node replay.js "../../$FILE" "../fixtures/level${L}_solution.json") |
            grep -E '^PASS|^FAIL'
    done
    (cd tests/headless && node menus.js "../../$FILE") | tail -1
done

echo
echo "all checks passed"
