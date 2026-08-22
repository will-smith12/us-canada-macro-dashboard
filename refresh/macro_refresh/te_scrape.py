"""
Trading Economics — headless-scrape source (no API key).

Strategy
--------
TE serves each indicator's chart data from a CloudFront host as an *encrypted*
payload that the page decrypts client-side into a Highcharts series. The default
request only asks for ~12 points. We:

  1. Open the public indicator page in headless Chromium.
  2. Intercept the CloudFront chart request and rewrite its `n` (point count)
     parameter up to TE_MAX_POINTS, so the page decrypts the *full* history.
  3. Read the decrypted series straight out of Highcharts (xData/yData).

This avoids the paid TE API entirely and is resilient to DOM changes (we read
the chart's data model, not the HTML).

The scraped histories are then fed into the existing workbook builders in
`fetch_economics.py` (build_summary / build_category_sheet / build_indicator_sheet)
so the sheet layout/styling matches what the master already uses.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import random
import re
from typing import Optional

from openpyxl import Workbook
from playwright.async_api import async_playwright, Route

from . import config

# Reuse the proven scope logic, builders, styling and indicator lists.
import fetch_economics as fe  # noqa: E402  (path wired up in config)

COUNTRY_FILES = {"US": "country_US.json", "CA": "country_CA.json"}

# JS run in-page: return every Highcharts series with its decoded points.
_EXTRACT_JS = """() => {
    if (typeof Highcharts === 'undefined' || !Highcharts.charts) return [];
    const out = [];
    for (const c of Highcharts.charts) {
        if (!c || !c.series) continue;
        for (const s of c.series) {
            const xs = s.xData || [];
            const ys = s.yData || [];
            if (!xs.length) continue;
            out.push({name: s.name || '', xs: xs, ys: ys});
        }
    }
    return out;
}"""


def _epoch_to_date(ms: float) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


def _series_to_pairs(xs, ys) -> list[tuple[str, float]]:
    pairs = []
    for x, y in zip(xs, ys):
        if x is None or y is None:
            continue
        try:
            pairs.append((_epoch_to_date(float(x)), float(y)))
        except (TypeError, ValueError):
            continue
    pairs.sort(key=lambda p: p[0])
    return pairs


def load_scope(country: str):
    """Return (latest_rows, meta, names, url_map) for a country from cached TE metadata."""
    path = config.RAW_TE / COUNTRY_FILES[country]
    rows = json.loads(path.read_text())
    latest, meta, names = fe.build_scope(rows)
    url_map = {r["Category"]: r.get("URL") for r in latest if r.get("URL")}
    return latest, meta, names, url_map


async def _rewrite_n(route: Route) -> None:
    url = route.request.url
    if config.TE_CHART_HOST in url and "/economics/" in url:
        new = re.sub(r"([?&]n=)\d+", lambda m: f"{m.group(1)}{config.TE_MAX_POINTS}", url)
        if "n=" not in new:
            new += ("&" if "?" in new else "?") + f"n={config.TE_MAX_POINTS}"
        await route.continue_(url=new)
    else:
        await route.continue_()


async def _scrape_one(context, country: str, name: str, url_path: str,
                      log, *, attempts: int, poll_rounds: int
                      ) -> Optional[list[tuple[str, float]]]:
    full_url = config.TE_BASE + url_path
    for attempt in range(1, attempts + 1):
        page = await context.new_page()
        try:
            await page.route("**/*", _rewrite_n)
            try:
                await page.goto(full_url, wait_until="domcontentloaded",
                                timeout=config.TE_PAGE_TIMEOUT_MS)
            except Exception:
                pass  # heavy ad scripts may stall load; chart can still render

            # Poll until a non-trivial series is present (full history decoded).
            series = []
            for _ in range(poll_rounds):
                await asyncio.sleep(1)
                series = await page.evaluate(_EXTRACT_JS)
                if series and max((len(s["xs"]) for s in series), default=0) > 12:
                    break

            if not series:
                log(f"    [{country}] {name}: no chart data (attempt {attempt})")
            else:
                best = max(series, key=lambda s: len(s["xs"]))
                pairs = _series_to_pairs(best["xs"], best["ys"])
                if pairs:
                    return pairs
                log(f"    [{country}] {name}: empty after decode (attempt {attempt})")
        except Exception as e:
            log(f"    [{country}] {name}: error {e!r} (attempt {attempt})")
        finally:
            await page.close()

        # Exponential backoff + jitter before the next attempt (not after the last)
        # so transient throttling/slow-CDN conditions get time to clear instead of
        # being hit again immediately.
        if attempt < attempts:
            delay = min(config.TE_RETRY_MAX_DELAY,
                        config.TE_RETRY_BASE_DELAY * (2 ** (attempt - 1)))
            await asyncio.sleep(delay * (0.5 + random.random()))
    return None


async def _scrape_pass(context, country: str, names, url_map, log, *,
                       concurrency: int, attempts: int, poll_rounds: int,
                       stagger: float, label: str = "") -> dict:
    """One concurrent scrape pass over `names`; returns {name: pairs} for hits."""
    sem = asyncio.Semaphore(concurrency)
    hist: dict[str, list] = {}
    done = 0
    total = sum(1 for n in names if url_map.get(n))

    async def worker(name: str):
        nonlocal done
        url_path = url_map.get(name)
        if not url_path:
            return
        async with sem:
            # De-sync simultaneous heavy page loads on the high-concurrency pass.
            if stagger:
                await asyncio.sleep(random.random() * stagger)
            pairs = await _scrape_one(context, country, name, url_path, log,
                                      attempts=attempts, poll_rounds=poll_rounds)
        done += 1
        if pairs:
            hist[name] = pairs
        if done % 25 == 0 or done == total:
            log(f"  [{country}]{label} {done}/{total} scraped "
                f"({len(hist)} with data)")

    await asyncio.gather(*(worker(n) for n in names))
    return hist


async def _scrape_country(context, country: str, names, url_map, log) -> dict:
    # Main pass: high concurrency for throughput.
    hist = await _scrape_pass(
        context, country, names, url_map, log,
        concurrency=config.TE_CONCURRENCY,
        attempts=config.TE_NAV_RETRIES + 2,
        poll_rounds=config.TE_POLL_ROUNDS,
        stagger=config.TE_WORKER_STAGGER)

    # Retry sweep: re-scrape only the misses at low concurrency with more attempts
    # and a longer poll budget. Once the bulk is done, TE is far less likely to
    # throttle, so most transient empty-chart dropouts recover here.
    missing = [n for n in names if url_map.get(n) and n not in hist]
    if missing:
        log(f"  [{country}] retry sweep: {len(missing)} missing "
            f"@ concurrency {config.TE_SWEEP_CONCURRENCY}")
        swept = await _scrape_pass(
            context, country, missing, url_map, log,
            concurrency=config.TE_SWEEP_CONCURRENCY,
            attempts=config.TE_SWEEP_RETRIES,
            poll_rounds=config.TE_SWEEP_POLL_ROUNDS,
            stagger=0.0, label=" sweep")
        hist.update(swept)
        still = [n for n in missing if n not in swept]
        log(f"  [{country}] sweep recovered {len(swept)}/{len(missing)}"
            + (f"; still missing: {', '.join(still)}" if still else "; none missing"))
    return hist


def _apply_latest(latest_rows, hist) -> None:
    """Override LatestValue/PreviousValue/LatestValueDate from freshly scraped series."""
    for row in latest_rows:
        pairs = hist.get(row.get("Category"))
        if not pairs:
            continue
        row["LatestValue"] = pairs[-1][1]
        row["LatestValueDate"] = pairs[-1][0]
        if len(pairs) >= 2:
            row["PreviousValue"] = pairs[-2][1]
            row["PreviousValueDate"] = pairs[-2][0]


async def _run_async(names_filter, log):
    us_latest, us_meta, us_names, us_urls = load_scope("US")
    ca_latest, ca_meta, ca_names, ca_urls = load_scope("CA")

    if names_filter is not None:
        keep = set(names_filter)
        us_names = [n for n in us_names if n in keep]
        ca_names = [n for n in ca_names if n in keep]

    log(f"Trading Economics scrape scope: US {len(us_names)}, CA {len(ca_names)} indicators")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=config.USER_AGENT)
        # Block obvious ad/analytics hosts to speed up and reduce flakiness.
        await context.route(re.compile(r"(doubleclick|googlesyndication|rubiconproject|"
                                       r"pubmatic|casalemedia|adtrafficquality|temu|"
                                       r"id5-sync|media\.net)"),
                            lambda r: asyncio.ensure_future(r.abort()))
        try:
            log("=== Scraping United States ===")
            us_hist = await _scrape_country(context, "US", us_names, us_urls, log)
            log("=== Scraping Canada ===")
            ca_hist = await _scrape_country(context, "CA", ca_names, ca_urls, log)
        finally:
            await browser.close()

    _apply_latest(us_latest, us_hist)
    _apply_latest(ca_latest, ca_hist)
    return us_latest, ca_latest, us_hist, ca_hist


def run(target=None, scope: str = "full", log=print, backfill: bool = True) -> None:
    """
    Rebuild the Trading Economics sheets (Summary + category + key-indicator
    sheets) in `target` by scraping the TE website.

    scope: "full" = every in-scope indicator (faithful rebuild of the master's
           category sheets); "key" = only fetch_economics.KEY_INDICATORS (fast).
    backfill: substitute full-history FRED/BoC/StatCan data for the curated set
           of indicators that scrape missing/truncated (see te_backfill).
    """
    target = target or config.MASTER
    pulled_at = dt.datetime.now().strftime("%B %d, %Y  %H:%M")

    names_filter = None
    if scope == "key":
        names_filter = set(fe.KEY_INDICATORS)

    us_latest, ca_latest, us_hist, ca_hist = asyncio.run(_run_async(names_filter, log))

    if backfill:
        from . import te_backfill
        te_backfill.backfill(us_hist, ca_hist, us_latest, ca_latest, log)

    log("=== Building Trading Economics workbook base ===")
    wb = Workbook()
    fe.build_summary(wb, us_latest, ca_latest, pulled_at)
    for cat in fe.CATEGORIES:
        fe.build_category_sheet(wb, cat, us_hist, ca_hist, us_latest, ca_latest)
    for ind in fe.KEY_INDICATORS:
        fe.build_indicator_sheet(wb, ind, us_hist.get(ind, []), ca_hist.get(ind, []))
    wb.save(str(target))
    log(f"Saved TE base -> {target}  "
        f"(US {len(us_hist)} / CA {len(ca_hist)} series with data)")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Scrape Trading Economics into the master workbook")
    ap.add_argument("--scope", choices=["full", "key"], default="full")
    ap.add_argument("--target", default=None)
    ap.add_argument("--no-backfill", action="store_true",
                    help="skip FRED/BoC/StatCan substitution for missing TE indicators")
    args = ap.parse_args()
    run(target=args.target, scope=args.scope, backfill=not args.no_backfill)
