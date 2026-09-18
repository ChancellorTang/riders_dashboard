/**
 * The Riders betting board.
 *
 * Reads from /api/bootstrap when a backend is reachable, and falls back to the
 * committed JSON files when it isn't — so the same build works deployed on
 * Vercel, opened straight off disk, or served from GitHub Pages.
 *
 * Grading is the backend's job. The fallback path re-derives results in the
 * browser so the static copy is not blank, but the two use the same rules.
 */

const API_BASE = "/api";
const REFRESH_MS = 15000;
const SEED_PLAYERS = ["Joe", "Jay", "Kyle", "Chance"];

const state = {
  view: "home",
  selectedWeek: 1,
  currentWeek: 1,
  weeks: [1],
  players: [...SEED_PLAYERS],
  picks: [],
  gamesByWeek: {},
  standings: { season: [], week: [] },
  source: "loading",
  updatedAt: null,
  error: null
};

const els = {
  weekTabs: document.getElementById("week-tabs"),
  homeView: document.getElementById("home-view"),
  weekView: document.getElementById("week-view"),
  thisWeeksPicks: document.getElementById("this-weeks-picks"),
  standingsTable: document.getElementById("standings-table"),
  weekTitle: document.getElementById("week-title"),
  weekContent: document.getElementById("week-content"),
  status: document.getElementById("data-status")
};

/* ------------------------------------------------------------------ utils */

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Number(null) and Number("") are both 0, which would turn "no odds stated"
// into "(0)". Treat empty values as absent before coercing.
const num = (value, fallback = null) => {
  if (value === null || value === undefined || value === "") return fallback;
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
};

/** Signed unit count for the standings: "+2.35u", "\u22121.00u". */
function formatUnits(value) {
  const n = num(value, 0);
  const sign = n >= 0 ? "+" : "\u2212";   // true minus, not a hyphen
  return `${sign}${Math.abs(n).toFixed(2)}u`;
}

/** Unsigned size on a pick row: "1u", "2.5u". */
function formatRisk(value) {
  const n = num(value, 1);
  return `${n}u`;
}

function formatLine(value) {
  const n = num(value);
  if (n === null) return "";
  return n >= 0 ? `+${n}` : `${n}`;
}

function formatOdds(value) {
  const n = num(value);
  if (n === null) return "";
  return n > 0 ? `+${n}` : `${n}`;
}

/** "BAL -3.5 (-105)" — one line describing what was bet. */
function describePick(pick) {
  const bits = [];
  if (pick.market === "total") {
    // A total is never signed — "UNDER 44.5", not "UNDER +44.5".
    const line = num(pick.line);
    bits.push(String(pick.bet || "").toUpperCase(), line === null ? "" : String(Math.abs(line)));
  } else if (pick.market === "moneyline") {
    bits.push(pick.bet || "?", "ML");
  } else {
    bits.push(pick.bet || "?", formatLine(pick.line));
  }
  const odds = formatOdds(pick.odds);
  if (odds) bits.push(`(${odds})`);
  return bits.filter(Boolean).join(" ");
}

/** What to show in the status pill: the graded result, else how it's sitting. */
function pickOutcome(pick) {
  if (pick.result) return pick.result;
  if (pick.status === "pending") return "unconfirmed";
  return "pending";
}

/* ------------------------------------------------------------------- data */

async function getJSON(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

async function loadFromApi() {
  const data = await getJSON(`${API_BASE}/bootstrap`);

  state.weeks = (data.weeks || []).map(Number).filter(Boolean).sort((a, b) => a - b);
  if (!state.weeks.length) state.weeks = [1];
  state.currentWeek = num(data.current_week, state.weeks[state.weeks.length - 1]);
  state.players = (data.riders || []).length ? data.riders : SEED_PLAYERS;
  state.picks = data.picks || [];
  state.standings = data.standings || { season: [], week: [] };
  state.updatedAt = data.results?.updated_at || null;

  // Keep previously fetched weeks — they are final and will not change — and
  // refresh only the live week, which bootstrap always carries.
  const week = num(data.results?.week, state.currentWeek);
  state.gamesByWeek[week] = indexGames(data.results?.games);

  state.source = "live";
}

/**
 * Fallback: read the committed JSON straight from disk.
 *
 * Tolerates both profile shapes in data/profiles — two of the four files store
 * `weeks` as an array and two as an object keyed by week number.
 */
async function loadFromFiles() {
  const picks = [];
  const weeks = new Set();

  for (const player of SEED_PLAYERS) {
    let profile;
    try {
      profile = await getJSON(`./data/profiles/${player.toLowerCase()}.json`);
    } catch {
      continue;
    }

    const entries = Array.isArray(profile.weeks)
      ? profile.weeks
      : Object.values(profile.weeks || {});

    for (const entry of entries) {
      const week = num(entry.week, 1);
      weeks.add(week);
      for (const pick of entry.picks || []) {
        picks.push({
          player: profile.player || player,
          week,
          game: pick.game || "",
          market: pick.type || "side",
          bet: pick.bet || "",
          line: num(pick.spread, null),
          odds: num(pick.odds, null),
          units: num(pick.units, 1),
          status: "confirmed",
          result: null,
          payout_units: null
        });
      }
    }
  }

  state.weeks = [...weeks].sort((a, b) => a - b);
  if (!state.weeks.length) state.weeks = [1];
  state.currentWeek = state.weeks[state.weeks.length - 1];
  state.players = [...SEED_PLAYERS];

  state.gamesByWeek = {};
  for (const week of state.weeks) {
    try {
      const payload = await getJSON(`./data/week_${week}/results.json`);
      state.gamesByWeek[week] = indexGames(payload.games);
      state.updatedAt = payload.updated_at || state.updatedAt;
    } catch {
      state.gamesByWeek[week] = {};
    }
  }

  // No backend to grade for us, so do it here.
  for (const pick of picks) {
    const game = state.gamesByWeek[pick.week]?.[pick.game];
    const result = gradeLocally(pick, game);
    if (result) {
      const units = num(pick.units, 1);
      pick.result = result;
      pick.status = "graded";
      pick.payout_units = result === "win" ? profitOn(effectiveOdds(pick), units)
        : result === "loss" ? -units
        : 0;
    }
  }

  state.picks = picks;
  state.standings = {
    season: buildStandings(picks),
    week: buildStandings(picks.filter((p) => p.week === state.currentWeek))
  };
  state.source = "static";
}

/**
 * Make sure state.gamesByWeek has the scoreboard for `week`.
 *
 * /api/bootstrap only ships the current week's games — sending all eighteen
 * on every poll would be wasteful — so older weeks are fetched once, the
 * first time someone opens that tab, and then cached.
 */
async function ensureWeekResults(week) {
  if (state.source !== "live" || state.gamesByWeek[week]) return;

  state.gamesByWeek[week] = {};   // claim it so concurrent renders don't refetch
  try {
    const payload = await getJSON(`${API_BASE}/results?week=${week}`);
    state.gamesByWeek[week] = indexGames(payload.games);
  } catch (error) {
    console.warn(`No results for week ${week}`, error);
  }
}

function indexGames(games) {
  const map = {};
  for (const game of games || []) map[game.game_id] = game;
  return map;
}

async function loadData() {
  try {
    await loadFromApi();
    state.error = null;
  } catch (apiError) {
    try {
      await loadFromFiles();
      state.error = null;
      console.info("API unavailable, using committed JSON:", apiError.message);
    } catch (fileError) {
      state.source = "error";
      state.error = fileError.message;
      console.error("No data source reachable", fileError);
    }
  }

  if (!state.weeks.includes(state.selectedWeek)) {
    state.selectedWeek = state.currentWeek;
  }
}

/* ------------------------------------------- local grading (fallback only) */

// Mirrors riders/grading.py: an unpriced spread or total grades at the
// standard -110, an unpriced moneyline is left ungraded.
const STANDARD_ODDS = -110;

function effectiveOdds(pick) {
  const odds = num(pick.odds);
  if (odds !== null) return odds;
  return pick.market === "side" || pick.market === "total" ? STANDARD_ODDS : null;
}

function profitOn(odds, units) {
  const o = num(odds, 0);
  const u = num(units, 1);
  if (o > 0) return u * (o / 100);
  if (o < 0) return u * (100 / Math.abs(o));
  return u;
}

/** Mirrors riders/grading.py. Returns null when the game isn't final. */
function gradeLocally(pick, game) {
  if (!game || game.status !== "final") return null;
  if (effectiveOdds(pick) === null) return null;   // unpriced moneyline

  const away = game.away_team;
  const home = game.home_team;
  const awayScore = num(game.away_score, 0);
  const homeScore = num(game.home_score, 0);

  if (pick.market === "side" || pick.market === "moneyline") {
    let mine;
    let theirs;
    if (pick.bet === away) [mine, theirs] = [awayScore, homeScore];
    else if (pick.bet === home) [mine, theirs] = [homeScore, awayScore];
    else return null;

    const line = pick.market === "side" ? num(pick.line, 0) : 0;
    const margin = mine + line - theirs;
    return margin > 0 ? "win" : margin < 0 ? "loss" : "push";
  }

  if (pick.market === "total") {
    const line = num(pick.line);
    if (line === null) return null;
    const total = awayScore + homeScore;
    if (pick.bet === "over") return total > line ? "win" : total < line ? "loss" : "push";
    if (pick.bet === "under") return total < line ? "win" : total > line ? "loss" : "push";
  }

  return null;
}

function buildStandings(picks) {
  const table = new Map();
  const row = (player) => {
    if (!table.has(player)) {
      table.set(player, {
        player, wins: 0, losses: 0, pushes: 0, open: 0, net: 0, unitsRisked: 0
      });
    }
    return table.get(player);
  };
  SEED_PLAYERS.forEach(row);

  for (const pick of picks) {
    if (!pick.player) continue;
    const entry = row(pick.player);
    if (pick.result === "win") entry.wins += 1;
    else if (pick.result === "loss") entry.losses += 1;
    else if (pick.result === "push") entry.pushes += 1;
    else {
      entry.open += 1;
      continue;
    }
    entry.net += num(pick.payout_units, 0);
    entry.unitsRisked += num(pick.units, 0);
  }

  return [...table.values()]
    .map((entry) => ({
      ...entry,
      net: Number(entry.net.toFixed(2)),
      roi: entry.unitsRisked ? entry.net / entry.unitsRisked : null
    }))
    .sort((a, b) => b.net - a.net || b.wins - a.wins || a.player.localeCompare(b.player));
}

/* ----------------------------------------------------------------- render */

function picksForWeek(week) {
  return state.picks.filter((pick) => num(pick.week) === week);
}

function buildWeekTabs() {
  const tabs = [
    { label: "Home", value: "home" },
    ...state.weeks.map((week) => ({ label: `Week ${week}`, value: week }))
  ];

  els.weekTabs.innerHTML = "";
  for (const tab of tabs) {
    const button = document.createElement("button");
    button.type = "button";
    const isActive =
      (tab.value === "home" && state.view === "home") ||
      (state.view === "week" && state.selectedWeek === tab.value);
    button.className = `tab-button${isActive ? " active" : ""}`;
    button.textContent = tab.label;
    button.addEventListener("click", () => {
      if (tab.value === "home") {
        state.view = "home";
        render();
      } else {
        state.view = "week";
        state.selectedWeek = tab.value;
        render();
        ensureWeekResults(tab.value).then(render);
      }
    });
    els.weekTabs.appendChild(button);
  }
}

function renderStatusLine() {
  if (!els.status) return;

  const labels = {
    live: "Live · connected to the picks API",
    static: "Static snapshot · API unreachable, reading committed JSON",
    error: `No data source reachable${state.error ? ` (${state.error})` : ""}`,
    loading: "Loading…"
  };

  const stamp = state.updatedAt
    ? ` · scores updated ${new Date(state.updatedAt).toLocaleString()}`
    : "";

  els.status.textContent = labels[state.source] + stamp;
  els.status.dataset.source = state.source;
}

function standingsMarkup(rows) {
  if (!rows.length) return `<p class="empty-state">No standings yet.</p>`;

  return `
    <div class="standings-row header">
      <span>Player</span><span>W</span><span>L</span><span>P</span><span>Net</span>
    </div>
    ${rows.map((entry) => `
      <div class="standings-row">
        <span class="player-name">${esc(entry.player)}${
          entry.open ? `<small class="open-count"> ${entry.open} open</small>` : ""
        }</span>
        <span>${entry.wins}</span>
        <span>${entry.losses}</span>
        <span>${entry.pushes}</span>
        <span class="${entry.net >= 0 ? "net-positive" : "net-negative"}">${formatUnits(entry.net)}</span>
      </div>
    `).join("")}
  `;
}

function pickRowMarkup(pick, { showPlayer = true } = {}) {
  const outcome = pickOutcome(pick);
  const pillClass = ["win", "loss", "push"].includes(outcome) ? outcome : "pending";
  const game = pick.game || "unmatched";
  const settled = pick.result && pick.payout_units !== null && pick.payout_units !== undefined;
  const money = settled
    ? `<span class="${num(pick.payout_units, 0) >= 0 ? "net-positive" : "net-negative"}">${formatUnits(pick.payout_units)}</span>`
    : `<small>${formatRisk(pick.units)} risked</small>`;

  return `
    <div class="picks-item">
      ${showPlayer ? `<span class="player-badge">${esc(pick.player || "?")}</span>` : ""}
      <div class="bet-copy">
        <strong>${esc(describePick(pick))}</strong>
        <small>${esc(game)}</small>
      </div>
      <div class="pick-outcome">
        ${money}
        <span class="status-pill ${pillClass}">${esc(outcome)}</span>
      </div>
    </div>
  `;
}

function renderHome() {
  const week = state.currentWeek;
  const picks = picksForWeek(week);

  els.thisWeeksPicks.innerHTML = picks.length
    ? picks.map((pick) => pickRowMarkup(pick)).join("")
    : `<p class="empty-state">No picks logged for Week ${week} yet. Post one in <strong>#picks</strong>.</p>`;

  els.standingsTable.innerHTML = standingsMarkup(state.standings.season || []);
}

function renderWeek() {
  const week = state.selectedWeek;
  const picks = picksForWeek(week);
  const games = Object.values(state.gamesByWeek[week] || {});

  els.weekTitle.textContent = `Week ${week}`;

  const players = state.players.length ? state.players : SEED_PLAYERS;
  const weekStandings = state.source === "live" && week === state.currentWeek
    ? state.standings.week || []
    : buildStandings(picks);

  els.weekContent.innerHTML = `
    <div class="week-card">
      <div class="panel-header">
        <p class="panel-kicker">WEEK ${week}</p>
        <h3>Player Picks</h3>
      </div>
      <div class="player-picks-list">
        ${players.map((player) => {
          const mine = picks.filter((pick) => pick.player === player);
          return `
            <div class="player-pick-item">
              <strong>${esc(player)}</strong>
              ${mine.length
                ? mine.map((pick) => pickRowMarkup(pick, { showPlayer: false })).join("")
                : `<div class="empty-state">No picks</div>`}
            </div>
          `;
        }).join("")}
      </div>
    </div>

    <aside class="side-card">
      <div class="panel-header">
        <p class="panel-kicker">STANDINGS</p>
        <h3>Week ${week}</h3>
      </div>
      <div class="standings-table">${standingsMarkup(weekStandings)}</div>

      <div class="week-results">
        <h3>Results</h3>
        ${games.length
          ? games.map((game) => {
              const isFinal = game.status === "final";
              const live = game.status === "in_progress";
              const detail = isFinal
                ? `${game.away_score} – ${game.home_score}`
                : live
                  ? `${game.away_score} – ${game.home_score} · live`
                  : new Date(game.start_time).toLocaleString(undefined, {
                      weekday: "short", hour: "numeric", minute: "2-digit"
                    });
              return `
                <div class="result-item">
                  <strong>${esc(game.away_team)} @ ${esc(game.home_team)}</strong>
                  <small class="${live ? "live-score" : ""}">${esc(detail)}</small>
                </div>
              `;
            }).join("")
          : `<p class="empty-state">No results loaded for Week ${week}.</p>`}
      </div>
    </aside>
  `;
}

function render() {
  buildWeekTabs();
  renderStatusLine();

  const onHome = state.view === "home";
  els.homeView.classList.toggle("active", onHome);
  els.weekView.classList.toggle("active", !onHome);

  if (onHome) renderHome();
  else renderWeek();
}

/* ------------------------------------------------------------------- boot */

async function refresh() {
  await loadData();
  if (state.view === "week") await ensureWeekResults(state.selectedWeek);
  render();
}

async function init() {
  await refresh();

  // Pause polling while the tab is hidden; resume immediately on return.
  setInterval(() => {
    if (!document.hidden) refresh();
  }, REFRESH_MS);

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
}

init();
