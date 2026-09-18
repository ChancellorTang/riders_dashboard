"""MongoDB access. Every reader and writer in the project goes through here.

Collections
    picks    one document per bet, keyed by ``_id`` (Discord message id)
    results  one document per week, holding that week's ESPN slate
    riders   discord user id -> display name

The client is created lazily and cached at module level, which is what you
want inside a serverless function: warm invocations reuse the connection pool
instead of opening a new one per request.
"""

import os
from functools import lru_cache

from pymongo import ASCENDING, MongoClient, UpdateOne

DB_NAME = os.environ.get("RIDERS_DB", "riders")
SEASON = int(os.environ.get("RIDERS_SEASON", "2026"))


@lru_cache(maxsize=1)
def client():
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError(
            "MONGODB_URI is not set. Copy it from Atlas > Connect > Drivers."
        )
    return MongoClient(uri, appname="riders", serverSelectionTimeoutMS=8000, tlsInsecure=True)


def db():
    return client()[DB_NAME]


def picks():
    return db()["picks"]


def results():
    return db()["results"]


def riders():
    return db()["riders"]


def ensure_indexes():
    """Safe to call repeatedly; Mongo ignores an index that already exists."""
    picks().create_index([("season", ASCENDING), ("week", ASCENDING)])
    picks().create_index([("status", ASCENDING)])
    picks().create_index([("rider", ASCENDING)])
    picks().create_index([("game_id", ASCENDING)])
    results().create_index([("season", ASCENDING), ("week", ASCENDING)], unique=True)


# ---------------------------------------------------------------- picks

def insert_pick(doc):
    """Insert unless the id is already present.

    Discord redelivers messages on gateway reconnect, so this has to be
    idempotent. Returns True when the document was actually new.
    """
    res = picks().update_one({"_id": doc["_id"]}, {"$setOnInsert": doc}, upsert=True)
    return res.upserted_id is not None


def get_pick(pick_id):
    return picks().find_one({"_id": str(pick_id)})


def set_status(pick_id, status):
    from .schema import now
    picks().update_one(
        {"_id": str(pick_id)},
        {"$set": {"status": status, "updated_at": now()}},
    )


def update_pick(pick_id, **fields):
    from .schema import now
    if not fields:
        return
    fields["updated_at"] = now()
    picks().update_one({"_id": str(pick_id)}, {"$set": fields})


def find_picks(season=None, week=None, status=None, rider=None):
    query = {"season": season if season is not None else SEASON}
    if week is not None:
        query["week"] = int(week)
    if status is not None:
        query["status"] = {"$in": list(status)} if isinstance(status, (list, tuple, set)) else status
    if rider is not None:
        query["rider"] = rider
    return list(picks().find(query).sort("posted_at", ASCENDING))


def record_results(graded):
    """Bulk-write grading output. ``graded`` is [(pick_id, result, units)].

    The third element is profit in units, not dollars.
    """
    from .schema import now
    if not graded:
        return 0
    stamp = now()
    ops = [
        UpdateOne(
            {"_id": str(pick_id)},
            {"$set": {
                "status": "graded", "result": result, "payout_units": payout_units,
                "graded_at": stamp, "updated_at": stamp,
            }},
        )
        for pick_id, result, payout_units in graded
    ]
    return picks().bulk_write(ops, ordered=False).modified_count


# ---------------------------------------------------------------- results

def save_week_results(season, week, games, updated_at=None):
    from .schema import now
    doc = {
        "season": int(season),
        "week": int(week),
        "updated_at": updated_at or now(),
        "games": games,
    }
    results().update_one(
        {"season": int(season), "week": int(week)}, {"$set": doc}, upsert=True
    )
    return doc


def get_week_results(season, week):
    return results().find_one({"season": int(season), "week": int(week)})


def games_by_id(season, week):
    doc = get_week_results(season, week)
    return {g["game_id"]: g for g in (doc or {}).get("games", [])}


def known_weeks(season=None):
    season = season if season is not None else SEASON
    weeks = results().distinct("week", {"season": season})
    weeks += picks().distinct("week", {"season": season})
    return sorted({int(w) for w in weeks})


# ---------------------------------------------------------------- riders

def rider_name(discord_user_id):
    doc = riders().find_one({"_id": str(discord_user_id)})
    return doc.get("name") if doc else None


def all_riders():
    return [d["name"] for d in riders().find().sort("name", ASCENDING)]


def roster(season=None):
    """Everyone who belongs on the board.

    The mapped riders, plus anyone who already has a pick. The union matters
    because a league member can have historical picks before their Discord id
    is mapped, and a freshly mapped member should appear with an empty row
    rather than waiting for their first bet.
    """
    season = season if season is not None else SEASON
    names = set(all_riders())
    names |= {n for n in picks().distinct("rider", {"season": season}) if n}
    return sorted(names)


def upsert_rider(discord_user_id, name, handle=None):
    riders().update_one(
        {"_id": str(discord_user_id)},
        {"$set": {"name": name, "handle": handle}},
        upsert=True,
    )
