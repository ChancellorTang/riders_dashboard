#!/usr/bin/env python3
"""
fetch_odds.py

Fetch NFL game spreads and totals for a given week from The Odds API.

Usage:
  python3 scripts/fetch_odds.py --week 1 --api-key YOUR_API_KEY

Writes to `data/week_<week>/odds.json` with game spreads and totals.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
import shutil
import argparse
import sys

try:
    import requests
except ImportError:
    requests = None


ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"

# NFL 2026 regular season dates (adjust as needed)
SEASON_START = datetime(2026, 9, 6)
WEEK_STARTS = {
    1: datetime(2026, 9, 6),
    2: datetime(2026, 9, 13),
    3: datetime(2026, 9, 20),
    4: datetime(2026, 9, 27),
    5: datetime(2026, 10, 4),
    6: datetime(2026, 10, 11),
    7: datetime(2026, 10, 18),
    8: datetime(2026, 10, 25),
    9: datetime(2026, 11, 1),
    10: datetime(2026, 11, 8),
    11: datetime(2026, 11, 15),
    12: datetime(2026, 11, 22),
    13: datetime(2026, 11, 29),
    14: datetime(2026, 12, 6),
    15: datetime(2026, 12, 13),
    16: datetime(2026, 12, 20),
    17: datetime(2026, 12, 27),
    18: datetime(2027, 1, 3),
}

# Team name to abbreviation mapping
TEAM_ABBR = {
    "Arizona Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}


def fetch_odds_for_week(week, api_key, insecure=False):
    """Fetch odds from The Odds API for a given week."""
    if not requests:
        print("requests library required. Install with: pip install requests", file=sys.stderr)
        sys.exit(1)

    start = WEEK_STARTS.get(week)
    if not start:
        print(f"Week {week} not found in season map", file=sys.stderr)
        return []

    # Query date range: week start to 7 days later
    date_from = start.isoformat() + "Z"
    date_to = (start + timedelta(days=7)).isoformat() + "Z"

    params = {
        "regions": "us",
        "markets": "spreads,totals",
        "oddsFormat": "american",
        "dateFrom": date_from,
        "dateTo": date_to,
        "apiKey": api_key,
    }

    opts = {"params": params, "timeout": 15}
    if insecure:
        opts["verify"] = False

    try:
        resp = requests.get(ODDS_API_URL, **opts)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Failed to fetch odds from The Odds API: {e}", file=sys.stderr)
        return []


def convert_to_game_odds(events):
    """Convert The Odds API response to a simpler game odds structure with team abbreviations."""
    games = []
    for event in events:
        away = event.get("away_team", "")
        home = event.get("home_team", "")
        away_abbr = TEAM_ABBR.get(away, away)
        home_abbr = TEAM_ABBR.get(home, home)
        game_id = f"{away_abbr}@{home_abbr}"
        start_time = event.get("commence_time")

        spreads = {}
        totals = {}

        for bm in event.get("bookmakers", []):
            for market in bm.get("markets", []):
                market_key = market.get("key")
                if market_key == "spreads":
                    for outcome in market.get("outcomes", []):
                        team = outcome.get("name")
                        team_abbr = TEAM_ABBR.get(team, team)
                        point = outcome.get("point")
                        price = outcome.get("price")
                        spreads.setdefault(team_abbr, {"point": point, "odds": price})

                elif market_key == "totals":
                    for outcome in market.get("outcomes", []):
                        ou = outcome.get("name")
                        point = outcome.get("point")
                        price = outcome.get("price")
                        totals.setdefault(ou, {"point": point, "odds": price})

        games.append({
            "game_id": game_id,
            "away_team": away_abbr,
            "home_team": home_abbr,
            "start_time": start_time,
            "spreads": spreads,
            "totals": totals,
        })

    return games


def ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)


def backup(path: Path):
    if path.exists():
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        bak = path.with_name(path.name + ".bak." + ts)
        shutil.copy2(path, bak)
        print(f"Backed up {path} -> {bak}")


def main():
    parser = argparse.ArgumentParser(description="Fetch NFL odds for a given week from The Odds API")
    parser.add_argument("--week", type=int, required=True, help="Week number")
    parser.add_argument("--api-key", required=True, help="The Odds API key")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1], help="Repo root")
    parser.add_argument("--insecure", action="store_true", help="Do not verify TLS certificates")

    args = parser.parse_args()
    repo = Path(args.repo_root)

    print(f"Fetching odds for week {args.week}...")
    events = fetch_odds_for_week(args.week, args.api_key, insecure=args.insecure)

    if not events:
        print("No events found for week", args.week, file=sys.stderr)
        sys.exit(1)

    games = convert_to_game_odds(events)

    out = {
        "week": args.week,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "games": games,
    }

    dest_dir = repo / f"data/week_{args.week}"
    ensure_dir(dest_dir)
    dest_file = dest_dir / "odds.json"

    backup(dest_file)

    with open(dest_file, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote {dest_file} with {len(games)} games")


if __name__ == "__main__":
    main()
