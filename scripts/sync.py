#!/usr/bin/env python3
"""Pull ESPN scores into Mongo and grade every pick they settle.

This is the whole backend loop. Run it on a schedule (GitHub Actions does it
every 15 minutes during the season) and the dashboard takes care of itself.

    python3 scripts/sync.py                 # live week
    python3 scripts/sync.py --week 1        # a specific week
    python3 scripts/sync.py --all           # every week with picks or results
    python3 scripts/sync.py --dry-run       # show what would change
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Convenience for local runs so you don't have to source .env by hand.
# Optional on purpose: CI and Vercel inject real environment variables and
# have no .env, so a hard import would break every scheduled run the moment
# python-dotenv wasn't installed. Explicit path so it works from any cwd.
try:
    import dotenv
    dotenv.load_dotenv(ROOT / ".env")
except ImportError:
    pass

from riders import db, espn, grading, odds  # noqa: E402


def refresh_odds(season, week, slate, dry_run=False, force=False):
    """Pull market lines if the cached ones have aged out.

    Gated on staleness because the free Odds API tier is 500 credits a month
    and each call costs 2. At the default one-hour TTL this is well inside
    budget even running every 15 minutes.
    """
    stored = db.get_week_odds(season, week)
    if not force and not odds.is_stale(stored):
        print(f"  odds: cached ({len(stored.get('lines') or {})} games), still fresh")
        return

    try:
        events, remaining = odds.fetch()
    except odds.OddsError as e:
        print(f"  odds: skipped — {e}")
        return

    lines = odds.convert(events, slate=slate)
    if not dry_run:
        db.save_week_odds(season, week, lines, remaining)
    print(f"  odds: refreshed {len(lines)}/{len(slate)} games "
          f"({remaining} credits left)")


def sync_week(week=None, dry_run=False, skip_odds=False, **fetch_kwargs):
    season, resolved_week, games = espn.week_games(week=week, **fetch_kwargs)

    finals = sum(1 for g in games if g["status"] == "final")
    live = sum(1 for g in games if g["status"] == "in_progress")
    print(f"week {resolved_week}: {len(games)} games "
          f"({finals} final, {live} in progress)")

    if not dry_run:
        db.save_week_results(season, resolved_week, games)

    if not skip_odds:
        refresh_odds(season, resolved_week,
                     [g["game_id"] for g in games], dry_run)

    results_by_game = {g["game_id"]: g for g in games}
    picks = db.find_picks(season=season, week=resolved_week,
                          status=["confirmed", "graded"])

    graded = []
    for pick, result, profit in grading.grade_all(picks, results_by_game):
        graded.append((pick["_id"], result, profit))
        print(f"  {pick.get('rider') or '?':8} {pick.get('game_id'):10} "
              f"{pick.get('bet')} {pick.get('line') if pick.get('line') is not None else '':>6} "
              f"-> {result:5} {profit:+.2f}u")

    if graded and not dry_run:
        db.record_results(graded)

    ungraded = [p for p in picks
                if p.get("status") == "confirmed"
                and p["_id"] not in {g[0] for g in graded}]
    if ungraded:
        print(f"  {len(ungraded)} pick(s) still open")

    return season, resolved_week, len(graded)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=int, help="Week to sync (default: the live week)")
    ap.add_argument("--all", action="store_true", help="Sync every known week")
    ap.add_argument("--dry-run", action="store_true", help="Report without writing")
    ap.add_argument("--skip-odds", action="store_true",
                    help="Do not touch the Odds API (saves credits)")
    ap.add_argument("--force-odds", action="store_true",
                    help="Refresh market lines even if the cache is fresh")
    ap.add_argument("--insecure", action="store_true",
                    help="Skip TLS verification (macOS system Python workaround)")
    ap.add_argument("--cacert", help="Path to a CA bundle")
    args = ap.parse_args()

    fetch_kwargs = {"insecure": args.insecure, "cacert": args.cacert}

    if not os.environ.get("MONGODB_URI"):
        print("MONGODB_URI is not set.", file=sys.stderr)
        return 2

    db.ensure_indexes()

    if args.all:
        weeks = db.known_weeks() or [1]
        print(f"syncing weeks {weeks}")
        total = 0
        for week in weeks:
            # Only the live week needs lines; past weeks are already graded.
            _, _, n = sync_week(week, args.dry_run,
                                skip_odds=(args.skip_odds or week != weeks[-1]),
                                **fetch_kwargs)
            total += n
        print(f"\ngraded {total} pick(s) across {len(weeks)} week(s)")
    else:
        if args.force_odds:
            odds.STALE_AFTER = odds.timedelta(0)
        _, _, n = sync_week(args.week, args.dry_run,
                            skip_odds=args.skip_odds, **fetch_kwargs)
        print(f"\ngraded {n} pick(s)")

    if args.dry_run:
        print("(dry run — nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
