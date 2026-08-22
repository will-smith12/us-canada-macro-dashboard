# Verification Brief — US & Canada Macro Dashboard

**For:** a GitHub Copilot agent that can clone and read repositories, run shell commands and
Python, but **cannot** see the rendered dashboard, cannot reach the original author's laptop,
and has no API credentials.

**Your job:** determine, from the repository alone, whether each part of this dashboard can be
**reproduced from scratch by someone new**, and report precisely which links in each chain are
present and which are missing.

This is a handover audit. The author is offboarding; anything that exists only on his machine is
about to be lost. Your findings decide what must be rescued before that happens.

---

## 1. What the thing is

A static website — no server, no database, no login — showing macroeconomic data for **Canada vs
the United States**. It is published by GitHub Pages, which serves files straight from a repo.

Live today at: `https://will-smith12.github.io/us-canada-macro-dashboard/`

It has **three independent dashboards** behind one tabbed shell (`index.html`), each in its own
iframe:

| Tab | Entry point | Subject |
|---|---|---|
| **Macro Indicators** | `macro.html` | 10 indicators, Canada vs US |
| **Housing Prices** | `housing/index.html` | Canadian house-price indices (Teranet–NB, CREA MLS HPI, StatCan) |
| **Business Outlook** | `bos/index.html` | Bank of Canada Business Outlook Survey |

There is also `divergence.html` (rolling correlation / divergence view).

**Critical point: these three tabs have three completely separate data pipelines.** They share a
shell and nothing else. Verify each one independently. A common mistake would be to confirm the
Macro pipeline works and conclude the dashboard is reproducible — it is not the same question.

---

## 2. Where the code is

Two locations. **Check the second one on the right branch — the folder does not exist on `main`.**

1. **Origin (public, personal account — will be deleted):**
   `https://github.com/will-smith12/us-canada-macro-dashboard`, branch `main`.

2. **Org copy (private, the one that must survive):**
   `judi-ai/Data.Science`, branch **`DS-macro-dashboard`** (open as PR #113), at path
   **`ResearchAndAnalytics/MacroDashboard/`**.

   ```bash
   git clone https://github.com/judi-ai/Data.Science.git
   cd Data.Science
   git checkout DS-macro-dashboard
   cd ResearchAndAnalytics/MacroDashboard
   ```

The org copy was imported with `git subtree`, so it should carry the origin's **full 22-commit
history**. Verifying that is one of your tasks.

---

## 3. How the data flows

### 3.1 Macro tab (the one with automation)

```
Trading Economics (web scrape, needs a real browser)  ─┐
FRED  — US Federal Reserve API   (needs FRED_API_KEY)  ├─►  Excel workbook  ─►  data.json
Bank of Canada Valet API         (no key needed)       ─┘   (temp file)         data.js
                                                                                   │
                                          ┌────────────────────────────────────────┘
                                          ▼
                              git commit  ─►  GitHub Pages serves the site
```

- **Collector:** `refresh/macro_refresh/`, a Python package. Entry point
  `python -m macro_refresh.refresh`, **run from inside `refresh/`**.
  It has four pipelines selectable with `--only`: `te` (Trading Economics scrape),
  `fredboc` (FRED + Bank of Canada), `cfib`, `potgdp`.
  Relevant flags: `--te-scope {key,full}`, `--no-backup`, `--target <path>`.
- **Extractor:** `update_dashboard_data.py` at the folder root. Reads the workbook, writes
  `data.json` and `data.js` (same payload, two formats — `.js` is for opening the page via
  `file://`, `.json` for HTTP).
- **Publisher:** a commit. GitHub Pages redeploys on push. There is no separate deploy step.

**Non-obvious and worth confirming:** the 8 worksheets the dashboard actually reads all come from
the **`te` (scrape)** pipeline, *not* from `fredboc`. The `fredboc` sheets enrich the workbook for
other research. This means the scrape is load-bearing for the website.

Sheet → indicator mapping lives near the top of `update_dashboard_data.py` (look for a dict
mapping indicator names to `{"sheet": ..., "kind": "long"|"wide", ...}`). Sheets used: `GDP`,
`GDP Growth Rate`, `Inflation Rate`, `Interest Rate`, `Labour`, `Consumer`, `Unemployment Rate`,
`Business`.

`data.json` shape:
```
{ "generated": "YYYY-MM-DD",
  "source": ...,
  "indicators": [ { "name", "chartType", "dualAxis", "description",
                    "unit", "frequency", "dates", "canada", "us" }, ... ] }
```
Expect exactly **10** indicators.

**The pipeline is stateless** — it rebuilds the workbook from the source APIs every run in about
75 seconds and keeps nothing between runs. If you find code that depends on a pre-existing
workbook being present, that contradicts this and is worth reporting.

### 3.2 Housing tab

```
raw sources (Teranet JSON, CREA MLS HPI zip, StatCan 34100013, Alberta xlsx)
        │
        ▼  build_housing_indices.py          ← is this in the repo?
canada_housing_indices.xlsx                  ← is this in the repo?
        │
        ▼  housing/build_dashboard_data.py   ← this one IS in the repo
housing/data.json  +  housing/data.js
```

### 3.3 Business Outlook tab

```
Bank of Canada BOS source data
        │
        ▼  harvest.py / build_xlsx.py        ← are these in the repo?
BoC_BOS_sector_region.xlsx                   ← is this in the repo?
        │
        ▼  bos/build_bos_data.py             ← this one IS in the repo
bos/data.json  +  bos/data.js
```

For 3.2 and 3.3, read the **docstring and the input path constants at the top** of the in-repo
build scripts. They name their input file explicitly. Then check whether that input, and whatever
produces it, exist anywhere in the repository.

---

## 4. Automation

Two workflow files exist. Only one can run, and knowing why matters:

| File | Runs? |
|---|---|
| `ResearchAndAnalytics/MacroDashboard/.github/workflows/refresh-dashboard.yml` | **No.** GitHub only executes workflows found in `.github/workflows/` at a **repository root**. This one sits in a subfolder and is kept for reference. |
| `.github/workflows/macro-dashboard-refresh.yml` (Data.Science root) | Yes, once enabled. |

The root workflow is deliberately **dormant**: it needs a secret `FRED_API_KEY` to refresh, and a
variable `PUBLISH_MACRO_DASHBOARD=true` plus Pages source set to "GitHub Actions" to publish.
Confirm this gating is real by reading the `if:` condition on the deploy job and the guard in the
rebuild step — a claim of "safe by default" should be checked, not taken on trust.

Note it publishes a **staged subset** (excluding `refresh/`, `docs/`, `*.py`), not the whole
folder.

---

## 5. Your verification tasks

Work through these and report findings per item. Prefer running commands over reading alone.

### A. Repository integrity
1. Does `ResearchAndAnalytics/MacroDashboard/` exist on branch `DS-macro-dashboard`? (It should
   **not** exist on `main` — that is expected, the PR is unmerged.)
2. Did the subtree import preserve history? Check that the import commit has **two parents**
   (`git cat-file -p <import-sha> | grep ^parent`) and that the origin's earliest commit is an
   ancestor of the branch head. A single parent means history was squashed and the origin's
   record is *not* preserved.
3. Are there any credentials in the tree or in history? Search for long hex/base64-looking
   literals. **Expected:** a `NEWS_TOKEN` string in `macro.html` — read the comment beside it
   before flagging; it is documented as a deliberately public anti-abuse token, not a secret.

### B. Macro pipeline completeness — expect this one to PASS
4. Is the whole collector present? Expect `refresh/macro_refresh/` with ~12 modules including
   `refresh.py`, `config.py`, `te_scrape.py`, `fred_boc.py`, and five sibling legacy scripts in
   `refresh/` (`fetch_fred_boc.py`, `fetch_economics.py`, `cfib_refresh.py`, `cfib_to_master.py`,
   `add_potential_gdp.py`) which the package imports via a `sys.path` insertion — check
   `config.py` for how it resolves them, and confirm that resolution still works given where the
   package now sits.
5. Is `refresh/raw_te/` present with `country_US.json` and `country_CA.json`? The scrape reads
   these as scope definitions and **throws without them**.
6. Does `refresh/requirements.txt` exist and cover what the code imports (expect requests,
   openpyxl, pandas, playwright)?
7. Is the FRED key sourced from an environment variable rather than hard-coded? Confirm no key
   literal remains.
8. **Static-trace the chain**: does `update_dashboard_data.py` reference sheets that the `te`
   pipeline actually writes? Report any sheet the dashboard reads that nothing produces.

### C. Housing and BOS completeness — inspect carefully
9. For **both** `housing/build_dashboard_data.py` and `bos/build_bos_data.py`: identify the input
   file path constant. Is that file in the repository?
10. Is the *upstream* script that produces each input in the repository?
11. Conclude for each tab: could a new person regenerate this data with only the repo, or not? If
    not, state exactly which artefacts are missing and what they are called, so they can be
    hunted down on the author's machine before it is wiped.

### D. Documentation accuracy
12. `docs/HANDOVER-MACRO-DASHBOARD.md` is the handover document. Spot-check its **commands**
    against the workflow file — specifically the module invocation and its flags. Documentation
    that has drifted from the workflow is a real defect here, because it is what the next person
    will follow.
13. Does the README explain that this folder came from another repo and how it now runs?

### E. Runtime sanity (best effort)
14. `python -m pip install -r refresh/requirements.txt` and confirm
    `python -m macro_refresh.refresh --help` runs **from inside `refresh/`**. This proves imports
    and packaging resolve. You will **not** be able to complete a real refresh without a FRED key
    and a browser — do not treat that as a failure, just report how far you got.
15. `python -c "import json; d=json.load(open('data.json')); print(len(d['indicators']))"` — expect
    10, and confirm each indicator has a non-empty `dates` list.

---

## 6. Findings already suspected — confirm or refute, do not assume

State agreement or disagreement with each, **with evidence**. If you contradict one, say so
plainly; these are prior conclusions, not ground truth.

1. The **Macro** tab is fully reproducible from the repo.
2. The **Housing** tab is **not** — `housing/build_dashboard_data.py` reads
   `~/Downloads/canada_housing_indices.xlsx`, which is produced by
   `~/Downloads/housing_indices/build_housing_indices.py` (~496 lines). Neither the workbook nor
   its generator is in the repo.
3. The **BOS** tab is **not** — `bos/build_bos_data.py` reads
   `~/Downloads/BoC_BOS_sector_region.xlsx`, produced by scripts in `~/Downloads/bos_harvest/`.
   Neither is in the repo.
4. `generate_data.py` at the root reads `~/Desktop/US_Canada_Macro_Indicators.xlsx` and appears to
   be **superseded** by `update_dashboard_data.py`. Determine whether anything still calls it; if
   it is dead, say so.
5. The `cfib` pipeline fails non-fatally and is excluded from the workflow (`--only fredboc te`).
6. The news panel in `macro.html` calls `news-desk.onrender.com`, hosted on the author's personal
   Render account. It currently **404s**, so that feature is already broken. Its backend source
   (`news_agents.py`, `Dockerfile`, `render.yaml`) is in the repo, so it is redeployable.

---

## 7. What you cannot verify — say so rather than guessing

- **Whether the rendered site looks right.** You cannot see it. Verify structurally: that every
  local `src`/`href` in the HTML resolves to a file that exists.
- **Whether the Trading Economics scrape still works.** It needs a real browser and a live site,
  and TE can change layout or block datacentre IPs at any time. It succeeded from GitHub's
  runners on 22 Aug 2026; that is a data point, not a guarantee.
- **Whether FRED accepts a given key.** No credentials are available to you.
- **Anything on the author's machine.** If a file is not in the repo, you can only report it as
  missing — you cannot confirm it exists elsewhere.

---

## 8. How to report

For each of the three tabs, give a one-line verdict — **reproducible / not reproducible / partly**
— followed by the evidence. Then list, in priority order, the specific artefacts that must be
rescued from the author's machine before it is decommissioned, with exact filenames and paths.

Be concrete and be blunt about gaps. A confident "everything is fine" that misses a broken chain
is far more damaging here than a cautious finding, because there is a deadline after which the
missing pieces cannot be recovered at all.
