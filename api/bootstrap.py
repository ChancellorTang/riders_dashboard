"""GET /api/bootstrap — everything the dashboard needs in one round trip.

The board polls on an interval, so collapsing weeks + picks + results +
standings into a single request keeps it to one Atlas round trip per refresh
instead of four.
"""

from riders.webapi import JSONHandler, public_pick, season_of, week_of
from riders import db, grading


class handler(JSONHandler):
    def payload(self, query):
        season = season_of(query)
        weeks = db.known_weeks(season) or [1]
        week = week_of(query) or weeks[-1]

        all_picks = db.find_picks(season=season)
        visible = [p for p in all_picks if p.get("status") != "rejected"]
        riders = db.roster(season)

        results = db.get_week_results(season, week) or {}

        return {
            "season": season,
            "weeks": weeks,
            "current_week": week,
            "riders": riders,
            "picks": [public_pick(p) for p in visible],
            "results": {
                "week": week,
                "updated_at": results.get("updated_at"),
                "games": results.get("games", []),
            },
            "standings": {
                "season": grading.standings(visible, riders),
                "week": grading.standings(
                    [p for p in visible if p.get("week") == week], riders),
            },
        }
