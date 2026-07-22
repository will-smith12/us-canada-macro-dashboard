# Canada Housing Price Indices — Dashboard

A self-contained, **offline** dashboard for Canada's three main house-price index
families, pulled from source into `~/Downloads/canada_housing_indices.xlsx`:

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
~/Downloads/housing_indices/build_housing_indices.py   # pulls sources -> canada_housing_indices.xlsx
        │
        ▼
build_dashboard_data.py   # reads the workbook -> data.js (window.HOUSING_DATA) + data.json
        │
        ▼
index.html                # offline frontend (bundled Chart.js)
```

Rebuild after refreshing the workbook:

```bash
~/.venv-relanalysis/bin/python build_dashboard_data.py
```

## Files

- `index.html` — the dashboard (self-contained; bundled `chart.umd.min.js`, `chartjs-plugin-zoom.min.js`, `hammer.min.js`).
- `build_dashboard_data.py` — regenerates `data.js` / `data.json` from the workbook.
- `data.js` / `data.json` — generated data payload.
- `start.command` — local-server launcher.

## Caveats

- The three methods measure different things — **levels are not directly comparable; growth rates are**.
- The StatCan appraisal series ends 2015 (program discontinued). Post-2015 points are the **Alberta equalized-assessment extension** (market-audited, authority-specific), shown with a note. See the workbook's `Provincial_Sources` sheet to extend other provinces.
