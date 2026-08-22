"""
Central configuration for the macro_refresh tool.

Secrets/keys are read from environment variables, optionally loaded from a
`.env` file living next to this module. Only FRED requires a key; the Bank of
Canada Valet API and the Trading Economics website scrape need none.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# --- paths -----------------------------------------------------------------
PKG_DIR = Path(__file__).resolve().parent
DOWNLOADS = PKG_DIR.parent                       # ~/Downloads
LOG_DIR = PKG_DIR / "logs"
RAW_TE = DOWNLOADS / "raw_te"                     # cached TE country metadata

# The workbook everything is refreshed into.
MASTER = Path(os.environ.get(
    "MACRO_MASTER_PATH", str(DOWNLOADS / "master_economics_data.xlsx")))

# Make the sibling legacy scripts importable (fetch_economics, cfib_refresh, ...).
if str(DOWNLOADS) not in sys.path:
    sys.path.insert(0, str(DOWNLOADS))


# --- minimal .env loader (no external dependency) --------------------------
def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv(PKG_DIR / ".env")

# --- keys ------------------------------------------------------------------
# FRED requires a free API key: https://fredaccount.stlouisfed.org/apikeys
# Set it in the environment, in a .env file next to this module, or (in CI) as
# the FRED_API_KEY GitHub Actions secret. Never hard-code it here -- this file
# is public.
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

# --- Trading Economics scrape tuning --------------------------------------
TE_BASE = "https://tradingeconomics.com"
# CloudFront host that serves the (encrypted) Highcharts series payloads.
TE_CHART_HOST = "d3ii0wo49og5mi.cloudfront.net"
# Rewrite the chart request's `n` (point count) up to this so the page decrypts
# full history instead of the default ~12-point window.
TE_MAX_POINTS = 6000
TE_CONCURRENCY = int(os.environ.get("MACRO_TE_CONCURRENCY", "4"))
TE_PAGE_TIMEOUT_MS = 45_000
TE_NAV_RETRIES = 2

# --- Scrape robustness knobs (all env-overridable) --------------------------- #
# Chart-render poll rounds (1s each) on the main pass before giving up an attempt.
TE_POLL_ROUNDS = int(os.environ.get("MACRO_TE_POLL_ROUNDS", "20"))
# Exponential backoff between retry attempts: min(MAX, BASE * 2**(attempt-1)) * jitter.
TE_RETRY_BASE_DELAY = float(os.environ.get("MACRO_TE_RETRY_BASE_DELAY", "2.0"))
TE_RETRY_MAX_DELAY = float(os.environ.get("MACRO_TE_RETRY_MAX_DELAY", "20.0"))
# Small random pre-navigation delay per worker on the high-concurrency main pass
# (de-syncs simultaneous heavy page loads). 0 disables.
TE_WORKER_STAGGER = float(os.environ.get("MACRO_TE_WORKER_STAGGER", "0.75"))
# Final retry sweep of indicators that the main pass missed: lower concurrency,
# more attempts, longer poll budget — far more likely to render once load is low.
TE_SWEEP_CONCURRENCY = int(os.environ.get("MACRO_TE_SWEEP_CONCURRENCY", "1"))
TE_SWEEP_RETRIES = int(os.environ.get("MACRO_TE_SWEEP_RETRIES", "4"))
TE_SWEEP_POLL_ROUNDS = int(os.environ.get("MACRO_TE_SWEEP_POLL_ROUNDS", "35"))

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

LOG_DIR.mkdir(exist_ok=True)
