const PEOPLE = ["Joe", "Jay", "Kyle", "Chance"];

const state = {
  selectedView: "home",
  selectedWeek: "Week 1",
  currentWeek: 1,
  weeks: [],
  picks: [],
  resultsByWeek: {}
};

const els = {
  weekTabs: document.getElementById("week-tabs"),
  homeView: document.getElementById("home-view"),
  weekView: document.getElementById("week-view"),
  thisWeeksPicks: document.getElementById("this-weeks-picks"),
  standingsTable: document.getElementById("standings-table"),
  weekTitle: document.getElementById("week-title"),
  weekContent: document.getElementById("week-content")
};

async function init() {
  await loadDashboardData();
  buildWeekTabs();
  render();
  startAutoRefresh();
}

function startAutoRefresh() {
  setInterval(async () => {
    await loadDashboardData();
    render();
  }, 5000);

  window.addEventListener("focus", async () => {
    await loadDashboardData();
    render();
  });
}

async function loadDashboardData() {
  const profileFiles = PEOPLE.map((person) => person.toLowerCase());
  const allPicks = [];
  const weekSet = new Set();

  for (const player of profileFiles) {
    try {
      const response = await fetch(`./data/profiles/${player}.json`, { cache: "no-store" });
      if (!response.ok) continue;
      const profile = await response.json();
      const weeks = Array.isArray(profile.weeks) ? profile.weeks : Object.values(profile.weeks || {});

      weeks.forEach((weekEntry) => {
        const weekNumber = Number(weekEntry.week ?? 1);
        const weekName = `Week ${weekNumber}`;
        weekSet.add(weekName);

        const picks = Array.isArray(weekEntry.picks) ? weekEntry.picks : [];
        picks.forEach((pick) => {
          allPicks.push({
            player: profile.player,
            week: weekName,
            game: pick.game || "",
            type: pick.type || "side",
            bet: pick.bet || "",
            spread: Number(pick.spread ?? 0),
            odds: Number(pick.odds ?? 0),
            stake: Number(pick.stake ?? 1)
          });
        });
      });
    } catch (error) {
      console.warn(`Unable to load profile ${player}`, error);
    }
  }

  state.picks = allPicks;
  state.weeks = [...weekSet].sort((a, b) => parseWeekNumber(a) - parseWeekNumber(b));
  if (!state.weeks.length) {
    state.weeks = ["Week 1"];
  }

  state.currentWeek = parseWeekNumber(state.weeks[state.weeks.length - 1]);
  state.selectedWeek = `Week ${state.currentWeek}`;

  const resultsByWeek = {};
  for (const weekName of state.weeks) {
    const weekNumber = parseWeekNumber(weekName);
    try {
      const response = await fetch(`./data/week_${weekNumber}/results.json`, { cache: "no-store" });
      if (!response.ok) continue;
      const payload = await response.json();
      const map = {};
      (payload.games || []).forEach((game) => {
        map[game.game_id] = game;
      });
      resultsByWeek[weekName] = map;
    } catch (error) {
      console.warn(`Unable to load results for ${weekName}`, error);
    }
  }

  state.resultsByWeek = resultsByWeek;
}

function parseWeekNumber(weekName) {
  const match = String(weekName).match(/(\d+)/);
  return match ? Number(match[1]) : 1;
}

function buildWeekTabs() {
  els.weekTabs.innerHTML = "";

  const tabs = [
    { name: "Home", value: "home" },
    ...state.weeks.map((week) => ({ name: week, value: week }))
  ];

  tabs.forEach((tab) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `tab-button ${state.selectedView === "home" && tab.value === "home" ? "active" : ""} ${state.selectedView === "week" && state.selectedWeek === tab.value ? "active" : ""}`;
    button.textContent = tab.name;
    button.addEventListener("click", () => {
      if (tab.value === "home") {
        state.selectedView = "home";
      } else {
        state.selectedView = "week";
        state.selectedWeek = tab.value;
      }
      render();
    });
    els.weekTabs.appendChild(button);
  });
}

function render() {
  buildWeekTabs();
  renderHomeOverview();
  renderWeekBoard();
}

function renderHomeOverview() {
  const thisWeek = `Week ${state.currentWeek}`;
  const picks = getPicksForWeek(thisWeek);
  const standings = getStandingsForWeek(thisWeek);

  els.thisWeeksPicks.innerHTML = picks.length
    ? picks.map((pick) => {
        const outcome = resolvePickAgainstGame(pick);
        return `
          <div class="picks-item">
            <span class="player-badge">${pick.player}</span>
            <div class="bet-copy">
              <strong>${getPickSummary(pick)}</strong>
              <small>${pick.game || "Game pick"}</small>
            </div>
            <span class="status-pill ${outcome === "win" ? "win" : outcome === "loss" ? "loss" : outcome === "push" ? "push" : "pending"}">${outcome}</span>
          </div>
        `;
      }).join("")
    : `<p class="empty-state">No picks found for ${thisWeek}.</p>`;

  els.standingsTable.innerHTML = `
    <div class="standings-row header">
      <span>Player</span>
      <span>W</span>
      <span>L</span>
      <span>P</span>
      <span>Net</span>
    </div>
    ${standings.map((entry) => `
      <div class="standings-row">
        <span class="player-name">${entry.player}</span>
        <span>${entry.wins}</span>
        <span>${entry.losses}</span>
        <span>${entry.pushes}</span>
        <span class="${entry.net >= 0 ? "net-positive" : "net-negative"}">${formatCurrency(entry.net)}</span>
      </div>
    `).join("")}
  `;
}

function renderWeekBoard() {
  const weekName = state.selectedWeek;
  const weekPicks = getPicksForWeek(weekName);
  const standings = getStandingsForWeek(weekName);
  const games = Object.values(state.resultsByWeek[weekName] || {});

  els.weekTitle.textContent = weekName;

  els.weekContent.innerHTML = `
    <div class="week-card">
      <div class="panel-header">
        <p class="panel-kicker">THIS WEEK</p>
        <h3>Player Picks</h3>
      </div>
      <div class="player-picks-list">
        ${PEOPLE.map((player) => {
          const picks = weekPicks.filter((pick) => pick.player === player);
          return `
            <div class="player-pick-item">
              <strong>${player}</strong>
              ${picks.length ? picks.map((pick) => `<div>${pick.game} · ${getPickSummary(pick)} · ${pick.type.toUpperCase()}</div>`).join("") : `<div>No picks</div>`}
            </div>
          `;
        }).join("")}
      </div>
    </div>

    <aside class="side-card">
      <div class="panel-header">
        <p class="panel-kicker">STANDINGS</p>
        <h3>${weekName}</h3>
      </div>
      <div class="standings-table">
        <div class="standings-row header">
          <span>Player</span>
          <span>W</span>
          <span>L</span>
          <span>P</span>
          <span>Net</span>
        </div>
        ${standings.map((entry) => `
          <div class="standings-row">
            <span class="player-name">${entry.player}</span>
            <span>${entry.wins}</span>
            <span>${entry.losses}</span>
            <span>${entry.pushes}</span>
            <span class="${entry.net >= 0 ? "net-positive" : "net-negative"}">${formatCurrency(entry.net)}</span>
          </div>
        `).join("")}
      </div>

      <div class="week-results" style="margin-top: 18px;">
        <h3>Results</h3>
        ${games.length
          ? games.map((game) => `
              <div class="result-item">
                <strong>${game.away_team} @ ${game.home_team}</strong>
                <small>${game.status === "final" ? `${game.away_score} - ${game.home_score}` : game.status}</small>
              </div>
            `).join("")
          : `<p class="empty-state">No results loaded yet.</p>`}
      </div>
    </aside>
  `;
}

function getPicksForWeek(weekName) {
  return state.picks.filter((pick) => pick.week === weekName);
}

function getPickSummary(pick) {
  if (pick.type === "total") {
    return `${pick.bet.toUpperCase()} ${Number(pick.spread || 0)}`;
  }

  const label = pick.bet || "Pick";
  return `${label} ${formatSpread(Number(pick.spread || 0))}`;
}

function resolvePickAgainstGame(pick) {
  const game = (state.resultsByWeek?.[pick.week] || {})[pick.game];
  if (!game || game.status !== "final") {
    return "pending";
  }

  const awayTeam = game.away_team;
  const homeTeam = game.home_team;
  const awayScore = Number(game.away_score || 0);
  const homeScore = Number(game.home_score || 0);

  if (pick.type === "side") {
    const betTeam = String(pick.bet || "");
    const spread = Number(pick.spread || 0);
    const selectedTeam = betTeam === awayTeam ? awayTeam : betTeam === homeTeam ? homeTeam : null;

    if (!selectedTeam) {
      return "pending";
    }

    const adjustedSelected = selectedTeam === awayTeam ? awayScore + spread : homeScore + spread;
    const opponentScore = selectedTeam === awayTeam ? homeScore : awayScore;

    if (adjustedSelected > opponentScore) return "win";
    if (adjustedSelected < opponentScore) return "loss";
    return "push";
  }

  if (pick.type === "total") {
    const totalScore = awayScore + homeScore;
    const spread = Number(pick.spread || 0);
    const betValue = String(pick.bet || "").toLowerCase();

    if (betValue === "over") {
      if (totalScore > spread) return "win";
      if (totalScore < spread) return "loss";
      return "push";
    }

    if (betValue === "under") {
      if (totalScore < spread) return "win";
      if (totalScore > spread) return "loss";
      return "push";
    }
  }

  return "pending";
}

function getStandingsForWeek(weekName) {
  return PEOPLE.map((player) => {
    const picks = state.picks.filter((pick) => pick.player === player && pick.week === weekName);

    const summary = picks.reduce(
      (result, pick) => {
        const outcome = resolvePickAgainstGame(pick);
        if (outcome === "win") {
          result.net += calculatePayout(Number(pick.odds || 0), Number(pick.stake || 0));
          result.wins += 1;
        } else if (outcome === "loss") {
          result.net -= Number(pick.stake || 0);
          result.losses += 1;
        } else if (outcome === "push") {
          result.pushes += 1;
        }
        return result;
      },
      { wins: 0, losses: 0, pushes: 0, net: 0 }
    );

    return {
      player,
      wins: summary.wins,
      losses: summary.losses,
      pushes: summary.pushes,
      net: summary.net
    };
  }).sort((a, b) => b.net - a.net);
}

function calculatePayout(odds, stake) {
  if (odds > 0) {
    return stake * (odds / 100);
  }
  if (odds < 0) {
    return stake * (100 / Math.abs(odds));
  }
  return 0;
}

function formatCurrency(value) {
  const numberValue = Number(value || 0);
  const prefix = numberValue >= 0 ? "+$" : "-$";
  const absolute = Math.abs(numberValue).toFixed(2);
  return `${prefix}${absolute}`;
}

function formatSpread(value) {
  const absValue = Math.abs(value);
  return value >= 0 ? `+${absValue}` : `-${absValue}`;
}

init();
