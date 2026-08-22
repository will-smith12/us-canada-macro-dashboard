# Canada Housing Price Indices — Dashboard

A self-contained, **offline** dashboard for Canada's three main house-price index
families, pulled from source into `data/canada_housing_indices.xlsx`:

| Family | Method | Coverage |
|--------|--------|----------|
| **Teranet–National Bank HPI** | Repeat-sales | Composite 11 + 11 CMAs, monthly, 1990→ |
| **CREA MLS® HPI** | Hedonic / benchmark | National + 9 provinces × 6 property types, monthly, 2005→ |
| **StatCan / provincial assessment** | Appraisal / assessment | Canada + provinces/territories, annual (+ Alberta 2024–26 extension) |

## Run it

```bash
./start.command          # serves on http://localhost:8078 and opens the browser
# or just double-click start.command in Finder
# or open index.html directly (file://) — everything is bundled, no network needed
```

## Features

- **Overview** — one card per index family (national headline + latest YoY sparkline) plus a national-comparison card.
- **Explore** — pick a family, measure (index level / MoM% / YoY% / benchmark $ / assessment $), and for CREA a property type; overlay any set of geographies via the chips. Wheel/drag to zoom, shift-drag to pan, quick 5y/10y/All ranges.
- **Compare national** — Teranet C11, CREA national and StatCan Canada together, as YoY % (single axis) or levels (dual axis: index vs C$).
- **🗺 Map** — the houses laid over a real map of Canada, each sitting on its city (Teranet CMAs) or province (CREA / StatCan). Houses are **sized by magnitude** and **colored green (rising) / red (falling)**, every province/territory is marked with its **abbreviation** (BC, AB, …, NU) for quick identification, and the national headline is shown as a badge. Drag the **year slider** or press **▶ Play** to watch the market move through time; click a house to open it in Explore. The outline is bundled (`canada_geo.js`) so it works fully offline, and land + houses share one Lambert Conformal Conic projection so placement is accurate.
- **PNG / CSV export** on every chart.

## Data pipeline

```
build_housing_indices.py    # fetches Teranet + CREA + StatCan/Alberta
        │                   #   -> data/canada_housing_indices.xlsx
        ▼
build_dashboard_data.py     # reads the workbook -> data.js (window.HOUSING_DATA) + data.json
        │
        ▼
index.html                  # offline frontend (bundled Chart.js)
```

Full rebuild from source (both steps, no API key needed — all sources are public):

```bash
pip install -r requirements.txt     # pandas + openpyxl
python build_housing_indices.py     # ~2 min; fetches into _work/, writes data/
python build_dashboard_data.py      # regenerates data.js / data.json
```

If you only changed how the payload is shaped, the second step alone is enough — the
committed workbook in `data/` is a valid input on its own.

Paths resolve next to the scripts, so a fresh clone works anywhere with no configuration.
`HOUSING_XLSX` and `HOUSING_WORK` override the workbook and scratch locations if needed.
`build_housing_indices.py --no-fetch` reuses whatever is already in `_work/` (offline re-run).

> **Why the workbook is committed.** Several upstream URLs are dated — CREA is keyed by
> month, Alberta's open-data resources by year — so they will eventually stop resolving.
> The committed workbook means the dashboard stays rebuildable even after that happens.
> The bulk raw downloads are *not* committed; they re-fetch into the gitignored `_work/`.

## Files

- `index.html` — the dashboard (self-contained; bundled `chart.umd.min.js`, `chartjs-plugin-zoom.min.js`, `hammer.min.js`).
- `build_housing_indices.py` — fetches the three source families into `data/canada_housing_indices.xlsx`.
- `build_dashboard_data.py` — regenerates `data.js` / `data.json` from the workbook.
- `data/canada_housing_indices.xlsx` — the source workbook (committed; see note above).
- `data.js` / `data.json` — generated data payload.
- `start.command` — local-server launcher.
- `_work/` — scratch space for fetched source files; gitignored, safe to delete.

## Caveats

- The three methods measure different things — **levels are not directly comparable; growth rates are**.
- The StatCan appraisal series ends 2015 (program discontinued). Post-2015 points are the **Alberta equalized-assessment extension** (market-audited, authority-specific), shown with a note. See the workbook's `Provincial_Sources` sheet to extend other provinces.
