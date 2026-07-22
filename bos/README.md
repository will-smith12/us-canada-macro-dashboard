# Business Outlook Survey — Dashboard

A self-contained, interactive dashboard for the **Bank of Canada Business
Outlook Survey (BOS)** disaggregated panels — each survey indicator broken down
**by sector, region and firm size** (quarterly four-quarter moving averages,
2004 Q1 – 2026 Q2, **Canada only**).

**🔗 Live:** https://will-smith12.github.io/bos-dashboard/

Built from `~/Downloads/BoC_BOS_sector_region.xlsx` (the tidy BOS spreadsheet
harvested from the public BoC Valet API).

## Run it

**Online:** just open the [live site](https://will-smith12.github.io/bos-dashboard/)
(served from this repo via GitHub Pages).

**Easiest locally:** double-click **`index.html`** — it opens in your browser and
works directly (data is embedded in `data.js`, Chart.js is bundled locally, so it
runs fully offline with no server or network).

**Or double-click `start.command`** to serve it over HTTP.

**Or from a terminal:**

```bash
cd ~/bos-dashboard
python3 -m http.server 8077
# then open http://localhost:8077
```

## What's in it

- **Overview** — a grid of small-multiple cards, one per indicator (14 Business
  Outlook Survey indicators, **plus** a Canada-vs-U.S. small-business sentiment
  card), each a mini multi-line chart. Click any card to drill in.
- **⚑ Filter** (in the chart's toolbar, right above the graph) — choose which
  series appear. The panel is **context-aware**: on a BoS indicator it filters by
  **sector**, **region** and **firm size**; on the Canada-vs-U.S. card it filters
  by **country** (show just Canada or just the U.S. — the hidden country's line
  *and* its axis drop out). The selection is applied to **both** the detail chart
  and the overview cards, stays in sync with the detail legend chips, and is
  remembered across indicators and page reloads (saved in the browser). The badge
  shows how many series are currently hidden in the current view; *Reset all*
  restores everything.
- **Detail view** — pick an **indicator**, a **subcomponent** (where an
  indicator has more than one, e.g. Capacity pressures, Inflation expectations),
  and a **breakdown** (Sector / Region / Firm size — auto-disabled where a
  breakdown isn't published). Features:
  - multi-series line chart with per-member **legend chips** (click to
    show/hide; *Show all* / *Hide all*),
  - **5Y / 10Y / All** quick ranges, plus drag-to-zoom, wheel-zoom and
    Shift-drag pan,
  - **PNG** and **CSV** export of the current view,
  - the underlying **survey question**, source, and the four-quarter
    moving-average caveat.
- **Business sentiment — Canada vs U.S.** — an extra card comparing the
  **CFIB Business Barometer** (Canada) with the **NFIB Small Business Optimism
  Index** (United States), monthly since 2000. Because the two use different
  scales they're drawn on a **dual axis** (Canada left, U.S. right); the legend
  chips — or the **⚑ Filter** *Country* group — toggle each country, and viewing
  a single country leaves just that series on its own axis.

Units are never mixed on one axis — each BoS indicator carries a single unit
(*Balance of opinion*, *% of firms*, or *Standardized units*). The Regional BOS
indicator is Region-only (shorter history, standardized units).

## Refreshing the data

The dashboard reads the tidy spreadsheet and rebuilds its two data files:

```bash
~/.venv-relanalysis/bin/python build_bos_data.py
# writes data.json + data.js next to index.html
```

To pull **new quarters** from the Bank of Canada first, re-run the upstream
harvester, then rebuild:

```bash
~/.venv-relanalysis/bin/python ~/Downloads/bos_harvest/build_xlsx.py   # refresh BoC_BOS_sector_region.xlsx
~/.venv-relanalysis/bin/python build_bos_data.py                        # rebuild dashboard data
```

The Canada-vs-U.S. sentiment card is pulled from the already-generated
`~/us-canada-macro-dashboard/data.json` (its "Small Business Sentiment"
indicator). If that file is absent, the build simply skips the card.

`build_bos_data.py` prints a verification summary (indicator / member / quarter
counts and data-point totals) each run.

## Publishing / updating GitHub Pages

This repo is served as a static site at
**https://will-smith12.github.io/bos-dashboard/** (Pages source: `main`
branch, root). To publish updates after a data refresh, just commit and push —
Pages rebuilds automatically:

```bash
cd ~/bos-dashboard
~/.venv-relanalysis/bin/python build_bos_data.py   # refresh data.js + data.json
git commit -am "Refresh BoS data"
git push                                           # Pages redeploys in ~1 min
```

`.nojekyll` is committed so GitHub serves the files as-is (no Jekyll
processing).

## Files

- `index.html` — the dashboard app (self-contained; uses the bundled libs below).
- `build_bos_data.py` — extracts `data.js` + `data.json` from
  `BoC_BOS_sector_region.xlsx` (tidy sheets `Sector_tidy` / `Region_tidy` /
  `Size_tidy` + `Definitions` / `Notes`).
- `data.js` — data embedded as JS so the page works when opened directly (`file://`).
- `data.json` — the same payload as JSON (used when served over HTTP).
- `chart.umd.min.js`, `chartjs-plugin-zoom.min.js`, `hammer.min.js` — Chart.js +
  zoom/pan, bundled so the app works offline.
- `start.command` — one-click local HTTP launcher.

## Source

Bank of Canada, **Business Outlook Survey** (Valet API, public — no key). Values
are four-quarter moving averages and may not match the aggregate BOS figures
published each quarter.
