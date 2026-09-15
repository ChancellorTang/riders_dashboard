#!/usr/bin/env python3
"""
update_results.py

Simple script to update or replace a week's results.json file.

Usage:
  python3 scripts/update_results.py --source results_source.json --week 1
  python3 scripts/update_results.py --url https://example.com/week1.json --week 1 --merge

Behavior:
- If --url is provided, the script fetches JSON from the URL.
- If --source is provided, the script reads the local file.
- If --merge is set, the script will merge games arrays by `game_id`.
- The destination file is `data/week_<week>/results.json`. A timestamped backup is created.
"""

import argparse
import json
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime
from urllib.request import urlopen


def load_json_from_url(url):
    with urlopen(url) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return json.loads(resp.read().decode(charset))


def load_json_from_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_week_dir(root, week):
    d = root / f"data/week_{week}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def backup_file(path):
    if path.exists():
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        bak = path.with_name(path.name + ".bak." + ts)
        shutil.copy2(path, bak)
        print(f"Backed up {path} to {bak}")


def merge_games(existing, incoming):
    # Map by game_id
    out = {g.get("game_id"): g for g in existing}
    for g in incoming:
        gid = g.get("game_id")
        if not gid:
            # if missing id, try to infer from away@home
            gid = f"{g.get('away_team','')}@{g.get('home_team','')}"
            g["game_id"] = gid
        out[gid] = g
    return list(out.values())


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source", help="Local JSON file to use as source")
    group.add_argument("--url", help="URL to fetch JSON from")
    parser.add_argument("--week", type=int, required=True, help="Week number to update")
    parser.add_argument("--merge", action="store_true", help="Merge incoming games into existing results.json by game_id")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1], help="Path to repo root (defaults to project root)")

    args = parser.parse_args()
    repo_root = Path(args.repo_root)
    dest_dir = ensure_week_dir(repo_root, args.week)
    dest_file = dest_dir / "results.json"

    try:
        if args.url:
            print(f"Fetching from URL: {args.url}")
            payload = load_json_from_url(args.url)
        else:
            print(f"Reading source file: {args.source}")
            payload = load_json_from_file(args.source)
    except Exception as e:
        print("Failed to load source:", e, file=sys.stderr)
        sys.exit(2)

    if not isinstance(payload, dict) or "games" not in payload:
        print("Source JSON must be an object with a top-level 'games' array", file=sys.stderr)
        sys.exit(3)

    existing = []
    if dest_file.exists():
        try:
            existing = load_json_from_file(dest_file)
            if isinstance(existing, dict):
                existing = existing.get("games", [])
        except Exception:
            existing = []

    if args.merge and existing:
        merged_games = merge_games(existing, payload.get("games", []))
        out = {"week": args.week, "updated_at": datetime.utcnow().isoformat() + "Z", "games": merged_games}
    else:
        out = payload
        # ensure week key
        out.setdefault("week", args.week)
        out.setdefault("updated_at", datetime.utcnow().isoformat() + "Z")

    # backup existing file
    backup_file(dest_file)

    with open(dest_file, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote {dest_file}")


if __name__ == "__main__":
    main()
