"""GET /api/standings?season=2026&week=2 — leaderboard, season-wide or one week."""

from riders.webapi import JSONHandler, season_of, week_of
from riders import db, grading


class handler(JSONHandler):
    def payload(self, query):
        season, week = season_of(query), week_of(query)
        rows = grading.standings(
            db.find_picks(season=season, week=week), db.roster(season)
        )
        return {"season": season, "week": week, "standings": rows}
