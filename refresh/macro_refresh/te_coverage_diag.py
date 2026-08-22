"""
Diagnostic: scrape every in-scope TE indicator and report coverage.

Classifies each indicator as:
  - missing   : page scraped but no chart data captured
  - truncated : scraped earliest date is >1.2y later than TE's FirstValueDate
                (i.e. we only got the default ~window, not full history)
  - ok        : full history captured

Writes /tmp/te_coverage.csv and prints a summary.
"""
import asyncio, csv, datetime as dt
from playwright.async_api import async_playwright
from macro_refresh import config, te_scrape as ts


def _truncated(first_scraped, meta_first, freq):
    if not first_scraped or not meta_first:
        return False
    try:
        a = dt.date.fromisoformat(first_scraped[:10])
        b = dt.date.fromisoformat(meta_first[:10])
    except Exception:
        return False
    gap_years = (a - b).days / 365.25
    return gap_years > 1.2


async def run():
    rows = []
    for country in ("US", "CA"):
        latest, meta, names, url_map = ts.load_scope(country)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(user_agent=config.USER_AGENT)
            sem = asyncio.Semaphore(config.TE_CONCURRENCY)
            results = {}

            async def work(name):
                url = url_map.get(name)
                if not url:
                    results[name] = None
                    return
                async with sem:
                    results[name] = await ts._scrape_one(ctx, country, name, url, lambda *_: None)

            await asyncio.gather(*(work(n) for n in names))
            await browser.close()

        for name in names:
            pairs = results.get(name)
            m = meta.get(name, {})
            n = len(pairs) if pairs else 0
            first = pairs[0][0] if pairs else ""
            last = pairs[-1][0] if pairs else ""
            if not pairs:
                status = "missing"
            elif _truncated(first, m.get("first"), m.get("freq")):
                status = "truncated"
            else:
                status = "ok"
            rows.append({
                "country": country, "indicator": name, "group": m.get("group", ""),
                "freq": m.get("freq", ""), "url": url_map.get(name, ""),
                "n": n, "first": first, "last": last,
                "meta_first": (m.get("first") or "")[:10], "status": status,
            })
        print(f"{country}: {len(names)} indicators scraped")

    with open("/tmp/te_coverage.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    by_status = Counter(r["status"] for r in rows)
    print("\n=== COVERAGE SUMMARY ===")
    print(by_status)
    print("\n--- MISSING ---")
    for r in rows:
        if r["status"] == "missing":
            print(f"  [{r['country']}] {r['indicator']}  ({r['group']}, {r['freq']})  {r['url']}")
    print("\n--- TRUNCATED ---")
    for r in rows:
        if r["status"] == "truncated":
            print(f"  [{r['country']}] {r['indicator']}  got {r['n']} pts {r['first']}->{r['last']} "
                  f"(meta first {r['meta_first']})  {r['url']}")


if __name__ == "__main__":
    asyncio.run(run())
