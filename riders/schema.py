"""The canonical shape of a pick, and the normaliser that produces one.

Three sources feed this: the LLM parser reading a Discord message, the
``/pick`` slash command, and the one-time seed from the old profile JSON.
They all land in the same document so grading and the API never branch on
where a pick came from.

Status lifecycle
    pending   parsed but the poster has not confirmed it
    confirmed poster vouched for it; grading will pick it up
    rejected  bad parse, or not a real pick
    graded    graded against a final ESPN score
"""

from datetime import datetime, timezone

from . import teams

MARKETS = ("side", "total", "moneyline")
STATUSES = ("pending", "confirmed", "rejected", "graded")
RESULTS = ("win", "loss", "push", "void")

# The ledger is denominated in units, not dollars, so everyone's board is
# comparable no matter what they actually risk. A rider sizes their own bet by
# saying so ("2 units on the Ravens"); anything unsized is one unit.
DEFAULT_UNITS = 1.0

# Spreads and totals are quoted at -110 as standard, and people routinely post
# a side with no price. Grading those at even money would hand every unpriced
# winner 1.00u instead of 0.91u and quietly inflate the whole board, so -110 is
# assumed instead. A moneyline has no standard price, so it must be stated.
STANDARD_ODDS = -110


def now():
    return datetime.now(timezone.utc).isoformat()


def build(
    *,
    pick_id,
    week,
    season,
    rider=None,
    discord_user_id=None,
    source="text",
    market="side",
    bet=None,
    line=None,
    odds=None,
    units=None,
    game_id=None,
    event_raw=None,
    confidence=None,
    parser_notes=None,
    raw_text=None,
    status="pending",
    posted_at=None,
):
    """Assemble a pick document. Nothing here talks to the database."""
    timestamp = now()
    return {
        "_id": str(pick_id),
        "season": int(season),
        "week": int(week),
        "rider": rider,
        "discord_user_id": str(discord_user_id) if discord_user_id else None,
        "source": source,
        "game_id": game_id,
        "event_raw": event_raw,
        "market": market,
        "bet": bet,
        "line": None if line is None else float(line),
        "odds": None if odds is None else int(odds),
        "units": DEFAULT_UNITS if units is None else float(units),
        "confidence": None if confidence is None else float(confidence),
        "parser_notes": parser_notes,
        "raw_text": raw_text,
        "status": status,
        "result": None,
        "payout_units": None,
        "graded_at": None,
        "posted_at": posted_at or timestamp,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def normalize_market(value):
    """Map the many words for a market onto our three."""
    v = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if v in ("spread", "side", "ats", "handicap", "point_spread", "line"):
        return "side"
    if v in ("total", "totals", "over_under", "ou", "over_under_total"):
        return "total"
    if v in ("moneyline", "ml", "money_line", "h2h", "win"):
        return "moneyline"
    return None


def normalize_bet(market, selection):
    """Turn the selection into the token grading expects.

    Sides and moneylines become a team abbreviation; totals become
    ``over``/``under``. Returns None when the selection cannot be pinned down,
    which is what keeps an unresolvable pick out of the graded pool.
    """
    text = str(selection or "").strip()
    if not text:
        return None

    if market == "total":
        low = text.lower()
        if "over" in low or low.startswith("o"):
            return "over"
        if "under" in low or low.startswith("u"):
            return "under"
        return None

    return teams.resolve(text)


def signed_line(market, line):
    """Keep the spread from the perspective of the team that was bet.

    A spread is stored the way the dashboard already reads it: add ``line`` to
    the bet team's score and compare to the opponent. That means a favourite
    carries a negative line. Books quote it that way too, so the number usually
    arrives correct; this only fixes the case where a sign is missing entirely.
    """
    if line is None or market != "side":
        return line
    return float(line)


def match_game(game_id_hint, event_raw, raw_text, slate):
    """Pick the game this bet belongs to out of a week's slate.

    ``slate`` is an iterable of game ids ("BAL@IND"). Three attempts, most
    trustworthy first: an id we were handed, a matchup string the poster wrote,
    and finally any team named anywhere in the message. The last one only wins
    if it identifies exactly one game, so "Bengals" resolves but a message
    naming four teams stays unmatched rather than guessing.
    """
    slate = list(slate or [])
    if not slate:
        return None

    if game_id_hint and game_id_hint in slate:
        return game_id_hint

    pair = teams.resolve_matchup(event_raw) or teams.resolve_matchup(raw_text)
    if pair:
        candidate = teams.game_id(*pair)
        if candidate in slate:
            return candidate
        # Poster may have written it home-first.
        flipped = teams.game_id(pair[1], pair[0])
        if flipped in slate:
            return flipped

    mentioned = set(teams.teams_in(event_raw or "")) | set(teams.teams_in(raw_text or ""))
    if mentioned:
        hits = [g for g in slate if set(g.split("@")) & mentioned]
        if len(hits) == 1:
            return hits[0]

    return None


def from_parsed(parsed, *, pick_id, week, season, slate, rider=None,
                discord_user_id=None, source="text", raw_text=None, posted_at=None):
    """Turn raw parser output into a canonical pick document.

    Returns ``(doc, problems)``. ``problems`` is a list of human-readable
    reasons the pick is not fully resolved — an unmatched game, an unknown
    market, a missing stake. The caller decides what to do with them; the bot
    uses them to force a confirmation instead of auto-confirming.
    """
    problems = []

    market = normalize_market(parsed.get("market"))
    if market is None:
        problems.append("could not tell which market this is")

    bet = normalize_bet(market, parsed.get("selection")) if market else None
    if bet is None:
        problems.append(f"could not resolve the selection {parsed.get('selection')!r}")

    event_raw = parsed.get("event")
    game_id = match_game(None, event_raw, raw_text, slate)
    if game_id is None:
        problems.append("no game on this week's slate matches")
    elif bet and market in ("side", "moneyline") and bet not in game_id.split("@"):
        problems.append(f"{bet} is not playing in {game_id}")
        game_id = None

    line = parsed.get("line")
    if market == "side" and line is None:
        problems.append("no spread stated")
    if market == "total" and line is None:
        problems.append("no total stated")

    # An unsized pick is simply one unit, so silence is not a problem here.
    units = parsed.get("units")

    # A dollar figure is not, though. The ledger ignores dollars entirely, so
    # "$500 on the Ravens" would quietly become one unit. Flag it instead and
    # let the rider either accept 1u or restate it in units.
    if units is None and parsed.get("saw_dollar_amount"):
        problems.append("dollar amount ignored — counted as 1 unit; "
                        "restate in units if that is wrong")

    # Only a moneyline is blocked by a missing price; a side or total falls
    # back to the standard -110, which is recorded in the notes so the rider
    # can see it was assumed rather than read.
    notes = [parsed.get("notes")] if parsed.get("notes") else []
    if parsed.get("odds") is None:
        if market == "moneyline":
            problems.append("a moneyline needs odds — no standard price to assume")
        elif market in ("side", "total"):
            notes.append(f"odds not stated; graded at the standard {STANDARD_ODDS}")

    doc = build(
        pick_id=pick_id,
        week=week,
        season=season,
        rider=rider,
        discord_user_id=discord_user_id,
        source=source,
        market=market or "side",
        bet=bet,
        line=signed_line(market, line),
        odds=parsed.get("odds"),
        units=units,
        game_id=game_id,
        event_raw=event_raw,
        confidence=parsed.get("confidence"),
        parser_notes="; ".join(notes) or None,
        raw_text=raw_text,
        posted_at=posted_at,
    )
    return doc, problems


def is_gradable(doc):
    """Whether a document has everything grading needs.

    A moneyline additionally needs odds: there is no standard price to fall
    back on, and guessing one either way would bias the board.
    """
    market = doc.get("market")
    if not doc.get("game_id") or not doc.get("bet") or market not in MARKETS:
        return False
    if market == "moneyline":
        return doc.get("odds") is not None
    return doc.get("line") is not None
