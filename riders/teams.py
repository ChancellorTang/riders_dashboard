"""NFL team resolution.

The LLM will hand back whatever the poster typed — "Ravens", "Baltimore",
"BAL", "Bmore". Everything downstream keys off ESPN's abbreviation, so this
module is the single place that maps loose text onto it.

ESPN quirks worth knowing: Washington is ``WSH`` (not WAS) and Jacksonville is
``JAX`` (not JAC). Both of the wrong ones are accepted as aliases because
sportsbooks and humans use them constantly.
"""

import re

# abbr -> (location, nickname, extra aliases)
TEAMS = {
    "ARI": ("Arizona", "Cardinals", ["cards", "az"]),
    "ATL": ("Atlanta", "Falcons", ["dirty birds"]),
    "BAL": ("Baltimore", "Ravens", ["bmore"]),
    "BUF": ("Buffalo", "Bills", ["bills mafia"]),
    "CAR": ("Carolina", "Panthers", []),
    "CHI": ("Chicago", "Bears", ["da bears"]),
    "CIN": ("Cincinnati", "Bengals", ["cincy"]),
    "CLE": ("Cleveland", "Browns", []),
    "DAL": ("Dallas", "Cowboys", ["boys", "americas team"]),
    "DEN": ("Denver", "Broncos", []),
    "DET": ("Detroit", "Lions", []),
    "GB": ("Green Bay", "Packers", ["pack", "gbp", "gnb"]),
    "HOU": ("Houston", "Texans", []),
    "IND": ("Indianapolis", "Colts", ["indy"]),
    "JAX": ("Jacksonville", "Jaguars", ["jags", "jac"]),
    "KC": ("Kansas City", "Chiefs", ["kan", "kcc"]),
    "LV": ("Las Vegas", "Raiders", ["oak", "oakland", "lvr", "vegas"]),
    "LAC": ("Los Angeles", "Chargers", ["bolts", "sd", "san diego"]),
    "LAR": ("Los Angeles", "Rams", ["la rams", "stl"]),
    "MIA": ("Miami", "Dolphins", ["fins", "phins"]),
    "MIN": ("Minnesota", "Vikings", ["vikes"]),
    "NE": ("New England", "Patriots", ["pats", "nwe"]),
    "NO": ("New Orleans", "Saints", ["nola", "nor"]),
    "NYG": ("New York", "Giants", ["gmen", "g men"]),
    "NYJ": ("New York", "Jets", []),
    "PHI": ("Philadelphia", "Eagles", ["philly", "birds"]),
    "PIT": ("Pittsburgh", "Steelers", ["stillers"]),
    "SF": ("San Francisco", "49ers", ["niners", "sfo", "forty niners"]),
    "SEA": ("Seattle", "Seahawks", ["hawks"]),
    "TB": ("Tampa Bay", "Buccaneers", ["bucs", "tampa", "tbb"]),
    "TEN": ("Tennessee", "Titans", []),
    "WSH": ("Washington", "Commanders", ["was", "commies", "wft"]),
}

ABBRS = frozenset(TEAMS)


def _norm(text):
    """Lowercase, strip punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", str(text).lower())).strip()


def _build_alias_index():
    index = {}

    def put(key, abbr):
        key = _norm(key)
        if not key:
            return
        # First writer wins, so the explicit entries below stay authoritative
        # over anything a broader alias would otherwise claim.
        index.setdefault(key, abbr)

    for abbr, (location, nickname, extras) in TEAMS.items():
        put(abbr, abbr)
        put(nickname, abbr)
        put(f"{location} {nickname}", abbr)
        for extra in extras:
            put(extra, abbr)

    # Bare city names are ambiguous for the two New York and two Los Angeles
    # clubs, so they are only registered for cities with a single team.
    by_location = {}
    for abbr, (location, _, _) in TEAMS.items():
        by_location.setdefault(_norm(location), []).append(abbr)
    for location, abbrs in by_location.items():
        if len(abbrs) == 1:
            put(location, abbrs[0])

    return index


ALIASES = _build_alias_index()

AMBIGUOUS = {"new york", "los angeles", "ny", "la"}


def resolve(text):
    """Return an ESPN abbreviation for ``text``, or None.

    Tries an exact alias match first, then looks for any alias appearing as a
    whole-word phrase inside a longer string, preferring the longest match so
    "los angeles chargers" never resolves via "chargers" alone.
    """
    if not text:
        return None

    key = _norm(text)
    if key in ALIASES:
        return ALIASES[key]

    best = None
    for alias, abbr in ALIASES.items():
        if alias in AMBIGUOUS or len(alias) < 3:
            continue
        if re.search(rf"\b{re.escape(alias)}\b", key) and (best is None or len(alias) > len(best[0])):
            best = (alias, abbr)

    return best[1] if best else None


def resolve_matchup(text):
    """Pull two teams out of a matchup string like "Ravens @ Colts".

    Returns ``(away, home)`` when both sides resolve and differ, else None.
    ESPN orders game ids away-first, and so do the separators people type
    ("@", "at", "vs", "v", "-"), so the left side is treated as the away team.
    """
    if not text:
        return None

    parts = re.split(r"\s*(?:@|\bat\b|\bvs?\.?\b|\bversus\b|/|\||-{1,2}|–)\s*", str(text), maxsplit=1, flags=re.I)
    if len(parts) != 2:
        return None

    away, home = resolve(parts[0]), resolve(parts[1])
    if away and home and away != home:
        return away, home
    return None


def game_id(away, home):
    return f"{away}@{home}"


def teams_in(text):
    """Every distinct team mentioned in ``text``, in order of appearance.

    Used as the fallback when the poster never wrote a real matchup — "took
    the Ravens tonight" still tells us which game they mean once we check it
    against the week's slate.
    """
    key = _norm(text or "")
    hits = []
    for alias, abbr in ALIASES.items():
        if alias in AMBIGUOUS or len(alias) < 3:
            continue
        match = re.search(rf"\b{re.escape(alias)}\b", key)
        if match:
            hits.append((match.start(), -len(alias), abbr))

    seen, ordered = set(), []
    for _, _, abbr in sorted(hits):
        if abbr not in seen:
            seen.add(abbr)
            ordered.append(abbr)
    return ordered
