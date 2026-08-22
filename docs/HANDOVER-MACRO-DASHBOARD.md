# US & Canada Macro Dashboard — Handover Brief

**Live site:** https://will-smith12.github.io/us-canada-macro-dashboard/
**Repository:** https://github.com/will-smith12/us-canada-macro-dashboard (public)
**Incoming owner:** Matthew Barrow (`MattBarrow70`)
**Outgoing:** Will Smith — this brief exists because Will is offboarding.
**Written:** 22 Aug 2026

---

## 1. Read this part if you read nothing else

The dashboard now **updates itself in the cloud.** It runs every Monday on GitHub's
servers, not on anyone's laptop. You do not have to do anything to keep it alive, and
it will not stop when Will's Mac is handed back.

That was **not** true a week ago. Until now the refresh ran on a scheduled job on Will's
MacBook, driving code that only existed in his `~/Downloads` folder and was in no
repository. When that machine went, the dashboard would have frozen on its last update
and the code that built it would have been gone. Everything below describes the fixed
setup.

**Three things are still on Will personally and need action from someone else — see
[§7 Open items](#7-open-items-need-someone-other-than-will).** The most important is
that the repository still sits on his *personal* GitHub account.

---

## 1a. Using this document with GitHub Copilot

You will most likely be working through Copilot rather than typing commands yourself.
This document is written to suit that: **every operational section gives you a prompt to
paste into Copilot, followed by the exact underlying command.**

Both are there deliberately. The prompt is what you will actually use. The command is the
ground truth — it is what the weekly cloud job runs, it has been verified to work, and it
is what Copilot should end up executing. If Copilot ever proposes something noticeably
different from the command shown, trust the document over the suggestion and say so.

**The single most useful thing you can do first** is open the repository folder in VS Code
(or point Copilot CLI at it) and ask:

> Read `docs/HANDOVER-MACRO-DASHBOARD.md` and `.github/workflows/refresh-dashboard.yml`,
> then explain in your own words how this dashboard updates itself and what I would need
> to do if the weekly job started failing.

That gives Copilot the full picture in one go, and its answer doubles as a check that you
have the whole repo and not a partial copy.

Two habits worth keeping:

- **Ask Copilot to explain before it changes anything.** "What does this do?" is safer
  than "fix this", especially with the scrape code.
- **Tell it what you have already tried.** Pasting the failing log line from the Actions
  tab into the prompt gets a far better answer than describing the symptom.

> ⚠️ One caution: this repo is public, but your **FRED API key is not**. Do not paste the
> key into a prompt, a file, or a commit. It belongs in an environment variable or a
> GitHub secret — see [§5](#5-getting-it-onto-your-machine).

---

## 2. What the dashboard is

A single-page website showing ten macroeconomic indicators for Canada and the United
States side by side — GDP, GDP growth, inflation, policy interest rate, unemployment,
labour productivity, household debt to GDP, gross fixed capital formation, GDP per
capita, and small-business sentiment.

It is a **static website**. There is no server, no database and no login. The site is
a handful of HTML/JavaScript files plus one data file, served free by GitHub Pages.
That is why it is cheap and hard to break: there is nothing running that can crash.

The repo also carries two sibling dashboards (`housing/`, `bos/` — the Bank of Canada
Business Outlook Survey). This brief is about the main macro dashboard; the others
follow the same publishing model.

---

## 3. How the data flows

Four stages, left to right:

```
  Public data sources          Excel workbook           Dashboard data          Live site
  ───────────────────          ──────────────           ──────────────          ─────────
  Trading Economics  ─┐
  FRED (US Fed)       ├──►  updating_master_    ──►    data.json    ──►    GitHub Pages
  Bank of Canada     ─┘      macro_variables.xlsx        data.js              (the website)
                                                                                    ▲
      [ refresh/macro_refresh ]   [ update_dashboard_data.py ]   [ git commit ]  ────┘
```

1. **Collect.** `refresh/macro_refresh` pulls from three public sources — the FRED API
   (US Federal Reserve), the Bank of Canada Valet API, and a browser-driven scrape of
   Trading Economics — and writes an Excel workbook.
2. **Extract.** `update_dashboard_data.py` reads the eight worksheets the dashboard
   actually uses and rewrites `data.json` and `data.js`.
3. **Publish.** Those two files are committed to the repository.
4. **Serve.** GitHub Pages notices the commit and republishes the site within a minute
   or two.

> **The key idea:** *committing the data file **is** the deployment.* There is no separate
> "deploy" or "upload" step. If the file is in the repo, it is on the website.

### One thing worth knowing

The workbook is rebuilt **completely from scratch on every run**, in about 75 seconds.
Nothing is carried over between runs. This was tested directly: starting from an empty
folder, the pipeline reproduced the published data with 9 of the 10 indicator series
coming out byte-for-byte identical (the tenth was a genuine new inflation reading).

Practically, that means **there is no state to protect** — no master file to back up, no
cache to keep warm, nothing that can slowly corrupt. If a run fails, the next run starts
clean. This is the single biggest reason the setup is now low-maintenance.

---

## 4. The automatic weekly update

Defined in `.github/workflows/refresh-dashboard.yml`.

| | |
|---|---|
| **When** | Every Monday, 14:00 UTC (07:00 Pacific) |
| **Where** | GitHub-hosted Linux runner — no laptop involved |
| **How long** | About 4½ minutes |
| **Cost** | Free (public repositories get unlimited GitHub Actions minutes) |
| **What it does** | Rebuild workbook → regenerate data → sanity-check → commit → Pages publishes |

### Watching it

Go to the repo → **Actions** tab → **Refresh dashboard data**. Green tick = ran fine.

Or ask Copilot:

> Show me the last few runs of the "Refresh dashboard data" workflow in this repo and
> whether they succeeded.

### Running it yourself, on demand

From the same screen: **Run workflow** → **Run workflow**. Or ask Copilot:

> Trigger the "Refresh dashboard data" workflow with `te_scope` set to `key`, then tell me
> when it finishes and whether it published anything.

There is one option, `te_scope`:

- **`key`** (default) — about 1 minute. Fetches the series the dashboard displays.
  This is the right choice essentially always.
- **`full`** — several hours. Fetches the entire Trading Economics catalogue into the
  workbook. Only useful if you are doing separate research off the workbook itself.
  Not needed to update the website.

<details>
<summary>The commands behind those prompts</summary>

```bash
gh run list --workflow=refresh-dashboard.yml --limit 5
gh workflow run refresh-dashboard.yml -f te_scope=key
```
</details>

### Knowing whether it is still alive

Every run writes `last_refresh.json` at the top of the repo:

```json
{
  "last_refresh_utc": "2026-08-22 00:24:50",
  "data_generated": "2026-08-17",
  "indicators": 10,
  "te_scope": "key",
  "run": "https://github.com/.../actions/runs/32540011908"
}
```

**If `last_refresh_utc` is more than about a week old, the automation has stopped.**
That is the one number to spot-check occasionally. It is written on every run — including
runs where no economic figure changed — precisely so that silence is meaningful.

Note `data_generated` can legitimately lag `last_refresh_utc`: it is the date the
*underlying figures* last moved, and in a quiet week nothing moves. Two different
questions, two different fields.

---

## 5. Getting it onto your machine

You only need this if you want to change the code, investigate a failure, or run a
refresh by hand. **Simply viewing the dashboard needs nothing but the URL.**

### One-time setup

You need **Git** and **Python 3.12+**. If you are not sure whether you have them, ask
Copilot:

> Do I have Git and Python 3.12 or newer installed? If not, tell me how to install them
> on this machine.

Then, to get the code and its dependencies:

> Clone `https://github.com/will-smith12/us-canada-macro-dashboard`, then install the
> Python dependencies from `refresh/requirements.txt` and install the Chromium browser
> that Playwright needs.

<details>
<summary>The commands behind that prompt</summary>

```bash
git clone https://github.com/will-smith12/us-canada-macro-dashboard.git
cd us-canada-macro-dashboard
python -m pip install -r refresh/requirements.txt
python -m playwright install chromium
```
</details>

The Playwright step is the one people miss. It downloads an actual browser, which the
Trading Economics scrape drives. Without it the refresh fails at the scrape step with a
"browser not found" style error.

### Get your own FRED API key

The US data comes from FRED, which requires a free key.

1. Sign up at https://fredaccount.stlouisfed.org/apikeys
2. Set it as an environment variable — ask Copilot:

> Set an environment variable called `FRED_API_KEY` on this machine so it persists in new
> terminal sessions. I will give you the value to use.

<details>
<summary>The commands behind that prompt</summary>

```bash
export FRED_API_KEY=your_key_here          # macOS / Linux (add to ~/.zshrc to persist)
setx FRED_API_KEY "your_key_here"          # Windows (then reopen the terminal)
```
</details>

> ⚠️ **Use your own key rather than reusing the existing one.** The key currently in the
> repository secret is registered to Will personally and should be treated as retired once
> he has left. See [§7](#7-open-items-need-someone-other-than-will).
>
> And as above — **do not paste the key itself into a Copilot prompt.** Set the variable
> yourself, or let Copilot write the command with a placeholder that you fill in.

### Run a refresh by hand

You should rarely need this, since the cloud job does it weekly. It is useful when the
cloud job is failing and you want an update now, or when you are testing a change.

> Run a manual dashboard refresh exactly as `docs/HANDOVER-MACRO-DASHBOARD.md` describes:
> rebuild the workbook to a scratch file, regenerate the dashboard data from it, then show
> me what changed before anything is committed.

Asking to **see the diff before committing** is the important part of that prompt — it
keeps you in control of what reaches the live site.

<details>
<summary>The commands behind that prompt</summary>

```bash
# Rebuild the workbook (~75 seconds). Run this from inside refresh/ --
# this is the exact command the weekly cloud job runs.
cd refresh
python -m macro_refresh.refresh --only fredboc te --te-scope key \
       --no-backup --target /tmp/macro.xlsx
cd ..

# Turn the workbook into dashboard data
python update_dashboard_data.py --workbook /tmp/macro.xlsx

# Publish
git add data.json data.js
git commit -m "Manual refresh"
git push
```
</details>

`--no-backup` matters: without it the tool tries to take a timestamped backup of the
*configured* master workbook, which is a path on Will's old machine and will not exist
on yours. `--target` writes to a scratch file instead, which is what the cloud job does.

The site updates a minute or two after the push.

### Just look at the site locally

Open `index.html` in a browser (or double-click `open.command` on a Mac). No server
needed.

---

## 6. When something goes wrong

The site is static, so **a failed refresh does not take the dashboard down.** It keeps
serving the last good data. That buys you time — failures are never an emergency.

| Symptom | Likely cause | What to do |
|---|---|---|
| Actions run fails at **"Rebuild the macro workbook"** | Trading Economics changed their page layout, or is rate-limiting | Re-run it once — transient blocks are common. If it fails repeatedly, the scrape selectors in `refresh/macro_refresh/te_scrape.py` need updating |
| Fails with a **FRED / 400 / API key** error | Key missing, expired, or revoked | Repo → Settings → Secrets and variables → Actions → update `FRED_API_KEY` |
| Fails at **"Sanity-check the generated data"** | An upstream source changed shape and series came back empty | This is the check doing its job — it deliberately refuses to publish empty data over good data. Inspect the log to see which indicator broke |
| Runs green, but the site looks stale | Usually correct — nothing changed that week | Check `data_generated` in `last_refresh.json`. Also try a hard refresh (Ctrl/Cmd+Shift+R) to defeat browser caching |
| Nothing has run for weeks | GitHub disables scheduled workflows in repos with ~60 days of no activity | Go to Actions and re-enable, or push any commit |

### Diagnosing with Copilot

The fastest route with any Actions failure is to get the log in front of Copilot rather
than describing the symptom:

> The "Refresh dashboard data" workflow failed. Fetch the log for the most recent run,
> find the step that failed and the actual error, and explain what it means in plain terms
> before suggesting a fix.

If you have the GitHub CLI available, Copilot can pull the log directly:

<details>
<summary>The commands behind that prompt</summary>

```bash
# List recent runs and their outcomes
gh run list --workflow=refresh-dashboard.yml --limit 5

# Full log for the most recent run
gh run view --log $(gh run list --workflow=refresh-dashboard.yml \
                    --limit 1 --json databaseId -q '.[0].databaseId')

# Re-run the most recent failed run
gh run rerun $(gh run list --workflow=refresh-dashboard.yml \
               --limit 1 --json databaseId -q '.[0].databaseId')
```
</details>

Two prompts worth keeping for the two most likely failures:

**The scrape has broken** (fails at "Rebuild the macro workbook", repeatedly):

> `refresh/macro_refresh/te_scrape.py` scrapes Trading Economics and it has started
> failing. Read the file, explain how it locates the data on the page, and work out
> whether the page structure has changed. Do not change anything yet — just tell me what
> you find.

**The site looks stale but the job is green:**

> Compare `last_refresh_utc` and `data_generated` in `last_refresh.json` against today's
> date, and tell me whether this dashboard is genuinely stale or just unchanged because no
> figures moved.

A caution on the scrape specifically: it is the most delicate part of this system, and it
is code Copilot cannot verify without running it. Have it explain and propose, then run a
manual refresh (§5) to confirm a fix actually works before pushing anything.

**Fallback:** if the cloud job is broken and you need an update now, run the manual steps
in §5 from your own machine. The two paths are the same code.

---

## 7. Open items — need someone other than Will

These could not be closed from Will's account and need action.

### 7.1 Land the copy that is already inside Data.Science — *most important*

The repository still lives on **Will's personal GitHub account**. Ownership sitting with a
departing employee is not where a team asset belongs, and when that account is deleted, so
is this repo.

**This is already most of the way solved.** The whole dashboard has been imported into the
company repository at
**`judi-ai/Data.Science` → `ResearchAndAnalytics/MacroDashboard/`**, awaiting review in
**[PR #113](https://github.com/judi-ai/Data.Science/pull/113)**. The import used
`git subtree`, so the dashboard's full 22-commit history came with it and will survive the
personal account being deleted.

That PR also adds a workflow which does the weekly refresh *and* can publish the dashboard
as a Pages site from inside Data.Science. It is committed **dormant** — merging it starts
nothing until an admin opts in.

**What still needs a repo admin on Data.Science:**

| Action | Where | Effect |
|---|---|---|
| Merge PR #113 | — | Code is org-owned; history preserved |
| Add secret `FRED_API_KEY` | Settings → Secrets and variables → Actions | The weekly refresh can run |
| Set variable `PUBLISH_MACRO_DASHBOARD` = `true` | same screen | Turns on the publish step |
| Settings → Pages → Source: **GitHub Actions** | Settings → Pages | Serves the site from the subfolder |

Because Data.Science is private and the org is on Enterprise, that Pages site can be
restricted to people with repo access, rather than being fully public as it is today —
usually the better default for an internal dashboard.

Until all that happens, the existing public site keeps serving, so **there is no gap**.
Once it is running from Data.Science, the personal repo can be archived and any Confluence
or bookmark links repointed.

> An earlier version of this document said transferring the repo was blocked because
> `judi-ai` disallows members creating repositories. That is still true of *creating a new
> repo*, but it turned out not to matter: the dashboard could simply be added as a folder
> inside the existing Data.Science repo, and a Pages site can be published from a nested
> folder using an Actions workflow. Both of those were things this document previously got
> wrong.

### 7.2 Replace the FRED API key

The `FRED_API_KEY` secret in the repository is Will's personal free key. It was set so the
dashboard keeps working through the transition. Replace it with your own (§5) and consider
Will's revoked.

The key used to be **hard-coded in the source**. It has been removed and now comes from an
environment variable / repository secret. It was never committed to this repository's
history.

### 7.3 Matt's permission level is *write*, not *admin*

You can clone, push, run and monitor workflows — everything needed day to day. You
**cannot** manage repository secrets, Pages settings or collaborators, because those need
admin, and the escalation was refused by the available credentials. If you need to change
the FRED key before the transfer in §7.1 happens, you will need Will (while he still has
an account) or the org admin doing the transfer to grant admin.

### 7.4 The Excel workbook is not stored anywhere

By design — see §3, it is rebuilt from scratch each run. Mentioned only so nobody goes
hunting for a master copy to preserve. There isn't one, and there doesn't need to be.

### 7.5 The news panel is already broken, and depends on Will's Render account

The Macro Indicators tab has a news panel that calls `news-desk.onrender.com` — a small
service hosted on **Will's personal Render account**, separate from GitHub entirely.

As of 22 Aug 2026 that service returns **404 on every endpoint**, so the panel is not
working today. This is pre-existing and unrelated to the move to GitHub Actions.

The good news is that the backend's source is in the repository (`news_agents.py`,
`Dockerfile`, `render.yaml`), so it can be redeployed to any container host by whoever
wants it. Decide whether the feature is worth keeping; if not, the panel should be removed
from `macro.html` so the dashboard stops calling a dead endpoint.

The token visible in `macro.html` next to that call is **not a credential** — the code
comments explain it is a throwaway string that pairs with the backend's CORS lock and rate
limit. It does not need rotating.

---

## 8. What was verified, and what wasn't

In the interest of not overstating this:

**Confirmed working, by running it:**

- The full pipeline executes on GitHub's servers end to end — 4m16s, all steps green.
- Trading Economics **does** serve GitHub's datacentre IP addresses. This was the main
  open risk (cloud IPs are blocked more often than home ones) and it is now settled by
  observation, not assumption.
- The cloud run independently reproduced the published data: all 10 indicators, current
  values, matching what the laptop had produced.
- The bot can commit and push to `main` (commit `be70546`).
- GitHub Pages picked that commit up and the live site serves it.
- The sanity check passes on good data and correctly fails on deliberately broken data.

**Not verified:**

- **A refresh where the numbers actually change.** Every test run happened in a week when
  no series moved, so the "data changed → commit updated data" branch has not been
  exercised in the cloud. The logic is a two-line diff check that ran correctly for
  months in the previous local script, so the risk is low — but it is not proven, and the
  first real change will be the proof. Watch the first Monday run.
- **Long-run scrape stability.** Trading Economics is a scrape, not a supported API. It
  can change without notice. This is the most likely source of future breakage, and it
  is inherent to the design rather than something introduced here.

---

## 9. Quick reference

| Thing | Where |
|---|---|
| Live dashboard | https://will-smith12.github.io/us-canada-macro-dashboard/ |
| Repository | https://github.com/will-smith12/us-canada-macro-dashboard |
| Run / monitor the refresh | Repo → Actions → "Refresh dashboard data", or ask Copilot (see below) |
| Is it still alive? | `last_refresh.json` in the repo root |
| The schedule and steps | `.github/workflows/refresh-dashboard.yml` |
| Data collection code | `refresh/macro_refresh/` |
| Workbook → website step | `update_dashboard_data.py` |
| Beginner walkthrough | `docs/REPRODUCTION-GUIDE.md` (563 lines, Windows + macOS) |
| Manual/local refresh script | `weekly_refresh_and_dashboard.sh` |

> `docs/REPRODUCTION-GUIDE.md` predates this change and describes the **manual** process
> in much more detail, assuming no GitHub experience. It is still accurate for running
> things by hand — just note that the automation it describes at the end (the launchd
> agent on a Mac) has been replaced by the GitHub Actions workflow described here.

### The five prompts worth keeping

Paste these into Copilot with the repo open.

| Situation | Prompt |
|---|---|
| **Getting oriented** | *Read `docs/HANDOVER-MACRO-DASHBOARD.md` and `.github/workflows/refresh-dashboard.yml`, then explain how this dashboard updates itself and what I'd do if the weekly job started failing.* |
| **Is it healthy?** | *Show me the last few runs of the "Refresh dashboard data" workflow, and compare `last_refresh_utc` in `last_refresh.json` to today's date. Is this dashboard current?* |
| **Update it now** | *Trigger the "Refresh dashboard data" workflow with `te_scope` set to `key`, then tell me when it finishes and whether it published anything.* |
| **It failed** | *The "Refresh dashboard data" workflow failed. Fetch the log for the most recent run, find the step that failed and the actual error, and explain what it means before suggesting a fix.* |
| **Refresh by hand** | *Run a manual dashboard refresh exactly as `docs/HANDOVER-MACRO-DASHBOARD.md` describes: rebuild the workbook to a scratch file, regenerate the dashboard data, then show me what changed before anything is committed.* |

---

*The scheduled job on Will's MacBook (`com.willsmith.macrorefresh`) was unloaded and its
configuration renamed to `...plist.RETIRED-20260822` on 22 Aug 2026, so it cannot start
again and publish alongside the cloud job. It was renamed rather than deleted, so it can
be restored if ever needed.*
