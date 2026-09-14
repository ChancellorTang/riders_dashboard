# Vice City Picks Challenge

A static dashboard for tracking a small weekly NFL picks league. It renders the league standings and each week's picks directly from committed JSON files, so it works well for a GitHub Pages deployment without needing a backend.

## What this project does

- Shows a home screen with:
  - this week's picks
  - current standings
  - wins / losses / pushes and net value
- Shows a week-by-week board for each player
- Resolves picks against weekly game results in the JSON data files
- Requires no database or server-side write logic

## Project structure

```text
.
├── app.js
├── index.html
├── styles.css
├── README.md
├── data/
│   ├── profiles/
│   │   ├── chance.json
│   │   ├── jay.json
│   │   ├── joe.json
│   │   └── kyle.json
│   └── week_1/
│       └── results.json
└── .gitignore
```

## Data model

### Player profile files

Each player profile is stored in `data/profiles/<player>.json`.

Example shape:

```json
{
  "player": "Chance",
  "weeks": [
    {
      "week": 1,
      "locked_at": "2026-09-13T00:00:00Z",
      "picks": [
        {
          "game": "BAL@IND",
          "bet": "BAL",
          "type": "side",
          "spread": -3.5,
          "odds": -105,
          "locked_at": "2026-09-13T00:00:00Z"
        }
      ]
    }
  ]
}
```

### Weekly results files

Each week's game results are stored in `data/week_<n>/results.json`.

Example shape:

```json
{
  "week": 1,
  "updated_at": "2026-09-14T17:18:45.751985+00:00",
  "games": [
    {
      "game_id": "BAL@IND",
      "away_team": "BAL",
      "home_team": "IND",
      "away_score": 41,
      "home_score": 23,
      "status": "final"
    }
  ]
}
```

Notes:

- `game_id` must match the `game` value used in the player picks.
- A game can be `pending` until the result is locked in.
- Final results are only used to resolve picks once `status` is `final`.

## How to run locally

Because this is a static app, you can run it in one of two ways:

### Option 1: Open directly in a browser

Open `index.html` directly in the browser.

### Option 2: Serve it locally

From the project root:

```bash
python3 -m http.server 8000
```

Then open:

```text
http://localhost:8000
```

## Deploying to GitHub Pages

This app is designed to be deployed as a static site.

1. Push the repo to GitHub.
2. Enable GitHub Pages in the repository settings.
3. Use the root branch or a docs folder if needed.
4. The dashboard will load the JSON files from the repo as-is.

## Weekly update workflow

1. Update the player profile JSON files with the current week's picks.
2. Add or update the weekly results file in `data/week_<n>/results.json`.
3. Commit the changes.
4. Push to GitHub.
5. Refresh the page to view the latest standings.

## Important limitations

- This is intentionally a read-only static dashboard.
- No browser form writes to files.
- All data updates happen by editing JSON files and pushing the repo.
- Because of GitHub Pages restrictions, there is no backend to persist changes automatically.

## Required files for the app to run

The dashboard expects these files to exist:

- `index.html`
- `styles.css`
- `app.js`
- `data/profiles/chance.json`
- `data/profiles/jay.json`
- `data/profiles/joe.json`
- `data/profiles/kyle.json`
- `data/week_1/results.json`

If a new week is added, create a matching folder and result file such as `data/week_2/results.json`.
