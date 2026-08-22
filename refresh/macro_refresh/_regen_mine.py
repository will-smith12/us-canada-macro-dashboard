"""Regenerate scraped + supplemented histories and pickle them for comparison."""
import asyncio
import pickle
import sys

from macro_refresh import te_scrape as ts, te_backfill as tb

OUT = "/tmp/macro_mine.pkl"


def main():
    def log(m):
        print(m, file=sys.__stdout__, flush=True)

    us_latest, ca_latest, us_hist, ca_hist = asyncio.run(ts._run_async(None, log))
    tb.backfill(us_hist, ca_hist, us_latest, ca_latest, log)

    backfilled = {("US", n) for (c, n) in tb.REGISTRY if c == "US"}
    backfilled |= {("CA", n) for (c, n) in tb.REGISTRY if c == "CA"}

    with open(OUT, "wb") as f:
        pickle.dump({
            "us_hist": us_hist, "ca_hist": ca_hist,
            "us_latest": us_latest, "ca_latest": ca_latest,
            "backfilled": list(backfilled),
        }, f)
    log(f"Pickled mine -> {OUT}  (US {len(us_hist)} / CA {len(ca_hist)} series)")


if __name__ == "__main__":
    main()
