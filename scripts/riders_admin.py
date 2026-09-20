#!/usr/bin/env python3
"""Manage the Discord id -> Rider mapping.

Writes both MongoDB *and* ``discord_bot/riders.json``, because the bot re-seeds
from that file on every startup — updating Mongo alone would be silently
reverted the next time the bot restarted.

    python3 scripts/riders_admin.py                        # show current state
    python3 scripts/riders_admin.py --set 1234... Chance   # map a real id
    python3 scripts/riders_admin.py --remove 1234...
    python3 scripts/riders_admin.py --discover             # unmapped posters
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import dotenv
    dotenv.load_dotenv(ROOT / ".env")
except ImportError:
    pass

from riders import db  # noqa: E402

RIDERS_JSON = ROOT.parent / "discord_bot" / "riders.json"

# Discord snowflakes are 17-19 digits. Anything else is a copied invite code,
# a channel name, or a truncated paste.
SNOWFLAKE = re.compile(r"^\d{17,19}$")

# The scaffold ids shipped in riders.json — all one repeated digit.
PLACEHOLDER = re.compile(r"^(\d)\1{16,18}$")


def load_json():
    if not RIDERS_JSON.exists():
        return {}
    return json.loads(RIDERS_JSON.read_text())


def save_json(mapping):
    comment = mapping.pop("_comment", None)
    out = {}
    if comment:
        out["_comment"] = comment
    out.update(mapping)
    RIDERS_JSON.write_text(json.dumps(out, indent=2) + "\n")


def show():
    mapping = load_json()
    rows = [(k, v) for k, v in mapping.items() if not k.startswith("_")]

    print(f"{RIDERS_JSON.relative_to(ROOT.parent)}")
    for uid, info in rows:
        tag = "  <- placeholder, still needs a real id" if PLACEHOLDER.match(uid) else ""
        print(f"  {uid:20} {info.get('name', '?'):8}{tag}")

    print("\nmongodb (riders collection)")
    for d in db.riders().find().sort("name", 1):
        tag = "  <- placeholder" if PLACEHOLDER.match(str(d["_id"])) else ""
        print(f"  {str(d['_id']):20} {str(d.get('name')):8}{tag}")

    stray = {str(d["_id"]) for d in db.riders().find()} - {k for k, _ in rows}
    if stray:
        print(f"\nin mongo but not in riders.json: {sorted(stray)}")
        print("  the bot will not re-create these; remove with --remove <id>")


def discover():
    """Ids that have posted picks but aren't mapped to anyone."""
    mapped = {str(d["_id"]) for d in db.riders().find()}
    seen = {}
    for p in db.picks().find({"discord_user_id": {"$ne": None}}):
        uid = str(p["discord_user_id"])
        if uid not in mapped:
            seen.setdefault(uid, []).append(p.get("raw_text") or p.get("game_id"))

    if not seen:
        print("no unmapped posters — every pick belongs to a known rider")
        return
    print("unmapped posters (picks exist but rider is null):")
    for uid, samples in seen.items():
        print(f"  {uid}   {len(samples)} pick(s), e.g. {samples[0]!r}")
        print(f"    map with: python3 scripts/riders_admin.py --set {uid} <Name>")


def set_rider(user_id, name, handle=None, replace=False):
    user_id = str(user_id).strip()
    if not SNOWFLAKE.match(user_id):
        sys.exit(f"'{user_id}' is not a Discord user id.\n"
                 "  Expected 17-19 digits. Turn on Developer Mode "
                 "(Settings > Advanced), then right-click the member > Copy User ID.")

    handle = handle or name.lower()
    mapping = load_json()

    # Swapping a placeholder for the real id is the normal case, so do it
    # without ceremony. Replacing one real id with another is not, so ask.
    for existing_id, info in list(mapping.items()):
        if existing_id.startswith("_") or existing_id == user_id:
            continue
        if str(info.get("name", "")).lower() == name.lower():
            if PLACEHOLDER.match(existing_id):
                del mapping[existing_id]
                db.riders().delete_one({"_id": existing_id})
                print(f"replaced placeholder {existing_id} for {name}")
            elif replace:
                del mapping[existing_id]
                db.riders().delete_one({"_id": existing_id})
                print(f"removed previous id {existing_id} for {name}")
            else:
                sys.exit(f"{name} is already mapped to {existing_id}.\n"
                         f"  Pass --replace to point {name} at {user_id} instead.")

    mapping[user_id] = {"name": name, "handle": handle}
    save_json(mapping)
    db.upsert_rider(user_id, name, handle)
    print(f"mapped {user_id} -> {name}  (riders.json + mongodb)")

    # Mongo can hold rows riders.json no longer mentions — editing the file by
    # hand leaves the old document behind. One name, one id, so clear the rest.
    stale = db.riders().delete_many({"name": name, "_id": {"$ne": user_id}})
    if stale.deleted_count:
        print(f"cleared {stale.deleted_count} stale mongo row(s) for {name}")

    # Adopt any picks this person posted before they were mapped.
    changed = db.picks().update_many(
        {"discord_user_id": user_id, "rider": None}, {"$set": {"rider": name}}
    ).modified_count
    if changed:
        print(f"backfilled {changed} earlier pick(s) to {name}")


def remove_rider(user_id):
    user_id = str(user_id).strip()
    mapping = load_json()
    existed = mapping.pop(user_id, None)
    save_json(mapping)
    gone = db.riders().delete_one({"_id": user_id}).deleted_count
    if existed or gone:
        print(f"removed {user_id}"
              + (f" ({existed.get('name')})" if existed else ""))
    else:
        print(f"{user_id} was not mapped")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", nargs=2, metavar=("DISCORD_ID", "NAME"))
    ap.add_argument("--handle")
    ap.add_argument("--replace", action="store_true",
                    help="Allow repointing a name that already has a real id")
    ap.add_argument("--remove", metavar="DISCORD_ID")
    ap.add_argument("--discover", action="store_true")
    args = ap.parse_args()

    if args.set:
        set_rider(args.set[0], args.set[1], args.handle, args.replace)
    elif args.remove:
        remove_rider(args.remove)
    elif args.discover:
        discover()
    else:
        show()


if __name__ == "__main__":
    main()
