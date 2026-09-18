"""Pull a week's NFL scoreboard from ESPN and normalise it.

This is the same conversion the original ``scripts/fetch_espn_results.py``
did, lifted out so the API, the cron job and the grader all share one
definition of what a game document looks like.

The macOS system Python often ships without a usable CA bundle, which is why
``certifi`` is preferred and ``--insecure`` still exists on the CLI wrapper.
"""

import json
import urllib.request

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
SEASON_TYPE_REGULAR = 2


def _opener(insecure=False, cacert=None):
    import ssl

    if insecure:
        ctx = ssl._create_unverified_context()
    else:
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=cacert or certifi.where())
        except ImportError:
            ctx = ssl.create_default_context(cafile=cacert) if cacert else ssl.create_default_context()
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def fetch_scoreboard(week=None, season=None, season_type=SEASON_TYPE_REGULAR,
                     insecure=False, cacert=None, timeout=20):
    """Raw ESPN payload. Omit ``week`` to get whatever ESPN considers current."""
    params = []
    if week is not None:
        params.append(f"week={int(week)}")
        params.append(f"seasontype={int(season_type)}")
    if season is not None:
        params.append(f"dates={int(season)}")
    url = SCOREBOARD + ("?" + "&".join(params) if params else "")

    # Deliberately no User-Agent override. ESPN's edge allows the default
    # client agents (Python-urllib, curl, requests) but 403s both custom
    # strings and spoofed browser ones, so the stock header is the safe pick.
    req = urllib.request.Request(url)
    with _opener(insecure, cacert).open(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return json.loads(resp.read().decode(charset))


def convert_event(event):
    """One ESPN event -> our game document."""
    comp = (event.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})

    home_abbr = (home.get("team") or {}).get("abbreviation") or ""
    away_abbr = (away.get("team") or {}).get("abbreviation") or ""

    status_type = (comp.get("status") or {}).get("type") or {}
    state = status_type.get("state")
    if status_type.get("completed"):
        status = "final"
    elif state == "in":
        status = "in_progress"
    else:
        status = "pending"

    return {
        "game_id": f"{away_abbr}@{home_abbr}",
        "away_team": away_abbr,
        "home_team": home_abbr,
        "away_score": int(away.get("score") or 0),
        "home_score": int(home.get("score") or 0),
        "start_time": comp.get("date") or event.get("date"),
        "status": status,
        "detail": status_type.get("shortDetail"),
    }


def week_games(week=None, season=None, **kwargs):
    """Return ``(season, week, games)`` for a scoreboard request.

    ESPN echoes back the season and week it actually served, so passing
    ``week=None`` is a reliable way to ask "what week is it right now?".
    """
    payload = fetch_scoreboard(week=week, season=season, **kwargs)

    served_week = ((payload.get("week") or {}).get("number")) or week
    served_season = ((payload.get("season") or {}).get("year")) or season

    games = []
    for event in payload.get("events") or []:
        try:
            game = convert_event(event)
        except Exception:
            continue
        if game["away_team"] and game["home_team"]:
            games.append(game)

    games.sort(key=lambda g: (g.get("start_time") or "", g["game_id"]))
    return int(served_season), int(served_week), games


def current_week(**kwargs):
    season, week, _ = week_games(**kwargs)
    return season, week
