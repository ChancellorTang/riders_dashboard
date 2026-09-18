#!/usr/bin/env python3
"""Run the site and the API together locally, the way Vercel wires them up.

Vercel maps ``api/picks.py`` onto ``/api/picks`` and serves everything else as
a static file. This reproduces that with the stdlib, so you can develop
against a real database without deploying or installing the Vercel CLI.

    export MONGODB_URI=...
    python3 scripts/dev_server.py
    # http://localhost:8000
"""

import argparse
import importlib.util
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "api"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(API_DIR))

from _common import JSONHandler  # noqa: E402


def load_endpoints():
    """Import each api/*.py and collect its ``handler`` class by route."""
    endpoints = {}
    for path in sorted(API_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"api_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if hasattr(module, "handler"):
            endpoints[f"/api/{path.stem}"] = module.handler
    return endpoints


class Router(JSONHandler, SimpleHTTPRequestHandler):
    """Serves the API from JSONHandler and everything else as a static file.

    The endpoint classes only ever touch ``self.path`` and the standard
    response machinery, so binding one's ``payload`` onto this connection is
    enough to run it exactly as Vercel would.
    """

    endpoints = {}

    def _endpoint(self):
        return self.endpoints.get(self.path.split("?")[0].rstrip("/"))

    def do_GET(self):
        target = self._endpoint()
        if target is None:
            return SimpleHTTPRequestHandler.do_GET(self)
        self.payload = target.payload.__get__(self)
        return JSONHandler.do_GET(self)

    def do_OPTIONS(self):
        if self._endpoint() is None:
            self.send_response(204)
            self.end_headers()
            return
        return JSONHandler.do_OPTIONS(self)

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s %s\n" % (self.command, self.path))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    Router.endpoints = load_endpoints()

    print(f"serving {ROOT}\n  http://localhost:{args.port}")
    for route in Router.endpoints:
        print(f"  http://localhost:{args.port}{route}")

    server = ThreadingHTTPServer(("", args.port), partial(Router, directory=str(ROOT)))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
