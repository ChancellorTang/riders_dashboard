"""Shared helpers for the HTTP API.

Each endpoint in ``api/`` is a tiny ``BaseHTTPRequestHandler`` — the interface
Vercel's Python runtime expects — so the boilerplate for JSON, CORS, caching
and error handling lives here instead of in every file.

This deliberately lives inside the ``riders`` package rather than as
``api/_common.py``. Vercel loads each function by file path with only the task
root on ``sys.path``, so a sibling import between two files in ``api/`` raises
ModuleNotFoundError at runtime even though it resolves locally. The package is
at the task root, so importing from here always works.
"""

import json
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from . import db

# Browsers poll this every few seconds. A short shared-cache window keeps
# Atlas well inside the free tier's 100 ops/sec without the board ever looking
# stale, and stale-while-revalidate hides the refresh latency.
CACHE_CONTROL = "public, max-age=5, s-maxage=10, stale-while-revalidate=30"


def season_of(query):
    value = query.get("season", [None])[0]
    return int(value) if value else db.SEASON


def week_of(query):
    value = query.get("week", [None])[0]
    if value in (None, "", "all"):
        return None
    return int(value)


class JSONHandler(BaseHTTPRequestHandler):
    """Subclass and implement ``payload(query)``."""

    def payload(self, query):  # pragma: no cover - overridden
        raise NotImplementedError

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        try:
            body = self.payload(query)
            status = 200
        except ValueError as e:
            body, status = {"error": str(e)}, 400
        except Exception as e:
            traceback.print_exc()
            body, status = {"error": f"{type(e).__name__}: {e}"}, 500

        self._send(status, body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, status, body):
        raw = json.dumps(body, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", CACHE_CONTROL if status == 200 else "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        # Vercel captures stderr; the default access log is just noise.
        pass


def public_pick(doc):
    """Strip a pick down to what the dashboard needs.

    Discord user ids and raw message text stay server-side — the board is a
    public URL and neither of those belongs on it.
    """
    return {
        "id": doc.get("_id"),
        "week": doc.get("week"),
        "player": doc.get("rider"),
        "game": doc.get("game_id"),
        "market": doc.get("market"),
        "bet": doc.get("bet"),
        "line": doc.get("line"),
        "odds": doc.get("odds"),
        "units": doc.get("units"),
        "status": doc.get("status"),
        "result": doc.get("result"),
        "payout_units": doc.get("payout_units"),
        "posted_at": doc.get("posted_at"),
    }
