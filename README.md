# US &amp; Canada Macro Indicators — Dashboard App

A self-contained, tabbed dashboard generated from `US_Canada_Macro_Indicators.xlsx`.
Each tab shows one macro indicator with a chart comparing **Canada** vs **United States**.

## Run it

**Easiest:** just **double-click `index.html`** — it opens in your browser and works directly
(data is embedded in `data.js`). You can also double-click `start.command` to serve it over HTTP.

**Or from a terminal:**

```bash
cd ~/Desktop/US_Canada_Macro_Dashboard
python3 -m http.server 8077
# then open http://localhost:8077
```

> Works fully offline — Chart.js is bundled locally (`chart.umd.min.js`).

## Tabs (one chart each)

| Indicator | Chart type |
|---|---|
| GDP Growth Rate QoQ (%) | line |
| GDP per Capita (USD) | line |
| Inflation Rate (%) | line |
| Policy Interest Rate (%) | stepped line |
| Labour Productivity (index) | line |
| Gross Fixed Capital Formation | line (dual axis) |
| GDP (USD B) | line |
| Households Debt to GDP (%) | line |
| Unemployment Rate (%) | line |

## Files

- `index.html` — the dashboard app (uses bundled `chart.umd.min.js`).
- `chart.umd.min.js` — Chart.js library (bundled so the app works offline).
- `data.js` — data embedded as JS so the page works when opened directly (file://).
- `data.json` — same data as JSON (used if served over HTTP).
- `generate_data.py` — re-extracts `data.js` + `data.json` from the Excel file. Re-run after updating the spreadsheet:
  ```bash
  python3 generate_data.py
  ```
- `start.command` — one-click launcher.

## Notes

- Tabs are limited to indicators with complete data for **both** countries. Two source
  series with no US history (GDP Growth Annualized, Households Debt to Income — subscriber-gated)
  are excluded automatically by `generate_data.py`.
- Gross Fixed Capital Formation uses different units per country (CAD Million vs USD Billion),
  so it is plotted on dual y-axes.
