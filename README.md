# IC Risk Screener

A pre-queue "gut check" for PJM solar + storage sites. Describe up to 3 candidate sites in plain English. A small team of AI agents pulls real PJM interconnection history from Berkeley Lab data and returns a red-to-green risk heatmap on five interconnection cost drivers. Every flag links to its source, and each site gets a suggested next step.

> Ratings guide diligence. They are **not** cost estimates and do not replace PJM studies or engineering review.

## Run it (about 3 minutes)

Requires Python 3.11+.

```bash
git clone https://github.com/tg676/ic-risk-screener.git
cd ic-risk-screener
python -m venv .venv
```

Activate the virtual environment:

- Windows: `.venv\Scripts\activate`
- macOS / Linux: `source .venv/bin/activate`

```bash
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:8050**, click **Load example**, then **Screen sites** (about 20 seconds).

**API key.** The app reads `PORTKEY_API_KEY` from a `.env` file. It looks in the repo folder first, then **one folder up**. See `.env.example`. It uses only `gpt-6-luna` via Portkey.

## Auditing a rating

Every tile shows the numbers that decided its color. Clicking a tile opens an audit panel with three parts:

- **The AI's reasoning** and the source records it cited.
- **A rubric check.** The same written thresholds the AI analyst is given are re-applied in plain code (`audit.py`) to the exact data the analyst saw. The panel shows which rule triggered and whether the AI's color matches. Any difference is flagged **AI judgment** on the tile. A banner above the grid shows how many ratings match the rules.
- **The underlying Berkeley Lab records** for that county: interconnection studies, active queue requests by substation, or outcome history. They can be sorted and downloaded as CSV.

## What's inside

| File | What it does |
|---|---|
| `app.py` | Dash dashboard: heatmap, source drill-down, charts, token/cost meters |
| `agents.py` | Intake agent → Risk Analyst agents (one per site, in parallel, with tools) → Verifier (code) → Portfolio agent |
| `tools.py` | Deterministic data tools the analyst calls (queue history, upgrade costs, substation crowding, state rules) |
| `audit.py` | Re-checks every rating against the written rubric and returns the underlying records for the audit panel |
| `data/` | Compact CSVs built from Berkeley Lab data (VA, PA, OH), curated state siting rules, sample sites |
| `tests/` | Offline tests of each safety defense and of the audit rubric (`pip install -r requirements-dev.txt`, then `python -m pytest -q`; no API calls) |
| `scripts/benchmark.py` | Token/cost benchmark: compact vs. raw tool data |
| `scripts/build_data.py` | Rebuilds `data/*.csv` from the raw Berkeley Lab workbooks |
| `logs/` | Token usage per run (`runs.jsonl`), benchmark results, saved runs for `?replay=demo` |
| `report.html`, `slides.html` | Final report and slide deck (self-contained; rebuilt by `report/build.py`) |

## Data

- **Berkeley Lab, *Queued Up* (data through 2024)**: project-level interconnection queue records. The app uses PJM solar/storage requests since 2015 in VA, PA and OH.
- **Berkeley Lab, *Interconnection Cost Analysis in the PJM Territory***: network-upgrade costs from PJM interconnection studies, 2017+.
- **State siting rules**: curated from the cited statutes (`data/state_rules.json`).

The shipped CSVs are small (~400 KB), so no test dataset is needed. To rebuild them, download the two workbooks listed in `scripts/build_data.py` into `data/raw/` and run `python scripts/build_data.py`. Adding states means changing `STATES` there.

## Safety

- Prompt-injection pre-screen
- Intake-agent injection flag
- Code verifier that rejects citations no tool returned and strips dollar quotes
- Tool-loop cap, per-call output cap, per-session token budget, input length cap
- Inputs are not stored. Logs keep only site names and token counts.
