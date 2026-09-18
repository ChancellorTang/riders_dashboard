"""GET /api/results?week=2&season=2026 — the ESPN slate and scores for a week."""

from riders.webapi import JSONHandler, season_of, week_of
from riders import db


class handler(JSONHandler):
    def payload(self, query):
        season = season_of(query)
        week = week_of(query)
        if week is None:
            weeks = db.known_weeks(season)
            week = weeks[-1] if weeks else 1

        doc = db.get_week_results(season, week) or {}
        return {
            "season": season,
            "week": week,
            "updated_at": doc.get("updated_at"),
            "games": doc.get("games", []),
        }
