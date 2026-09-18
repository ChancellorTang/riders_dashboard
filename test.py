"""Scratch script, superseded.

Fetching ESPN scores now lives in `riders/espn.py`, and the full
fetch -> store -> grade loop is `scripts/sync.py`:

    python3 scripts/sync.py            # live week
    python3 scripts/sync.py --all      # every week

This file previously had a The Odds API key hardcoded in it. That key is in
this repo's public git history (commit 9ab3efc) and must be rotated at
the-odds-api.com; removing it here does not un-publish it. Read keys from the
environment instead:

    os.environ["ODDS_API_KEY"]
"""
