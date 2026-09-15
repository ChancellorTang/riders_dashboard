#!/usr/bin/env python3
"""
fetch_espn_results.py

Fetch ESPN scoreboard for a given week and convert to the app's `results.json` shape.

Usage:
  python3 scripts/fetch_espn_results.py --week 1

Writes to `data/week_<week>/results.json` and backs up an existing file.
"""

import json
from pathlib import Path
from datetime import datetime
import shutil
import argparse
import sys
try:
    import requests
except Exception:
    requests = None

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?week={week}"


def fetch_json(url, insecure=False, cacert=None):
    if requests:
        opts = {"timeout": 15}
        if insecure:
            opts["verify"] = False
        elif cacert:
            opts["verify"] = cacert
        resp = requests.get(url, **opts)
        resp.raise_for_status()
        return resp.json()

    # fallback to urllib (may raise SSL errors on some macOS Pythons)
    from urllib.request import urlopen
    with urlopen(url) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return json.loads(resp.read().decode(charset))


def ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)


def backup(path: Path):
    if path.exists():
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        bak = path.with_name(path.name + ".bak." + ts)
        shutil.copy2(path, bak)
        print(f"Backed up {path} -> {bak}")


def convert_event_to_game(event):
    # competitions list usually has one competition
    comp = event.get("competitions", [])[0]
    competitors = comp.get("competitors", [])
    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)

    home_abbr = (home.get("team", {}) or {}).get("abbreviation") if home else None
    away_abbr = (away.get("team", {}) or {}).get("abbreviation") if away else None

    home_score = int(home.get("score") or 0) if home else 0
    away_score = int(away.get("score") or 0) if away else 0

    start_time = comp.get("date") or comp.get("startDate") or event.get("date")

    # Determine status
    status_obj = comp.get("status") or {}
    t = status_obj.get("type") or {}
    completed = t.get("completed") if isinstance(t, dict) else None
    status = "final" if completed else "pending"

    gid = f"{away_abbr or ''}@{home_abbr or ''}".strip("@")

    return {
        "game_id": gid,
        "away_team": away_abbr or "",
        "start_time": start_time,
        "home_team": home_abbr or "",
        "home_score": home_score,
        "away_score": away_score,
        "status": status
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", type=int, required=True, help="Week number to fetch")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1], help="Repo root")
    parser.add_argument("--url", help="Override ESPN URL template (use {week} in it)")
    parser.add_argument("--insecure", action="store_true", help="Do not verify remote TLS certificates (insecure)")
    parser.add_argument("--cacert", help="Path to a CA bundle file to use for certificate verification")
    args = parser.parse_args()

    repo = Path(args.repo_root)
    url = (args.url or ESPN_URL).format(week=args.week)
    print(f"Fetching ESPN scoreboard for week {args.week} from: {url}")

    try:
        payload = fetch_json(url, insecure=args.insecure, cacert=args.cacert)
    except Exception as e:
        print("Failed to fetch ESPN JSON:", e, file=sys.stderr)
        if not requests:
            print("Note: requests library not available; install with: pip install requests")
        sys.exit(2)

    events = payload.get("events") or []
    games = []
    for ev in events:
        try:
            g = convert_event_to_game(ev)
            games.append(g)
        except Exception as e:
            print("Skipping event due to error:", e)

    out = {
        "week": args.week,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "games": games
    }

    dest_dir = repo / f"data/week_{args.week}"
    ensure_dir(dest_dir)
    dest_file = dest_dir / "results.json"

    backup(dest_file)

    with open(dest_file, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote {dest_file} with {len(games)} games")


if __name__ == "__main__":
    main()
