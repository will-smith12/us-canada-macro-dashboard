# macro_refresh

A single tool that refreshes **`~/Downloads/master_economics_data.xlsx`** on a
weekly schedule, pulling from four sources:

| Pipeline | Source | Auth | Sheets produced |
|----------|--------|------|-----------------|
| `te`      | Trading Economics — **headless website scrape** | none | `Summary`, category sheets (`GDP`, `Labour`, `Prices`, `Money`, `Trade`, `Government`, `Business`, `Consumer`, `Markets`, `Housing`), and key-indicator sheets (`Unemployment Rate`, `Inflation Rate`, …) |
| `fredboc` | FRED + Bank of Canada (Valet) | FRED API key (BoC needs none) | `FRED Vintage - GDP/CPI/Payrolls`, `US Financial Conditions`, `US SLOOS`, `Commodity Prices`, `Canada (BoC)` |
| `cfib`    | CFIB Business Barometer (monthly workbook) | none | `CFIB Barometer`, `CFIB Barometer (Tidy)` |
| `potgdp`  | FRED (CBO potential GDP) + BoC Valet (output gap) | FRED API key | `Potential GDP & Output Gap` |

The `te` pipeline rebuilds the workbook from scratch, then `fredboc`, `cfib` and
`potgdp` append their sheets — so a full refresh runs all four **in order**.

## How the Trading Economics scrape works

TE serves each indicator's chart data from a CloudFront host as an *encrypted*
payload that the page decrypts client-side into a Highcharts series, defaulting
to ~12 points. The scraper opens each public indicator page in headless
Chromium, **intercepts the chart request and rewrites its `n` (point-count)
parameter** up to `TE_MAX_POINTS`, so the page decrypts the *full* history, then
reads the decoded series straight out of Highcharts. No API key, and it's
resilient to HTML/DOM changes because it reads the chart's data model.

### Scrape robustness

TE occasionally serves an empty chart under load, so a full run would otherwise
drop a different handful of indicators each time. Three layers guard against this:

- **Backoff + jitter between retry attempts** (`_scrape_one`): instead of retrying
  instantly, it waits `min(TE_RETRY_MAX_DELAY, TE_RETRY_BASE_DELAY · 2^(n-1))` with
  jitter, giving transient throttling / slow-CDN conditions time to clear.
- **Worker stagger** (`TE_WORKER_STAGGER`): a small random pre-navigation delay on
  the high-concurrency main pass de-syncs simultaneous heavy page loads.
- **Final retry sweep**: after the main pass, indicators with no data are
  re-scraped **at low concurrency** (`TE_SWEEP_CONCURRENCY`, default 1) with more
  attempts (`TE_SWEEP_RETRIES`) and a longer poll budget (`TE_SWEEP_POLL_ROUNDS`).
  Once the bulk is done TE stops throttling, so most transient dropouts recover
  here. The sweep logs `recovered X/Y; still missing: …`.

All knobs are env-overridable (e.g. `MACRO_TE_SWEEP_CONCURRENCY`,
`MACRO_TE_POLL_ROUNDS`, `MACRO_TE_RETRY_BASE_DELAY`, `MACRO_TE_WORKER_STAGGER`),
mirroring `MACRO_TE_CONCURRENCY`. There is no last-good cache: an indicator that
genuinely can't be scraped (and isn't backfilled) is simply left to whatever TE
serves, rather than silently substituting stale data.

## Backfilling missing / truncated TE indicators

A handful of TE indicators only ever expose a short window through the encrypted
chart feed (they scrape **missing** or **truncated**), or scrape *intermittently*
(the chart occasionally returns empty). For a curated set of those (**43
indicators**), `te_backfill.py` substitutes **full-history data from
authoritative free providers** at the data layer — *before* the workbook is
built — so the category and key-indicator sheets come out complete. TE remains
the source for every other indicator.

- **FRED** (US): Inflation Rate / MoM (`CPIAUCSL` via `pc1`/`pch`), Interest Rate
  (`DFEDTAR`+`DFEDTARU` splice), Effective Fed Funds (`DFF`), 10Y (`DGS10`),
  jobless claims (`ICSA`/`CCSA`/`IC4WSA`), mortgage rates (`MORTGAGE15US`/
  `MORTGAGE30US`), Fed balance sheet (`WALCL`), Job Vacancies / Job Offers
  (`JTSJOL`), Job Quits (`JTSQUL` / rate `JTSQUR`), Layoffs (`JTSLDL`),
  Factory Orders (`AMTMNO` MoM%), Retail Trade Payrolls (`USTRADE` change),
  Exports (`BOPTEXP`), SOFR (`SOFR`), Employment Rate (`EMRATIO`), Energy
  Inflation (`CPIENGNS` YoY), Existing Home Sales (`EXHOSLUSM495S`) + MoM,
  Philly Fed CAPEX (`CEFDFSA066MSFRBPHI`), the retail-sales sub-component
  MoMs via the Census **advance** report (`MARTSSM44W72USS`, `RSDBS`, `RSFHFS`,
  `RSGASS`, plus Ex-Autos `RSFSXMV`, Ex-Fuel `MARTSMPCSM44Z72USS`, Electronics
  `MARTSMPCSM443USS`), and ECI Wages (All-Civilian wages&salaries
  `CIS1020000000000I`, QoQ%).
- **Bank of Canada Valet** (CA): Interest Rate (`V39079`), 10Y
  (`BD.CDN.10YR.DQ.YLD`).
- **StatCan WDS** (CA): Inflation Rate / MoM (CPI all-items vector `v41690973`,
  YoY/MoM computed locally — fresher than FRED's OECD Canada CPI); Capacity
  Utilization (total industrial, vector `v4331081`, table 16-10-0109); GDP by
  industry levels (table 36-10-0434, chained 2017$ SAAR): Mining `v65201236`,
  Public Administration `v65201476`, Services-producing `v65201212`,
  Transportation & warehousing `v65201381`.

Each registry entry carries a `scale` factor so the filled column matches TE's
stated unit (e.g. FRED jobless claims are in persons → ×0.001 for TE's
"Thousand"; `BOPTEXP` USD millions → ×0.001 for TE's "USD Billion"; Existing Home
Sales units → ×0.001 for "Thousand").

Two source nuances worth knowing:
- **Retail sub-components use the *advance* MARTS series**, not the *final* MRTS
  series — the final series lag a month and won't match TE's latest MoM print.
- **`Job Offers` and `Job Vacancies` both map to `JTSJOL`.** Job Offers matches
  the API exactly; TE's separate "Job Vacancies" figure has no exact free
  equivalent, so it stays a small documented diff (≈ −7%).

The gap list was seeded by `te_coverage_diag.py` (a re-runnable audit that
compares each scraped series' earliest date against TE's `FirstValueDate`,
frozen at `te_coverage.csv`) and extended via `te_vs_api.py`, which benchmarks
the full output against the cached paid-API history in `raw_te/{US,CA}_batch_*.json`.
Re-run either after TE site changes to surface new gaps for the registry.

**Out of scope** (no clean free source — documented in `te_backfill.OUT_OF_SCOPE`,
intentionally left to whatever TE serves): US MBA mortgage indices, regional Fed
surveys (Kansas/Richmond), Challenger job cuts, External Debt, Stock Market
(FRED S&P 500 is licence-capped to 10y), weekly crude production; CA Government
Spending, Gross National Product, TSX, Gross Fixed Capital Formation (FRED series
stale to 2023; no matching free StatCan vector); and the **ISM Non-Manufacturing
(Services PMI) sub-indices** (Employment / New Orders / Prices) — ISM is
proprietary and pulled its series from FRED over licensing, so no free
equivalent exists.

Disable the layer with `--no-backfill` (on either `te_scrape` or `refresh`).

## Setup

```bash
cd ~/Downloads
# deps (already installed in ~/venv): requests, openpyxl, pandas, playwright
/Users/william.smith/venv/bin/python3 -m pip install -r macro_refresh/requirements.txt
/Users/william.smith/venv/bin/python3 -m playwright install chromium

# optional: set your own FRED key (otherwise the bundled one is used)
cp macro_refresh/.env.example macro_refresh/.env
# edit macro_refresh/.env -> FRED_API_KEY=...
```

> Only FRED needs a key. BoC Valet and the TE scrape need none.

## Usage

Run as a module from `~/Downloads` (so the package and the sibling legacy
scripts it reuses are importable):

```bash
cd ~/Downloads

# Full weekly refresh (all four pipelines, full TE breadth)
python3 -m macro_refresh.refresh

# Faster TE (only the key indicators, leaves category sheets sparse)
python3 -m macro_refresh.refresh --te-scope key

# Just one pipeline (appends to the existing master)
python3 -m macro_refresh.refresh --only fredboc
python3 -m macro_refresh.refresh --only cfib potgdp

# Keep TE sheets, refresh everything else
python3 -m macro_refresh.refresh --skip te

# Scrape TE but skip the FRED/BoC/StatCan backfill of missing indicators
python3 -m macro_refresh.refresh --no-backfill

# Don't write a pre-run backup
python3 -m macro_refresh.refresh --no-backup

# Write to a different workbook (e.g. a test copy)
python3 -m macro_refresh.refresh --target /tmp/test.xlsx
```

### Safety behaviour
- **Backup**: before each run the master is copied to
  `master_economics_data.BACKUP-YYYY-MM-DD-HHMMSS.xlsx` (skip with `--no-backup`).
- **Open-workbook guard**: aborts if Excel has the file open (`~$…` lock present).
- **Failure isolation**: if one pipeline fails, the others still run; the process
  exits non-zero and the summary lists what failed.
- **Logs**: every run writes `macro_refresh/logs/refresh-YYYYMMDD-HHMMSS.log`.

## Weekly schedule (macOS `launchd`)

A ready-made user agent runs the full refresh **every Monday at 07:00**. If the Mac
is asleep/off at that time, `launchd` runs it at the next wake (built-in catch-up).

```bash
# install
cp ~/Downloads/macro_refresh/com.willsmith.macrorefresh.plist \
   ~/Library/LaunchAgents/

launchctl load ~/Library/LaunchAgents/com.willsmith.macrorefresh.plist
#   modern equivalent: launchctl bootstrap gui/$(id -u) \
#       ~/Library/LaunchAgents/com.willsmith.macrorefresh.plist

# verify it's registered (and see scheduling details)
launchctl list | grep macrorefresh
launchctl print gui/$(id -u)/com.willsmith.macrorefresh

# optional: trigger a real run now (NOTE: rewrites the master; backs up first)
launchctl start com.willsmith.macrorefresh

# stop scheduling / uninstall
launchctl unload ~/Library/LaunchAgents/com.willsmith.macrorefresh.plist
#   modern equivalent: launchctl bootout gui/$(id -u)/com.willsmith.macrorefresh
```

After editing the plist (e.g. to change the day/time), reload it:

```bash
launchctl unload ~/Library/LaunchAgents/com.willsmith.macrorefresh.plist
cp ~/Downloads/macro_refresh/com.willsmith.macrorefresh.plist ~/Library/LaunchAgents/
launchctl load   ~/Library/LaunchAgents/com.willsmith.macrorefresh.plist
```

Edit the `StartCalendarInterval` block in the plist to change the day/time
(`Weekday` 1 = Monday). The agent uses `~/venv/bin/python3` and runs from
`~/Downloads`. `launchd` job stdout/stderr go to
`macro_refresh/logs/launchd.out.log` / `launchd.err.log`; each run also writes its
own `macro_refresh/logs/refresh-YYYYMMDD-HHMMSS.log`.

## Files

```
macro_refresh/
├── refresh.py          orchestrator CLI (entry point)
├── config.py           paths, FRED key, TE scrape tuning, .env loader
├── te_scrape.py        Trading Economics headless scraper
├── te_backfill.py      FRED/BoC/StatCan backfill for missing/truncated TE series
├── te_coverage.csv     frozen coverage audit (478 ok / 29 truncated / 16 missing)
├── te_coverage_diag.py re-runnable audit that compares scraped span vs TE FirstValueDate
├── te_vs_api.py        benchmarks scraped+backfilled output vs the cached paid TE API
├── te_vs_api_report.csv per-indicator comparison (verdict, diffs, coverage)
├── fred_boc.py         FRED + BoC (wraps fetch_fred_boc.py)
├── cfib.py             CFIB Barometer (curl download + cfib_to_master.py)
├── potential_gdp.py    Potential GDP & Output Gap (wraps add_potential_gdp.py)
├── _legacy.py          helper to drive the legacy scripts with logging
├── requirements.txt
├── .env.example
├── com.willsmith.macrorefresh.plist
└── logs/
```

It reuses the existing, tested scripts in `~/Downloads`
(`fetch_economics.py` builders, `fetch_fred_boc.py`, `cfib_refresh.py`,
`cfib_to_master.py`, `add_potential_gdp.py`); those originals are left untouched.
