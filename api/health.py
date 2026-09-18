"""GET /api/health — is the function warm and can it reach Atlas?"""

from _common import JSONHandler
from riders import db


class handler(JSONHandler):
    def payload(self, query):
        db.client().admin.command("ping")
        season = db.SEASON
        return {
            "ok": True,
            "season": season,
            "weeks": db.known_weeks(season),
            "picks": db.picks().count_documents({"season": season}),
            "riders": db.roster(season),
        }
