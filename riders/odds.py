"""Market lines from The Odds API, used to fact-check what riders claim.

Someone posting "Ravens -3.5" when the real line is -7.5 is either misreading
their slip or remembering last week. Checking against the market catches that
at intake, while they are still in the channel to fix it.

Budget matters here. The free tier is 500 credits a month and a spreads+totals
request costs 2, so roughly 240 calls. Nothing calls this module per message:
lines are fetched on a timer, cached in Mongo, and read from there.

Consensus is the median across books rather than one book's number, so a rider
quoting FanDuel is not flagged for disagreeing with DraftKings.
"""

import json
import os
import ssl
import statistics
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import teams

API_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"

# How far a stated line may sit from the market before the rider is asked.
# Half a point is noise between books; two points is a different bet.
TOLERANCE = float(os.environ.get("RIDERS_LINE_TOLERANCE", "1.5"))

# Lines drift slowly outside of injury news, and the credit budget is small.
STALE_AFTER = timedelta(minutes=int(os.environ.get("RIDERS_ODDS_TTL_MIN", "60")))


class OddsError(RuntimeError):
    pass


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch(api_key=None, timeout=20):
    """Raw events from The Odds API. Returns ``(events, credits_remaining)``."""
    api_key = api_key or os.environ.get("ODDS_API_KEY")
    if not api_key:
        raise OddsError("ODDS_API_KEY is not set")

    query = urllib.parse.urlencode({
        "regions": "us",
        "markets": "spreads,totals",
        "oddsFormat": "american",
        "apiKey": api_key,
    })
    req = urllib.request.Request(f"{API_URL}?{query}")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            events = json.loads(resp.read().decode())
            remaining = resp.headers.get("x-requests-remaining")
            return events, (int(remaining) if remaining else None)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        raise OddsError(f"Odds API HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise OddsError(f"Cannot reach the Odds API: {e.reason}") from e


def _median(values):
    """Consensus line, snapped to the half point.

    A median across eight books lands on values like 8.75 or 46.17, which no
    book would ever post. Betting lines move in half points, so rounding to
    one keeps the number we quote back to a rider credible.
    """
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return None
    return round(statistics.median(clean) * 2) / 2


def convert(events, slate=None):
    """Normalise events into ``{game_id: {spreads, total, books}}``.

    Team names go through ``teams.resolve`` rather than a local lookup table,
    which is what keeps Washington as ESPN's ``WSH`` instead of ``WAS`` — a
    mismatch there would silently prevent every Commanders line from matching.

    ``slate`` restricts the result to one week's games; the API returns every
    upcoming event regardless of week.
    """
    out = {}
    for event in events:
        away = teams.resolve(event.get("away_team"))
        home = teams.resolve(event.get("home_team"))
        if not away or not home:
            continue

        game_id = teams.game_id(away, home)
        if slate and game_id not in slate:
            continue

        spread_points = {away: [], home: []}
        total_points = []
        books = 0

        for book in event.get("bookmakers", []):
            books += 1
            for market in book.get("markets", []):
                if market.get("key") == "spreads":
                    for outcome in market.get("outcomes", []):
                        abbr = teams.resolve(outcome.get("name"))
                        if abbr in spread_points:
                            spread_points[abbr].append(outcome.get("point"))
                elif market.get("key") == "totals":
                    for outcome in market.get("outcomes", []):
                        if str(outcome.get("name", "")).lower() == "over":
                            total_points.append(outcome.get("point"))

        out[game_id] = {
            "game_id": game_id,
            "away_team": away,
            "home_team": home,
            "start_time": event.get("commence_time"),
            "spreads": {t: _median(pts) for t, pts in spread_points.items()},
            "total": _median(total_points),
            "books": books,
        }
    return out


def is_stale(doc):
    """Whether a stored odds document is old enough to refetch."""
    if not doc or not doc.get("updated_at"):
        return True
    try:
        stamp = datetime.fromisoformat(str(doc["updated_at"]).replace("Z", "+00:00"))
    except ValueError:
        return True
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - stamp > STALE_AFTER


def market_line(lines, game_id, market, bet):
    """The consensus number for one pick, or None if the market is unknown.

    For a side this is the spread from the bet team's perspective, matching how
    ``line`` is stored everywhere else.
    """
    game = (lines or {}).get(game_id)
    if not game:
        return None
    if market == "side":
        return (game.get("spreads") or {}).get(bet)
    if market == "total":
        return game.get("total")
    return None   # a moneyline has no line to check


def check(stated, market, tolerance=None):
    """Compare a stated line against the market.

    Returns ``(verdict, market_line)`` where verdict is one of:
        ``ok``       within tolerance, or nothing to compare against
        ``off``      outside tolerance; the market number should replace it
    """
    tolerance = TOLERANCE if tolerance is None else tolerance
    if stated is None or market is None:
        return "ok", market
    return ("ok" if abs(float(stated) - float(market)) <= tolerance else "off"), market
