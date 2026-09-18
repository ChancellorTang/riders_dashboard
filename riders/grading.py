"""Grade picks against final ESPN scores.

Everything here is denominated in units, never dollars: a 1-unit bet at -110
wins 0.91u and loses 1.00u. That keeps the board comparable across riders who
risk wildly different amounts of actual money.

A pick is only ever graded off a game whose status is ``final``. Anything
else stays pending, so a bot outage or a half-finished slate can never write
a wrong result that someone has to go back and undo.
"""

from . import schema


def effective_odds(pick):
    """The price to grade this pick at, or None if it cannot be determined.

    An unpriced spread or total grades at the standard -110 rather than at
    even money. An unpriced moneyline has no such fallback and is refused, so
    it stays open instead of being graded at a made-up number.
    """
    odds = pick.get("odds")
    if odds is not None:
        return int(odds)
    if pick.get("market") in ("side", "total"):
        return schema.STANDARD_ODDS
    return None


def payout(odds, units):
    """Profit in units on a winning bet, excluding the returned stake.

    American odds are a ratio, so they carry over to units untouched: +150
    pays 1.5u per unit risked, -110 pays 0.909u.
    """
    units = 1.0 if units is None else float(units)
    if odds is None:
        return units
    odds = float(odds)
    if odds > 0:
        return units * (odds / 100.0)
    if odds < 0:
        return units * (100.0 / abs(odds))
    return units


def grade_pick(pick, game):
    """Return ``(result, profit_in_units)`` for one pick, or ``(None, None)``.

    ``None`` means "not gradable yet" — no matching game, the game is not
    final, or the pick never resolved to a side we understand.
    """
    if not game or game.get("status") != "final":
        return None, None

    bet = pick.get("bet")
    market = pick.get("market")
    if not bet or market not in schema.MARKETS:
        return None, None

    away = game.get("away_team")
    home = game.get("home_team")
    away_score = float(game.get("away_score") or 0)
    home_score = float(game.get("home_score") or 0)

    result = None

    if market in ("side", "moneyline"):
        if bet == away:
            mine, theirs = away_score, home_score
        elif bet == home:
            mine, theirs = home_score, away_score
        else:
            # Bet a team that is not in this game — do not guess.
            return None, None

        # A moneyline is a spread of zero, so both markets share one comparison.
        line = float(pick.get("line") or 0) if market == "side" else 0.0
        margin = (mine + line) - theirs
        result = "win" if margin > 0 else "loss" if margin < 0 else "push"

    elif market == "total":
        line = pick.get("line")
        if line is None:
            return None, None
        total = away_score + home_score
        if bet == "over":
            result = "win" if total > line else "loss" if total < line else "push"
        elif bet == "under":
            result = "win" if total < line else "loss" if total > line else "push"
        else:
            return None, None

    units = pick.get("units")
    units = 1.0 if units is None else float(units)

    odds = effective_odds(pick)
    if odds is None:
        return None, None   # unpriced moneyline — leave it open

    if result == "win":
        return "win", round(payout(odds, units), 2)
    if result == "loss":
        return "loss", round(-units, 2)
    return "push", 0.0


def grade_all(picks, results_by_game):
    """Grade a batch. Yields ``(pick, result, profit)`` for gradable picks only.

    ``results_by_game`` maps game_id -> the ESPN game document.
    """
    for pick in picks:
        if pick.get("status") not in ("confirmed", "graded"):
            continue
        game = results_by_game.get(pick.get("game_id"))
        result, profit = grade_pick(pick, game)
        if result is None:
            continue
        # Skip picks already carrying this exact result so reruns are cheap.
        if pick.get("status") == "graded" and pick.get("result") == result:
            continue
        yield pick, result, profit


def standings(picks, riders=None):
    """Aggregate graded picks into a leaderboard, in units.

    ``net`` and ``units_risked`` are both unit counts, so ``roi`` is directly
    comparable between riders however much money they actually put up.

    Pending picks count toward ``open`` but never toward the record, so the
    board reads the same whether or not the week has finished.
    """
    table = {}

    def row(name):
        return table.setdefault(name, {
            "player": name, "wins": 0, "losses": 0, "pushes": 0,
            "open": 0, "net": 0.0, "units_risked": 0.0,
        })

    for name in riders or []:
        row(name)

    for pick in picks:
        name = pick.get("rider")
        if not name or pick.get("status") == "rejected":
            continue
        entry = row(name)
        result = pick.get("result")

        if result == "win":
            entry["wins"] += 1
        elif result == "loss":
            entry["losses"] += 1
        elif result == "push":
            entry["pushes"] += 1
        else:
            entry["open"] += 1
            continue

        entry["net"] += float(pick.get("payout_units") or 0)
        entry["units_risked"] += float(pick.get("units") or 0)

    rows = []
    for entry in table.values():
        decided = entry["wins"] + entry["losses"]
        entry["net"] = round(entry["net"], 2)
        entry["units_risked"] = round(entry["units_risked"], 2)
        entry["win_pct"] = round(entry["wins"] / decided, 4) if decided else None
        entry["roi"] = (round(entry["net"] / entry["units_risked"], 4)
                        if entry["units_risked"] else None)
        rows.append(entry)

    rows.sort(key=lambda r: (-r["net"], -r["wins"], r["player"]))
    return rows
