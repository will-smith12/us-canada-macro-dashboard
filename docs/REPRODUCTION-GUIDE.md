# How to Reproduce & Update the Macro Dashboard — A Complete Beginner's Guide

**Audience:** someone who has **never used GitHub** and wants to run, rebuild, and re-publish
the *US & Canada Macro Dashboard* from scratch. No prior programming knowledge is assumed — every
term is explained the first time it appears.

**What you'll be able to do by the end:**
1. Understand what the dashboard is and how its data flows, end to end.
2. Install the few free tools you need (on **Windows or Mac**).
3. Refresh the underlying economic data (the "Excel workbook").
4. Turn that workbook into the dashboard's data files.
5. **Publish** the update so the live website changes.
6. View the result — online or on your own computer.

> **The single most important idea:** you do **not** need to understand the code. You just run
> **four steps in order** (A → B → C → D). This guide walks through each one with copy-paste commands.

The live dashboard lives here:
👉 **https://will-smith12.github.io/us-canada-macro-dashboard/**

---

## Table of contents
- [Part 0 — The big picture](#part-0--the-big-picture)
- [Part 1 — Concepts & one-time setup](#part-1--concepts--one-time-setup)
- [Part 2 — Get the code onto your computer](#part-2--get-the-code-onto-your-computer)
- [Part 3 — Stage A: auto-update the Excel workbook](#part-3--stage-a-auto-update-the-excel-workbook)
- [Part 4 — Stage B: turn the workbook into dashboard data](#part-4--stage-b-turn-the-workbook-into-dashboard-data)
- [Part 5 — Stage C: publish to the website (GitHub Pages)](#part-5--stage-c-publish-to-the-website-github-pages)
- [Part 6 — Stage D: view the dashboard](#part-6--stage-d-view-the-dashboard)
- [Part 7 — (Optional) Automate the whole thing](#part-7--optional-automate-the-whole-thing)
- [Part 8 — Troubleshooting & FAQ](#part-8--troubleshooting--faq)
- [Part 9 — Glossary](#part-9--glossary)
- [Appendix A — Handover checklist (what you must be given)](#appendix-a--handover-checklist-what-you-must-be-given)
- [Appendix B — File & path reference](#appendix-b--file--path-reference)

---

## Part 0 — The big picture

The dashboard is a **website made of plain files** (HTML + a data file). It has three tabs — Macro
Indicators (Canada vs US), Canadian Housing Prices, and the Bank of Canada Business Outlook. All the
numbers it shows are baked into one data file, so the site itself needs no database and no server.

Getting fresh numbers onto the live site is a **four-stage pipeline**:

```
 RAW ECONOMIC SOURCES                    STAGE A: the "macro_refresh" program
 ┌───────────────────────────┐          ┌───────────────────────────────────────────┐
 │ Trading Economics (website)│         │  Downloads the latest numbers and writes    │
 │ FRED  (US Federal Reserve) │ ───────► │  them all into ONE Excel file:              │
 │ Bank of Canada             │         │  "updating_master_macro_variables.xlsx"     │
 │ CFIB / Statistics Canada   │         └───────────────────────────────────────────┘
 └───────────────────────────┘                          │
                                                         ▼
                                   STAGE B: "update_dashboard_data.py"
                                   Reads the Excel file and writes two small data files:
                                        data.js   and   data.json
                                                         │
                                                         ▼
                                   STAGE C: "publish" (push to GitHub)
                                   Send data.js + data.json to GitHub. GitHub Pages
                                   automatically re-publishes the website.
                                                         │
                                                         ▼
                                   STAGE D: "view"
                                   Open https://will-smith12.github.io/us-canada-macro-dashboard/
```

**In one sentence:** *Stage A* makes a fresh Excel file → *Stage B* turns it into the dashboard's
data → *Stage C* uploads it to GitHub → *Stage D* is just opening the web page.

> ⏱️ **Time & effort per stage.** Stage A is the heavy one — it visits many web pages and can take
> a while (tens of minutes). Stages B and C take seconds. Stage D is instant.

A few honest heads-ups before you start (explained in detail later):
- The **Stage A program is not inside the website's GitHub project** — it's a separate folder of
  scripts that must be given to you as a bundle (see [Appendix A](#appendix-a--handover-checklist-what-you-must-be-given)).
- Stage A **collects data from a live third-party website (Trading Economics)**, so it can
  occasionally be flaky; the program has built-in retries to cope.
- Everything was originally built on a **Mac**. It also runs on **Windows**; wherever the steps
  differ, this guide shows both.

---

## Part 1 — Concepts & one-time setup

You only do Part 1 **once** per computer.

### 1.1 A 60-second vocabulary
- **GitHub** — a website that stores projects (folders of files) and can also *host* simple
  websites for free.
- **Repository ("repo")** — one project/folder on GitHub. Ours is called
  `us-canada-macro-dashboard`.
- **GitHub Pages** — the free GitHub feature that turns a repo into a public website. That's why the
  dashboard has a `github.io` web address.
- **Clone** — make a copy of a GitHub repo on your own computer so you can work with the files.
- **Commit** — save a snapshot of your changes, with a short note describing them.
- **Push** — upload your committed changes back to GitHub. *Pushing the data files is what makes the
  live website update.*
- **Python** — the programming language the data scripts are written in. You just need it
  *installed*; you won't write any Python.
- **Terminal (Mac) / PowerShell (Windows)** — a text window where you type commands. Don't worry,
  you'll copy-paste them.

### 1.2 Create a free GitHub account
1. Go to **https://github.com** and click **Sign up**.
2. To publish updates you need permission to the repo. Ask the dashboard's owner (@will-smith12) to
   **add your GitHub username as a collaborator** (repo → *Settings → Collaborators → Add people*).
   You'll get an email invitation — accept it.

### 1.3 Install GitHub Desktop (the easy, no-typing way to use GitHub)
GitHub Desktop is a friendly app with buttons instead of commands. **We recommend it** over the
command line for Stage C.
1. Download from **https://desktop.github.com**.
2. Install and open it, then **File → Options → Accounts → Sign in** with your GitHub account.

### 1.4 Install Python 3
You need Python **3.10 or newer**.

**Windows**
1. Go to **https://www.python.org/downloads/** → **Download Python 3.x**.
2. Run the installer and — **very important** — tick **“Add python.exe to PATH”** on the first
   screen, then click *Install Now*.
3. Verify: open **PowerShell** (Start menu → type *PowerShell*) and run:
   ```powershell
   py --version
   ```
   You should see something like `Python 3.12.x`.

**Mac**
1. Easiest: download the installer from **https://www.python.org/downloads/** and run it.
2. Verify: open **Terminal** (Spotlight → type *Terminal*) and run:
   ```bash
   python3 --version
   ```
   You should see something like `Python 3.12.x`.

### 1.5 (Recommended) Get your own free FRED API key
One of the data sources (FRED, the US Federal Reserve's database) asks for a free **API key** (think
of it as a password that lets a program download data).
1. Create a free account at **https://fred.stlouisfed.org/**.
2. Go to **My Account → API Keys → Request API Key**. Copy the long string it gives you.
3. Keep it somewhere safe for [Part 3](#part-3--stage-a-auto-update-the-excel-workbook).

> The Stage A program ships with a shared fallback key so it *works out of the box*, but that key is
> rate-limited and shared. Using your own is more reliable. **Never paste an API key into a file you
> push to GitHub** (more on this in [Part 8](#part-8--troubleshooting--faq)).

---

## Part 2 — Get the code onto your computer

You need **two** things on your machine:
1. **The dashboard repo** (the website + Stage B script + the publish step).
2. **The Stage A bundle** (`macro_refresh` + a few helper scripts) — handed to you separately,
   because it is *not* stored inside the dashboard repo. See
   [Appendix A](#appendix-a--handover-checklist-what-you-must-be-given).

### 2.1 Clone the dashboard repo (with GitHub Desktop)
1. In GitHub Desktop: **File → Clone repository…**
2. Pick `will-smith12/us-canada-macro-dashboard` from the list (or paste the URL
   `https://github.com/will-smith12/us-canada-macro-dashboard.git`).
3. Choose where to save it (the default is fine) and click **Clone**.

You now have a folder called `us-canada-macro-dashboard` on your computer. Note its location — GitHub
Desktop shows it under **Repository → Show in Finder/Explorer**. Typical paths:
- **Mac:** `/Users/<you>/us-canada-macro-dashboard` (or `~/Documents/GitHub/us-canada-macro-dashboard`)
- **Windows:** `C:\Users\<you>\Documents\GitHub\us-canada-macro-dashboard`

### 2.2 Put the Stage A bundle in place
The Stage A program expects to live in your **Downloads** folder, alongside a handful of helper
scripts it reuses. Unzip the bundle you were given so the layout looks like this:

```
Downloads/
├── macro_refresh/                ← the Stage A program (a folder)
│   ├── refresh.py
│   ├── config.py
│   ├── te_scrape.py
│   ├── te_backfill.py
│   ├── fred_boc.py
│   ├── cfib.py
│   ├── potential_gdp.py
│   ├── requirements.txt
│   └── .env.example
├── raw_te/                       ← cached data the scraper needs
├── fetch_fred_boc.py             ← helper scripts macro_refresh reuses
├── cfib_to_master.py
├── cfib_refresh.py
├── add_potential_gdp.py
└── fetch_economics.py
```

> **Why Downloads?** The scripts refer to this folder by name. You *can* use a different folder, but
> then you must adjust paths (see [Appendix B](#appendix-b--file--path-reference)). For a first run,
> using **Downloads** is by far the simplest.

---

## Part 3 — Stage A: auto-update the Excel workbook

**Goal:** produce a fresh master Excel file of economic data.
**Program:** the `macro_refresh` package.
**Output:** `Downloads/updating_master_macro_variables.xlsx`.

### 3.1 Install Stage A's Python tools (once)
It's tidy to install everything into a private **virtual environment** (an isolated Python
workspace, so these tools don't clash with anything else on your machine).

**Mac (Terminal):**
```bash
cd ~/Downloads
python3 -m venv ~/venv-macro                 # make the isolated workspace (once)
source ~/venv-macro/bin/activate             # switch into it (each new Terminal)
pip install -r macro_refresh/requirements.txt
python -m playwright install chromium        # installs the headless browser (see note)
```

**Windows (PowerShell):**
```powershell
cd $env:USERPROFILE\Downloads
py -m venv $env:USERPROFILE\venv-macro        # make the isolated workspace (once)
$env:USERPROFILE\venv-macro\Scripts\Activate.ps1   # switch into it (each new PowerShell)
pip install -r macro_refresh\requirements.txt
python -m playwright install chromium         # installs the headless browser (see note)
```

> **What is “playwright / headless Chromium”?** One data source (Trading Economics) only shows its
> full history to a real web browser. The program drives an invisible ("headless") copy of Chrome to
> read those numbers. `playwright install chromium` downloads that browser once (a few hundred MB).

> **You'll know the environment is active** when your command prompt shows `(venv-macro)` at the
> start of the line. Re-activate it (the `activate` line above) every time you open a new terminal.

### 3.2 Set your FRED key (optional but recommended)
Copy the example settings file and put your key in it:

**Mac:**
```bash
cp ~/Downloads/macro_refresh/.env.example ~/Downloads/macro_refresh/.env
open -e ~/Downloads/macro_refresh/.env       # opens it in TextEdit
```
**Windows:**
```powershell
Copy-Item $env:USERPROFILE\Downloads\macro_refresh\.env.example $env:USERPROFILE\Downloads\macro_refresh\.env
notepad $env:USERPROFILE\Downloads\macro_refresh\.env
```
In the file, remove the `#` in front of this line and paste your key:
```
FRED_API_KEY=your_fred_api_key_here
```
Save and close. (Skip this whole step to just use the built-in fallback key.)

### 3.3 Run the refresh
Make sure your environment is active (you see `(venv-macro)`), then from the **Downloads** folder:

**Mac:**
```bash
cd ~/Downloads
python -m macro_refresh.refresh --target ~/Downloads/updating_master_macro_variables.xlsx
```
**Windows:**
```powershell
cd $env:USERPROFILE\Downloads
python -m macro_refresh.refresh --target $env:USERPROFILE\Downloads\updating_master_macro_variables.xlsx
```

This runs four mini-pipelines **in order**: `te` (Trading Economics) → `fredboc` (FRED + Bank of
Canada) → `cfib` (CFIB business barometer) → `potgdp` (potential GDP / output gap). It prints a
running log and finishes with a `=== summary ===` showing `ok` or `FAILED` for each.

> ⚠️ **Run it from the `Downloads` folder** exactly as shown. The program needs to sit next to its
> helper scripts to find them.

**Handy variations** (optional):
| Command (add after `python -m macro_refresh.refresh`) | What it does |
|---|---|
| *(nothing)* | Full refresh — all four sources, full history. Slowest, most complete. |
| `--te-scope key` | Faster: only the headline Trading Economics indicators. |
| `--only fredboc` | Run just one source (e.g. re-pull FRED/BoC), leaving the rest as they were. |
| `--skip te` | Refresh everything *except* the slow Trading Economics scrape. |
| `--no-backfill` | Don't substitute official data for gaps in the Trading Economics scrape. |
| `--no-backup` | Don't make the automatic pre-run backup copy. |

### 3.4 What you should see afterwards
- A fresh **`updating_master_macro_variables.xlsx`** in your Downloads folder (check the *Date
  modified* is now).
- A **timestamped backup** of the previous version alongside it (e.g.
  `...BACKUP-2026-07-26-101500.xlsx`) — safe to keep or delete.
- A **log file** under `Downloads/macro_refresh/logs/refresh-YYYYMMDD-HHMMSS.log` if you ever need to
  see what happened.

> 🧯 **If it says the file is “open in Excel”:** close the workbook in Excel and run again — the
> program refuses to overwrite a file that Excel has locked.

> 🔁 **Occasional missing indicators:** because Trading Economics is scraped live, a few series can
> come back empty under load. The program automatically retries and back-fills from official sources.
> If the summary still lists a few failures, simply run Stage A again later.

---

## Part 4 — Stage B: turn the workbook into dashboard data

**Goal:** convert the Excel workbook into the two files the website actually reads.
**Program:** `update_dashboard_data.py` (inside the dashboard repo).
**Output:** `data.json` and `data.js` (both in the dashboard repo folder).

Stage B needs just one Python tool (`openpyxl`, which reads Excel files). If you're still in the
`(venv-macro)` environment from Stage A you already have it; otherwise install it:
```bash
pip install openpyxl
```

Run it **from inside the dashboard repo folder**:

**Mac:**
```bash
cd ~/us-canada-macro-dashboard          # adjust to wherever GitHub Desktop cloned it
python update_dashboard_data.py
```
**Windows:**
```powershell
cd $env:USERPROFILE\Documents\GitHub\us-canada-macro-dashboard   # adjust to your clone location
python update_dashboard_data.py
```

By default it reads `Downloads/updating_master_macro_variables.xlsx` (the file Stage A just made). It
only rewrites `data.js`/`data.json` **if the numbers actually changed** — a safety feature.

**Useful options:**
| Option | What it does |
|---|---|
| `--force` | Rewrite the data files even if nothing changed (handy for a first run). |
| `--dry-run` | Show what *would* change, writing a preview to a temp folder instead of the real files. |
| `--workbook <path>` | Read a different Excel file than the default. |

### What you should see
```
Wrote .../data.json + .../data.js (10 indicators).
```
In GitHub Desktop, the left-hand **Changes** list will now show **`data.js`** and **`data.json`** as
modified. That's exactly what you want — those are the files you'll publish next.

---

## Part 5 — Stage C: publish to the website (GitHub Pages)

**Goal:** upload the two updated data files so the live site refreshes.
**Tool:** GitHub Desktop (easiest).

1. Open **GitHub Desktop**. It should show `us-canada-macro-dashboard` as the current repository and
   list `data.js` + `data.json` under **Changes**.
2. At the bottom-left, type a short **Summary**, e.g. `Refresh dashboard data (July 2026)`.
3. Click **Commit to main**. *(This saves a snapshot on your computer.)*
4. Click **Push origin** (top bar). *(This uploads it to GitHub.)*
5. Wait ~1–2 minutes. GitHub Pages rebuilds automatically, then the live site shows the new numbers:
   **https://will-smith12.github.io/us-canada-macro-dashboard/**

> 💡 **You only ever need to publish `data.js` and `data.json`** for a data refresh — the rest of the
> site rarely changes.

### First-time only: make sure GitHub Pages is switched on
If the repo has never been published before:
1. On github.com, open the repo → **Settings → Pages**.
2. Under **Build and deployment → Source**, choose **Deploy from a branch**.
3. Set **Branch** to **`main`** and folder to **`/ (root)`**, then **Save**.
4. After a minute, the same page shows *“Your site is live at …”* with the public address.

> 🖥️ **Command-line alternative to Steps 1–4** (only if you prefer typing to GitHub Desktop):
> ```bash
> cd <the dashboard repo folder>
> git add data.js data.json
> git commit -m "Refresh dashboard data"
> git push origin main
> ```

---

## Part 6 — Stage D: view the dashboard

**Online (what everyone else sees):** just open
**https://will-smith12.github.io/us-canada-macro-dashboard/** in any browser.

**On your own computer (no internet needed):** open the repo folder and **double-click
`index.html`** — it opens in your browser and works entirely offline (the data is bundled in
`data.js`).
- **Mac shortcut:** double-click **`open.command`** (does the same thing).
- **Prefer a local web address?** Double-click **`start.command`** (Mac), or run
  `python -m http.server 8077` inside the repo folder (Mac or Windows) and open
  `http://localhost:8077`.

**Switch tabs** with the buttons in the header, the number keys **1 / 2 / 3**, or by adding
`#macro`, `#housing`, or `#bos` to the address.

---

## Part 7 — (Optional) Automate the whole thing

Everything above is manual, which is perfect for occasional updates. The original Mac also runs it
**automatically once a week** so the site stays current without anyone doing anything. This part is
optional and more advanced.

### 7.1 The one-command chain
The repo includes `weekly_refresh_and_dashboard.sh` (Mac shell script) that runs **Stage A → B → C**
back-to-back: refresh the workbook, regenerate `data.js`/`data.json`, then commit & push them to
GitHub — only pushing when the data actually changed.

### 7.2 Scheduling on a Mac (launchd)
macOS schedules background jobs with **launchd**. A ready-made scheduler file lives at
`Downloads/macro_refresh/com.willsmith.macrorefresh.plist`; it triggers the chain and re-checks
daily, effectively running a full refresh once a week (with catch-up if the Mac was asleep).
```bash
# install / start it
cp ~/Downloads/macro_refresh/com.willsmith.macrorefresh.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.willsmith.macrorefresh.plist

# check it's registered
launchctl list | grep macrorefresh

# run it right now (optional)
launchctl start com.willsmith.macrorefresh

# stop / uninstall
launchctl unload ~/Library/LaunchAgents/com.willsmith.macrorefresh.plist
```
> On a Mac, the background job also needs **Full Disk Access** so it can read your Downloads folder:
> *System Settings → Privacy & Security → Full Disk Access* → add your terminal app.

### 7.3 Scheduling on Windows (Task Scheduler)
Windows has no launchd; use the built-in **Task Scheduler** instead. Create a small batch file, e.g.
`refresh_all.bat`, that activates the environment and runs Stages A and B, then publishes:
```bat
call %USERPROFILE%\venv-macro\Scripts\activate.bat
cd /d %USERPROFILE%\Downloads
python -m macro_refresh.refresh --target %USERPROFILE%\Downloads\updating_master_macro_variables.xlsx
cd /d %USERPROFILE%\Documents\GitHub\us-canada-macro-dashboard
python update_dashboard_data.py
git add data.js data.json
git commit -m "Weekly auto-refresh dashboard data"
git push origin main
```
Then: **Task Scheduler → Create Basic Task → Weekly →** point the action at `refresh_all.bat`.
(For the `git push` to run unattended, sign in to GitHub once via GitHub Desktop or the
[GitHub CLI](https://cli.github.com) so your credentials are remembered.)

---

## Part 8 — Troubleshooting & FAQ

**The live site didn't change after I ran the scripts.**
You almost certainly did Stages A/B but not **Stage C**. Open GitHub Desktop and confirm you
**committed *and* pushed** `data.js` + `data.json`. The site only reflects what has been *pushed*.

**`python` or `pip` is “not recognized” / “command not found”.**
Python isn't on your PATH. **Windows:** re-run the Python installer and tick *“Add python.exe to
PATH.”* **Mac:** use `python3` and `pip3` instead of `python`/`pip`, or make sure your `venv-macro`
environment is active (you should see `(venv-macro)` in the prompt).

**Stage A says a pipeline `FAILED`.**
Each source is isolated, so one failure won't stop the others. Trading Economics is scraped live and
can be flaky under load — just run Stage A again later, or re-run only the failed source, e.g.
`python -m macro_refresh.refresh --only fredboc`.

**“ABORT: … appears open in Excel.”**
Close the workbook in Excel and run Stage A again.

**Stage B prints “data unchanged — nothing to write.”**
That's normal if the numbers didn't move. Force a rewrite with
`python update_dashboard_data.py --force`.

**Do I need the FRED key?**
No — a fallback key is built in. Your own free key (Part 1.5) is just more reliable.

**Is it safe to commit? Will I leak my key?**
Your key lives in `Downloads/macro_refresh/.env`, which is **outside** the dashboard repo, so GitHub
Desktop will never offer to upload it. **Rule of thumb:** only ever publish `data.js` and
`data.json`. Never paste keys into files inside the repo.

**What about the “News” button / News Desk?**
That's a separate optional live-news feature that needs its own backend and an AI key. It is **not**
part of reproducing the charts and can be ignored for this guide.

**Can I break the live site?**
The only files that matter for a data update are `data.js`/`data.json`, and GitHub keeps a full
history — any bad commit can be reverted in GitHub Desktop (**History → right-click → Revert**).

---

## Part 9 — Glossary
- **Repository (repo):** a project folder stored on GitHub.
- **Clone:** copy a repo from GitHub onto your computer.
- **Commit:** save a labelled snapshot of changes.
- **Push:** upload commits to GitHub (this is what updates the live site).
- **Branch / `main`:** a line of development; `main` is the primary one this site publishes from.
- **GitHub Pages:** free GitHub feature that serves a repo as a public website.
- **API key:** a personal token that lets a program download data from a service (e.g. FRED).
- **Virtual environment (venv):** an isolated set of Python tools for one project.
- **Headless browser:** an invisible web browser a program controls to read web pages.
- **launchd / Task Scheduler:** the Mac / Windows tools that run jobs on a schedule.
- **Workbook:** the master Excel file of economic data (`updating_master_macro_variables.xlsx`).

---

## Appendix A — Handover checklist (what you must be given)

Cloning the dashboard repo alone is **not enough** to run Stage A. Ask @will-smith12 to provide:

1. **Collaborator access** to `github.com/will-smith12/us-canada-macro-dashboard` (so you can push).
2. **The Stage A bundle** — a zip of the `macro_refresh` folder **plus** the helper scripts it uses.
   On the source Mac this is created with:
   ```bash
   cd ~/Downloads
   zip -r macro_refresh_bundle.zip \
       macro_refresh raw_te \
       fetch_fred_boc.py cfib_to_master.py cfib_refresh.py add_potential_gdp.py fetch_economics.py
   ```
   Unzip it into your **Downloads** folder (see [Part 2.2](#22-put-the-stage-a-bundle-in-place)).
3. *(Optional)* A recent copy of **`updating_master_macro_variables.xlsx`** to drop in your Downloads
   folder. This lets you try **Stage B → C** immediately, before you've run the slow Stage A.
4. *(Optional)* Your own **FRED API key** instructions (Part 1.5) — or confirmation that the built-in
   fallback key is fine for now.

> The workbook itself does **not** need to be shipped for the long term — Stage A regenerates it. It's
> only useful as a head-start.

---

## Appendix B — File & path reference

### Key files and what they do
| File / folder | Stage | Role |
|---|---|---|
| `Downloads/macro_refresh/` | A | The program that rebuilds the Excel workbook (run as `python -m macro_refresh.refresh`). |
| `Downloads/macro_refresh/config.py` | A | Settings: workbook path, FRED key, scrape tuning. |
| `Downloads/macro_refresh/.env` | A | *Your* FRED key (create from `.env.example`; keep private). |
| `Downloads/updating_master_macro_variables.xlsx` | A→B | The master Excel workbook (Stage A's output, Stage B's input). |
| `us-canada-macro-dashboard/update_dashboard_data.py` | B | Reads the workbook, writes `data.js` + `data.json`. |
| `us-canada-macro-dashboard/data.js` / `data.json` | B→C | The dashboard's data (the only files you publish). |
| `us-canada-macro-dashboard/index.html` | D | The website itself (open to view). |
| `us-canada-macro-dashboard/weekly_refresh_and_dashboard.sh` | A+B+C | Mac script that chains all three and pushes. |
| `Downloads/macro_refresh/com.willsmith.macrorefresh.plist` | — | Mac weekly scheduler. |

### Default locations (and how to change them)
- The scripts assume the **Downloads** folder. `update_dashboard_data.py` looks for
  `~/Downloads/updating_master_macro_variables.xlsx`; override with `--workbook <path>`.
- `macro_refresh`'s default output name is `master_economics_data.xlsx`; the live setup overrides it
  to `updating_master_macro_variables.xlsx` via `--target` (or the `MACRO_MASTER_PATH` environment
  variable). **Use the same name in Stage A's `--target` and Stage B's `--workbook`.**

### Moving to a different computer / folder
- `~` means your home folder — it expands automatically to `C:\Users\<you>` on Windows and
  `/Users/<you>` on Mac, so `~/Downloads` "just works" on both.
- The Mac-only conveniences (`.command` files, `launchd`, `open.command`, `start.command`) have no
  effect on Windows — use PowerShell commands / Task Scheduler instead, as shown in
  [Part 7](#part-7--optional-automate-the-whole-thing).
- If you place `macro_refresh` somewhere other than Downloads, keep the helper scripts (from
  Appendix A) **in the same parent folder** and run the command from that folder.

---

*Questions or something not matching what you see? The step that trips people up 95% of the time is
forgetting **Stage C (push)** — check GitHub Desktop first.*
