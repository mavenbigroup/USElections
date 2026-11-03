# Midterm Night Board

Single-file, zero-build election board for the November 3, 2026 US midterms. Open `index.html` in a browser or serve it from GitHub Pages.

## What it does

- **Top strip**: Senate and House with three readings each: AP called, prediction-market odds, and the model's call.
- **Sliders**: adjust the model live.
  - *Independents break*: how unaffiliated voters split (baseline D+13, Reuters/Ipsos).
  - *Dem turnout surge* / *GOP turnout surge*: points added to the remaining-ballot margin on Election Day.
  - *Remaining undecideds break*: NYT/Siena's final battleground poll found last-month deciders went R+9; applied to the ~6% still undecided (default R+9).
  - *Trust polls vs early-vote history*: blend for the model call.
- **Map**: colored by modeled final margin; states without a party-split early vote use 2024 presidential margin + national swing. Click a state for the early/remaining ballot bar, both lenses, the statewide races, and Cook's competitive House seats.
- **Senate table**: every race that decides control, with the model margin and win probability at the current slider settings.

## Model

For each of 16 modeled states:

1. Expected 2026 turnout = 2022 turnout × 1.07.
2. Early-vote margin = 0.9 × (Dem reg − Rep reg) + (independents slider) × other share.
3. **Polls lens**: the margin the remaining ballots need for the final poll average to hold.
4. **History lens**: remaining ballots skew R by the state's usual Election Day gap (22 pts mail-heavy, 12 pts in-person-early), plus Dem surge minus GOP surge.
5. **Model call** = trust × adjusted poll + (1 − trust) × history-lens final.

Senate: start at 47 D; flips and holds decided by the model margin, probability via a logistic (σ ≈ 3.2). House: 230 D at a D+9 national margin, 6.3 seats per point.

## Data

- Early ballots: On Point Politics / civicAPI, snapshot 12:10 pm MST Nov 3. State-reported party registration where available (AZ, NV, FL, NC, PA, IA, KS, ME, CO, NJ, OR); On Point model elsewhere. KS and ME totals approximate.
- Polls: final averages from NYT/Siena, Atlas, Emerson, YouGov, CNN, Silver Bulletin, On Point forecast.
- Markets: Kalshi and Polymarket, midday Nov 3.
- House ratings: Cook Political Report via 270toWin, Oct 23 2026.
- Map: `us-atlas` states-albers-10m, embedded.

All data is inline in `index.html` (`M`, `EO`, `SEN`, `GOV`, `HOUSE` constants). To update: edit the constants and reload. The "AP called" tiles are static placeholders; wire them to a feed or edit by hand as races are called.

## Dependencies

d3 7.8.5 and topojson-client 3.0.2 from cdnjs; Archivo and IBM Plex Mono from Google Fonts. No build step.

## Caveats

This is a what-if tool, not a forecast with error bars. The early-vote-to-vote conversion, the Election Day skew constants, and the seats-per-point figure are all judgment calls documented above.

## Live refresh

- `.github/workflows/refresh.yml` runs `fetch_data.py` every 5 minutes (GitHub's cron floor; real cadence is often 5–15 min) and commits `data.json` when it changes. Enable Actions on the repo; the workflow needs the default `contents: write` permission, which is set in the file.
- `index.html` re-reads `data.json` every 30 seconds and also tries Polymarket (Gamma), PredictIt and Kalshi directly from the browser every 30 seconds. Whichever answers updates the Markets tiles and the status line under the header. If a feed blocks cross-origin requests, the page silently falls back to `data.json`.
- `fetch_data.py` pulls: Kalshi public trade API, Polymarket Gamma API, PredictIt marketdata API, On Point Politics early-vote tracker (national total and per-state rows, which update the modeled states' ballot counts and party shares), UF Election Lab national total, and `calls.json`.
- `calls.json`: edit by hand as AP calls races. The next Action run folds it into `data.json` and the AP-called tiles update.

Every source is best-effort; a failing feed keeps its last good value and the status line names which sources answered.
