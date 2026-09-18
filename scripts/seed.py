#!/usr/bin/env python3
"""One-time migration: the old JSON files into MongoDB.

The four profile files disagree with each other about shape — chance.json and
kyle.json store ``weeks`` as a list, jay.json and joe.json as a dict keyed by
week number. Both are read here and normalised away for good.

The league scores in units, and none of the historical picks recorded a size,
so each one seeds at 1 unit. Override with ``--units`` if the old picks should
count for more.

    python3 scripts/seed.py
    python3 scripts/seed.py --dry-run
"""

import argparse
import json
import sys
from pathlib import Path
import dotenv

dotenv.load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from riders import db, schema  # noqa: E402

PROFILES = ROOT / "data" / "profiles"
DATA = ROOT / "data"
BOT_RIDERS = ROOT.parent / "discord_bot" / "riders.json"


def iter_weeks(profile):
    """Yield week entries from either profile shape."""
    weeks = profile.get("weeks")
    if isinstance(weeks, dict):
        weeks = list(weeks.values())
    return weeks or []


def load_profiles(season, units):
    docs = []
    for path in sorted(PROFILES.glob("*.json")):
        profile = json.loads(path.read_text())
        player = profile.get("player") or path.stem.title()

        for entry in iter_weeks(profile):
            week = int(entry.get("week") or 1)
            for i, pick in enumerate(entry.get("picks") or []):
                market = schema.normalize_market(pick.get("type")) or "side"
                bet = schema.normalize_bet(market, pick.get("bet"))
                docs.append(schema.build(
                    # Deterministic id so re-running the seed cannot duplicate.
                    pick_id=f"seed-{path.stem}-w{week}-{i}",
                    week=week,
                    season=season,
                    rider=player,
                    source="seed",
                    market=market,
                    bet=bet,
                    line=pick.get("spread"),
                    odds=pick.get("odds"),
                    units=pick.get("units", units),
                    game_id=pick.get("game"),
                    event_raw=pick.get("game"),
                    confidence=1.0,
                    status="confirmed",
                    posted_at=pick.get("locked_at") or entry.get("locked_at"),
                ))
    return docs


def load_results(season):
    out = []
    for path in sorted(DATA.glob("week_*/results.json")):
        payload = json.loads(path.read_text())
        week = int(payload.get("week") or path.parent.name.split("_")[-1])
        out.append((week, payload.get("games") or [], payload.get("updated_at")))
    return out


def load_riders():
    if not BOT_RIDERS.exists():
        return []
    mapping = json.loads(BOT_RIDERS.read_text())
    return [(uid, info["name"], info.get("handle"))
            for uid, info in mapping.items() if not uid.startswith("_")]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=db.SEASON)
    ap.add_argument("--units", type=float, default=1.0,
                    help="Unit size for historical picks (they recorded none)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    picks = load_profiles(args.season, args.units)
    results = load_results(args.season)
    riders = load_riders()

    print(f"profiles : {len(picks)} pick(s)")
    for doc in picks:
        flag = "" if schema.is_gradable(doc) else "   <- not gradable"
        line = "" if doc["line"] is None else format(doc["line"], "+g")
        print(f"  {doc['rider']:8} w{doc['week']} {str(doc['game_id']):10} "
              f"{doc['bet']} {line}{flag}")
    print(f"results  : {len(results)} week(s) — " +
          ", ".join(f"w{w} ({len(g)} games)" for w, g, _ in results))
    print(f"riders   : {len(riders)} mapped")

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    db.ensure_indexes()

    new = sum(1 for doc in picks if db.insert_pick(doc))
    for week, games, updated in results:
        db.save_week_results(args.season, week, games, updated)
    for uid, name, handle in riders:
        db.upsert_rider(uid, name, handle)

    print(f"\ninserted {new} new pick(s) ({len(picks) - new} already present)")
    print(f"wrote {len(results)} week(s) of results")
    print("\nNow run:  python3 scripts/sync.py --all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
