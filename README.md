# The Riders Picks Challenge

A weekly NFL picks league for four people. Picks arrive through a Discord bot,
get stored in MongoDB, and are graded automatically against ESPN's scoreboard.
The board is a public web page that updates itself.

```
 #picks channel          Ollama            MongoDB Atlas        Vercel
 ───────────────         ──────            ─────────────        ──────
 "2u BAL -3.5    ──▶  extract &  ──▶  picks collection  ──▶  /api/bootstrap
  at -110"             normalise              ▲                    │
                                              │                    ▼
                    ESPN scoreboard ──▶  scripts/sync.py      index.html
                    (every 15 min)         grade picks        (the board)
```

## What lives where

| path | what it is |
|---|---|
| `index.html`, `app.js`, `styles.css` | the board |
| `api/*.py` | Vercel serverless functions, one file per route |
| `riders/` | shared core — team resolution, pick schema, grading, ESPN, Mongo |
| `scripts/sync.py` | fetch scores, grade picks. **The whole backend loop.** |
| `scripts/seed.py` | one-time migration of the old JSON into Mongo |
| `scripts/dev_server.py` | run the site + API locally, the way Vercel wires them |
| `data/` | the original JSON, kept as a seed and an offline fallback |
| `../discord_bot/` | the bot that collects picks |

`riders/` is deliberately shared by all three entry points, so there is exactly
one definition of what a pick is and one implementation of grading. The bot
reaches it by path (`sys.path` in `bot.py`); Vercel picks it up automatically
because it sits in the project root.

## The data model

One MongoDB database, three collections.

**`picks`** — one document per bet, `_id` is the Discord message id so a
gateway reconnect can't duplicate one.

```json
{
  "_id": "1234567890",
  "season": 2026, "week": 2,
  "rider": "Chance",
  "game_id": "BAL@IND",
  "market": "side",          // side | total | moneyline
  "bet": "BAL",              // team abbr, or "over"/"under"
  "line": -3.5,              // spread or total; null for moneyline
  "odds": -105, "units": 1.0,
  "status": "graded",        // pending | confirmed | rejected | graded
  "result": "win", "payout_units": 0.95
}
```

`line` is always from the perspective of the team bet: add it to their score
and compare to the opponent. A favourite is negative.

**The ledger is in units, never dollars.** `units` is what the rider risked
(1 unit unless they said otherwise) and `payout_units` is the profit or loss
in units. That keeps the board comparable no matter how much actual money
anyone puts up. A 1-unit bet at -110 wins 0.91u and loses 1.00u.

An unpriced spread or total grades at the standard **-110** rather than at
even money — grading those at even money would pay every unpriced winner
1.00u instead of 0.91u and quietly inflate the board. A moneyline has no
standard price, so an unpriced one is left ungraded instead of guessed at.

**`results`** — one document per week, holding that week's ESPN slate.
**`riders`** — Discord user id → display name.

### Status lifecycle

```
 pending ──✅──▶ confirmed ──sync.py──▶ graded
    │                                     
    └──❌/✏️──▶ rejected               
```

Only `confirmed` picks are graded, and a pick is only graded against a game
ESPN reports as `final`. A half-finished slate or a bot outage can never write
a result someone has to undo.

---

## Deploying

Everything below is free except the machine the bot runs on.

### 1. MongoDB Atlas

1. Create a free **M0** cluster at [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas/register).
2. Database Access → add a user with **Read and write to any database**.
3. Network Access → add `0.0.0.0/0`. Vercel's functions don't have fixed IPs,
   so the access list can't be narrower; the password is what protects you.
4. Connect → Drivers → copy the `mongodb+srv://…` string.

### 2. Seed it

```bash
cd riders_dashboard
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export MONGODB_URI='mongodb+srv://...'

.venv/bin/python scripts/seed.py --dry-run   # look first
.venv/bin/python scripts/seed.py             # then write
.venv/bin/python scripts/sync.py --all       # pull scores, grade everything
```

None of the historical picks recorded a size, so each seeds at 1 unit. Pass
`--units` if they should count for more.

### 3. Vercel

1. [vercel.com/new](https://vercel.com/new) → import the GitHub repo.
2. Set **Root Directory** to `riders_dashboard`.
3. Settings → Environment Variables → add `MONGODB_URI` (and `RIDERS_SEASON`
   if it isn't 2026). Apply to Production, Preview and Development.
4. Deploy. You get `https://<project>.vercel.app`.

Check `https://<project>.vercel.app/api/health` first — it pings Atlas and
reports what it can see.

### 4. The cron

`.github/workflows/sync.yml` runs `scripts/sync.py` every 15 minutes during
game windows, plus a daily `--all` reconcile sweep at 08:00 ET that catches
anything a missed run left ungraded.

1. Repo **Settings → Secrets and variables → Actions → New repository secret**
2. Name `MONGODB_URI`. **Use the read-write Atlas user** — the read-only one
   the site uses can't write grades back.
3. Actions tab → *Sync ESPN scores and grade picks* → **Run workflow** to
   confirm it works before trusting the schedule.

Free on public repos; a private repo spends Actions minutes.

Two things about GitHub's scheduler worth knowing:

- **It disables scheduled workflows after 60 days with no commits to the
  repo.** GitHub emails you first. Any commit resets the clock, so this only
  bites in a quiet off-season.
- **Cron times are best-effort.** Runs are often 5-15 minutes late at peak,
  occasionally more. Fine for scores; don't build anything time-critical on
  it.

Vercel Cron is not an option here: on the Hobby plan it is capped at **once
per day** with up to 59 minutes of jitter.

### 5. The bot

See [`../discord_bot/README.md`](../discord_bot/README.md). It needs an
always-on process, which is the one piece with no free PaaS tier — Render's
free web services sleep after 15 minutes and kill the gateway connection. A
Raspberry Pi, a spare Mac, or an Oracle Cloud Always Free ARM VM all work.

---

## Local development

```bash
export MONGODB_URI='mongodb+srv://...'
.venv/bin/python scripts/dev_server.py        # http://localhost:8000
```

Serves the site and routes `/api/*` to the same handler classes Vercel runs,
so what you see locally is what deploys.

With no `MONGODB_URI`, opening `index.html` still works — the board falls back
to the committed JSON in `data/` and grades in the browser. The status line
under the title tells you which mode you're in:

- 🟢 **Live** — reading the API
- 🟡 **Static snapshot** — API unreachable, using committed JSON
- 🔴 **No data source reachable**

## The API

| route | returns |
|---|---|
| `GET /api/bootstrap` | everything the board needs, one round trip |
| `GET /api/picks?week=2` | picks for a week (omit `week` for all) |
| `GET /api/results?week=2` | that week's ESPN slate and scores |
| `GET /api/standings?week=2` | leaderboard, season-wide or one week |
| `GET /api/health` | Atlas connectivity and a row count |

All read-only and CORS-open — the board is public anyway. Discord user ids and
raw message text are stripped server-side and never reach the page.

Responses carry `s-maxage=10, stale-while-revalidate=30`, so Vercel's edge
absorbs the polling and Atlas sees a trickle regardless of how many people
have the board open.

## Running the sync by hand

```bash
python3 scripts/sync.py                  # live week
python3 scripts/sync.py --week 1         # one week
python3 scripts/sync.py --all            # every week with picks or results
python3 scripts/sync.py --dry-run        # show what would change
python3 scripts/sync.py --insecure       # macOS system Python TLS workaround
```

Safe to run repeatedly. It only writes a result that changed.

## Things worth knowing

- **ESPN's User-Agent check.** The scoreboard endpoint 403s a custom or
  browser-spoofed `User-Agent` but allows the default ones. `riders/espn.py`
  deliberately sends no override — don't add one.
- **Week numbers come from ESPN**, not from a hardcoded calendar. Asking for
  the scoreboard with no `week` returns whatever is current, so nothing needs
  editing when the season rolls over.
- **Two profile shapes.** `chance.json` and `kyle.json` stored `weeks` as an
  array; `jay.json` and `joe.json` used an object keyed by week number.
  `scripts/seed.py` reads both and the inconsistency dies with the migration.
- **`data/` is now a fallback, not the source of truth.** Editing it won't
  change the live board. It's kept so the page still renders with no backend.
- **Rotate the Odds API key.** `test.py` had one hardcoded and it's in this
  repo's public history (commit `9ab3efc`). Removing it from the working tree
  does not un-publish it — generate a new one at the-odds-api.com.
