"""GET /api/picks?week=2&season=2026 — picks for a week (omit week for all)."""

from _common import JSONHandler, public_pick, season_of, week_of
from riders import db


class handler(JSONHandler):
    def payload(self, query):
        season, week = season_of(query), week_of(query)
        picks = db.find_picks(season=season, week=week)
        visible = [p for p in picks if p.get("status") != "rejected"]
        return {
            "season": season,
            "week": week,
            "count": len(visible),
            "picks": [public_pick(p) for p in visible],
        }
