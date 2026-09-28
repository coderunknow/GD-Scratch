#!/usr/bin/env python3
"""Serve the browser preview of GD-Scratch.

    python3 preview/serve.py [--port 8600]

Everything the page needs is served from inside the repository, so the preview
works without network access:

* the player itself (``preview/index.html``, ``preview/player.js``),
* the four scratch-* browser bundles, read straight out of
  ``tests/headless/node_modules`` (run ``npm ci`` there first),
* the built ``dist/*.sb3`` archives.

Nothing is copied or committed: ``node_modules`` stays out of git and this
script just points at it.
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import sys

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NODE_MODULES = os.path.join(ROOT, "tests", "headless", "node_modules")

# URL -> file on disk. The scratch-* packages only publish these paths, so the
# mapping is spelled out rather than guessed.
VENDOR = {
    "/vendor/scratch-vm.js":
        "scratch-vm/dist/web/scratch-vm.js",
    "/vendor/scratch-render.js":
        "scratch-render/dist/web/scratch-render.min.js",
    "/vendor/scratch-storage.js":
        "scratch-storage/dist/web/scratch-storage.min.js",
    "/vendor/scratch-audio.js":
        "scratch-audio/dist.js",
}


def resolve(path: str) -> str | None:
    """Map a request path to a real file, or None if it is not one we serve."""
    if path in ("/", "/index.html"):
        return os.path.join(HERE, "index.html")
    if path == "/player.js":
        return os.path.join(HERE, "player.js")
    if path == "/vendor/scratch-audio-shim.js":
        return os.path.join(HERE, "scratch-audio-shim.js")
    if path in VENDOR:
        return os.path.join(NODE_MODULES, VENDOR[path])
    if path.startswith("/dist/") and path.endswith(".sb3"):
        return os.path.join(ROOT, path.lstrip("/"))
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "GDScratchPreview/1.0"

    def log_message(self, fmt, *args):  # keep the log to one line per request
        sys.stderr.write("%s %s\n" % (self.command, self.path))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        target = resolve(path)
        if target is None or not os.path.isfile(target):
            hint = ""
            if path in VENDOR:
                hint = (" (run `npm ci` in tests/headless to install the "
                        "scratch-* bundles)")
            self.send_error(404, f"no such file: {path}{hint}")
            return
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        try:
            with open(target, "rb") as handle:
                body = handle.read()
        except OSError as exc:
            self.send_error(500, str(exc))
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    do_HEAD = do_GET


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8600)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    missing = [u for u in VENDOR
               if not os.path.isfile(os.path.join(NODE_MODULES, VENDOR[u]))]
    if missing:
        print("warning: these bundles are missing -- run `npm ci` in "
              "tests/headless:", ", ".join(missing), file=sys.stderr)

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"GD-Scratch preview on http://{args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
