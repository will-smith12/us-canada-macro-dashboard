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

## News Desk (live LLM agents)

The **📰 News** button (top-right of the header) opens the **News Desk** — an overlay with three
feeds (Macro News, Government Updates, Social). Clicking it fires three Gemini agents that use
Google Search grounding to find the most relevant items per category. The **Government** agent is
restricted to official **US + Canadian government** sources (Federal Reserve, BLS, BEA, Treasury,
White House; Bank of Canada, Statistics Canada, Department of Finance, etc.) — both by prompt and
by a post-filter that drops any item not on an official `.gov` / `.gc.ca` domain.

This needs a small local backend (the page itself is static and can't hold API keys):

```bash
# Get a FREE Gemini API key at https://aistudio.google.com/apikey
export GEMINI_API_KEY=...                  # required
# optional: export GEMINI_MODEL=gemini-2.5-flash   (override the model)
./start_news_agents.command                # serves the agents on http://localhost:8181
```

Then open the dashboard over HTTP (`python3 -m http.server 8077`) and click **📰 News**. Each feed
shows a loading state while its agent researches, then the ranked results; the **↻** button re-runs
the agents and the **US / CA / All** filter narrows the view.

- Backend: `news_agents.py` (stdlib HTTP server + `httpx`; no extra packages needed).
- The key is read from the environment at runtime and never written to disk.
- Free-tier Gemini grounding has daily limits; the model is overridable via `GEMINI_MODEL`.
- This is a **local** feature — the agents backend isn't part of the static GitHub Pages deploy, so
  on the published site the feeds will show an "agents offline" message.

### Keep it always-on (recommended)

So you never see "agents offline" again, run the backend as a `launchd` service that starts at
login and restarts itself if it crashes. The key lives only in a private file — never in the plist.

```bash
# 1. Store the key once, in a private file outside the repo:
mkdir -p ~/.config/macro-dashboard
printf 'export GEMINI_API_KEY=%s\n' 'YOUR_KEY' > ~/.config/macro-dashboard/env
chmod 600 ~/.config/macro-dashboard/env

# 2. Load the service (plist: ~/Library/LaunchAgents/com.willsmith.newsdesk.plist):
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.willsmith.newsdesk.plist

# Status / logs:
launchctl print gui/$(id -u)/com.willsmith.newsdesk | grep -E 'state|pid'
tail -f ~/Library/Logs/newsdesk.err.log

# Stop / uninstall:
launchctl bootout gui/$(id -u)/com.willsmith.newsdesk
```

The agent sources `~/.config/macro-dashboard/env` and serves on :8181 with `KeepAlive` +
`RunAtLoad`. After editing `news_agents.py`, restart it with:
`launchctl kickstart -k gui/$(id -u)/com.willsmith.newsdesk`.

### Make the News Desk work for everyone (host the backend)

The local/launchd backend only serves *your* machine. To let visitors of the published
GitHub Pages site load news, host the backend somewhere with HTTPS and point the frontend
`NEWS_API` at it. The backend is container-ready (see `Dockerfile`) and reads these env vars:

| Var | Purpose | Default |
| --- | --- | --- |
| `GEMINI_API_KEY` | Gemini key (keep server-side; never in the static site) | — (required) |
| `PORT` | Port to bind (Cloud Run/Render set this) | `NEWS_PORT` or `8181` |
| `NEWS_HOST` | Bind address (use `0.0.0.0` in a container) | `127.0.0.1` |
| `NEWS_ALLOWED_ORIGIN` | CORS allow-list, comma-separated (or `*`) | `*` |
| `NEWS_TOKEN` | If set, `/api/news/*` requires `X-News-Token` (or `?token=`) | _(off)_ |
| `NEWS_RATE_LIMIT` / `NEWS_RATE_WINDOW` | Per-IP rate limit (requests / seconds) | `30` / `60` |
| `NEWS_CACHE_TTL` | Seconds before a cached feed is refreshed (stale-while-revalidate) | `720` |

> **Token caveat:** the frontend is public, so any token it sends is visible in page source —
> it deters drive-by bots but is not true secrecy. It is combined with a CORS allow-list and a
> per-IP rate limit to protect the Gemini quota.

**Caching & cold starts.** The backend keeps the last good feed per category in memory and
serves it instantly, refreshing in the background once it is older than `NEWS_CACHE_TTL`
(default 12 min). Responses include `cached_at` and `age_seconds` so the UI can show "Updated
Xm ago". On Render's free tier the service still sleeps after ~15 min idle, so a scheduled
GitHub Actions workflow (`.github/workflows/warm-news-desk.yml`) pings the three endpoints
every 12 minutes to keep it awake and the cache warm.

> **Set up the warm workflow:** add a repository secret `NEWS_TOKEN` (Settings → Secrets and
> variables → Actions) matching the `NEWS_TOKEN` in Render / `index.html`. The workflow also
> has a manual "Run workflow" button in the Actions tab.

Example (Google Cloud Run):

```bash
gcloud run deploy news-desk --source . --region us-central1 --allow-unauthenticated \
  --set-env-vars NEWS_HOST=0.0.0.0,NEWS_ALLOWED_ORIGIN=https://will-smith12.github.io \
  --set-env-vars GEMINI_API_KEY=YOUR_KEY,NEWS_TOKEN=YOUR_TOKEN
# then set NEWS_API in index.html to the printed https://news-desk-xxxx.run.app URL
```


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
| Small Business Sentiment | line (dual axis) |

## Zooming &amp; date ranges

- **Quick ranges:** use the **1Y / 3Y / 5Y / 10Y / All** buttons above the chart to focus on recent years.
- **Drag to zoom:** click-drag horizontally across the chart to zoom into a date range.
- **Scroll to zoom:** mouse wheel zooms in/out on the x-axis.
- **Pan:** hold **Shift** and drag to move along the timeline.
- **Reset zoom** returns to the full history.

## Files

- `index.html` — the dashboard app (uses bundled `chart.umd.min.js`).
- `chart.umd.min.js` — Chart.js library (bundled so the app works offline).
- `chartjs-plugin-zoom.min.js`, `hammer.min.js` — zoom/pan support (bundled, offline).
- `data.js` — data embedded as JS so the page works when opened directly (file://).
- `data.json` — same data as JSON (used if served over HTTP).
- `generate_data.py` — re-extracts `data.js` + `data.json` from the Excel file. Re-run after updating the spreadsheet:
  ```bash
  python3 generate_data.py
  ```
- `start.command` — one-click launcher.
- `news_agents.py` — News Desk backend: three Claude web-search agents (macro / government / social).
- `start_news_agents.command` — launcher for the News Desk backend (needs `GEMINI_API_KEY`). For an
  always-on service instead, use the `com.willsmith.newsdesk` launchd agent (see above).

## Notes

- Tabs are limited to indicators with complete data for **both** countries. Two source
  series with no US history (GDP Growth Annualized, Households Debt to Income — subscriber-gated)
  are excluded automatically by `generate_data.py`.
- Gross Fixed Capital Formation uses different units per country (CAD Million vs USD Billion),
  so it is plotted on dual y-axes.
- Small Business Sentiment pairs Canada's **CFIB Business Barometer** (0–100 index, 50 = neutral)
  with the **US NFIB Small Business Optimism Index** (index, 1986 = 100). The two use different
  scales, so it is dual-axis: single-country views use each series' own axis and the US-Canada
  view normalizes both to index 100.
