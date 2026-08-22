"""
Benchmark the refresher's output (scraped + supplemented) against the paid TE
API historical data cached locally in `raw_te/{US,CA}_batch_*.json`.

Usage
-----
    # 1) regenerate "mine" (fresh scrape + backfill -> /tmp/macro_mine.pkl)
    python3 -m macro_refresh._regen_mine
    # 2) run the comparison
    python3 -m macro_refresh.te_vs_api

Outputs `macro_refresh/te_vs_api_report.csv` and prints a summary.
"""
from __future__ import annotations

import bisect
import csv
import datetime as dt
import glob
import json
import pickle
import statistics as st
from pathlib import Path

from . import config

HERE = Path(__file__).resolve().parent
MINE_PKL = "/tmp/macro_mine.pkl"
REPORT = HERE / "te_vs_api_report.csv"
TODAY = dt.date.today().isoformat()

COUNTRY_NAME = {"US": "United States", "CA": "Canada"}


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #
def load_api():
    """(country_code, Category) -> {'actual': [(date,val)], 'fc': n_forecast}."""
    out: dict[tuple[str, str], dict] = {}
    for code in ("US", "CA"):
        pts: dict[str, list] = {}
        for f in glob.glob(str(config.RAW_TE / f"{code}_batch_*.json")):
            for r in json.load(open(f)):
                v = r.get("Value")
                if v is None:
                    continue
                pts.setdefault(r["Category"], []).append((r["DateTime"][:10], float(v)))
        for cat, series in pts.items():
            series.sort()
            actual = [p for p in series if p[0] <= TODAY]
            fc = sum(1 for p in series if p[0] > TODAY)
            out[(code, cat)] = {"actual": actual, "fc": fc}
    return out


def load_units():
    units = {}
    for code in ("US", "CA"):
        for r in json.loads((config.RAW_TE / f"country_{code}.json").read_text()):
            units[(code, r["Category"])] = (r.get("Unit") or "").strip()
    return units


def load_mine():
    with open(MINE_PKL, "rb") as f:
        d = pickle.load(f)
    mine = {}
    for code, key in (("US", "us_hist"), ("CA", "ca_hist")):
        for name, pairs in d[key].items():
            if pairs:
                mine[(code, name)] = sorted(pairs)
    backfilled = {tuple(x) for x in d["backfilled"]}
    return mine, backfilled


# --------------------------------------------------------------------------- #
# Alignment & metrics
# --------------------------------------------------------------------------- #
def _to_ord(s):
    return dt.date.fromisoformat(s).toordinal()


def median_spacing(series):
    """Median day-gap of the *recent* tail — robust to old, denser vintages
    (e.g. surveys that were bi-weekly decades ago but are monthly now)."""
    if len(series) < 3:
        return 31.0
    tail = series[-60:] if len(series) > 60 else series
    ords = [_to_ord(d) for d, _ in tail]
    gaps = [b - a for a, b in zip(ords, ords[1:]) if b > a]
    return st.median(gaps) if gaps else 31.0


def _bucket_fn(spacing):
    """Return (kind, fn) mapping an ISO date -> period bucket key, frequency-aware.

    Period-start vs period-end stamps (FRED stamps the 1st, TE the last day of a
    period) must land in the *same* bucket, so monthly/quarterly/annual series are
    bucketed by calendar period rather than matched by nearest raw date.
    """
    if spacing <= 20:                       # daily / weekly
        return "fine", None
    if spacing <= 75:                       # monthly
        return "month", lambda s: s[:7]
    if spacing <= 200:                      # quarterly
        return "quarter", lambda s: (s[:4], (int(s[5:7]) - 1) // 3)
    return "year", lambda s: s[:4]          # annual


def align(mine, api):
    """Pair mine points to API points for the same economic period."""
    if not mine or not api:
        return []
    spacing = median_spacing(api)
    kind, bf = _bucket_fn(spacing)

    if bf is None:  # fine-grained: nearest raw date within a small window
        window = max(5.0, 1.6 * spacing)
        a_ords = [_to_ord(d) for d, _ in api]
        a_vals = [v for _, v in api]
        pairs = []
        for d, mv in mine:
            o = _to_ord(d)
            i = bisect.bisect_left(a_ords, o)
            best = None
            for j in (i - 1, i, i + 1):
                if 0 <= j < len(a_ords):
                    dist = abs(a_ords[j] - o)
                    if best is None or dist < best[0]:
                        best = (dist, a_vals[j])
            if best and best[0] <= window:
                pairs.append((mv, best[1]))
        return pairs

    # period bucketing: last observation in each bucket wins
    a_by = {}
    for d, v in api:
        a_by[bf(d)] = v
    pairs = []
    for d, mv in mine:
        b = bf(d)
        if b in a_by:
            pairs.append((mv, a_by[b]))
    return pairs


def _period_gap(last_mine, last_api, spacing):
    """Difference between the two latest stamps measured in whole periods."""
    days = abs(_to_ord(last_mine) - _to_ord(last_api))
    return days / max(spacing, 1.0)


def classify(country, name, mine, api_rec, units, backfilled):
    api = api_rec["actual"] if api_rec else []
    is_rate = "percent" in units.get((country, name), "").lower()

    row = {
        "country": country, "indicator": name,
        "source": "backfilled" if (country, name) in backfilled else "scraped",
        "unit": units.get((country, name), ""),
        "n_mine": len(mine), "n_api": len(api),
        "first_mine": mine[0][0] if mine else "",
        "last_mine": mine[-1][0] if mine else "",
        "first_api": api[0][0] if api else "",
        "last_api": api[-1][0] if api else "",
        "api_forecast_rows": api_rec["fc"] if api_rec else "",
        "latest_mine": mine[-1][1] if mine else "",
        "latest_api": api[-1][1] if api else "",
        "latest_pct_diff": "", "overlap_n": 0, "overlap_median_absdiff": "",
        "overlap_max_absdiff": "", "overlap_corr": "", "verdict": "", "note": "",
    }

    if not api:
        row["verdict"] = "NOT_IN_API"
        return row
    if not mine:
        row["verdict"] = "MISSING_MINE"
        row["note"] = "indicator absent from refresher output"
        return row

    # latest value diff
    lm, la = mine[-1][1], api[-1][1]
    if la != 0:
        row["latest_pct_diff"] = round((lm - la) / abs(la) * 100, 3)

    pairs = align(mine, api)
    row["overlap_n"] = len(pairs)
    if pairs:
        diffs = [abs(m - a) for m, a in pairs]
        row["overlap_median_absdiff"] = round(st.median(diffs), 5)
        row["overlap_max_absdiff"] = round(max(diffs), 5)
        if len(pairs) >= 5:
            try:
                row["overlap_corr"] = round(st.correlation([m for m, _ in pairs],
                                                            [a for _, a in pairs]), 4)
            except st.StatisticsError:
                row["overlap_corr"] = ""
        med_abs = st.median(diffs)
        # Range-relative tolerance: normalise by the API series' inter-decile
        # range, which is robust for level series AND for diffusion indices that
        # swing through zero (where relative-to-median is meaningless).
        avals = sorted(a for _, a in pairs)
        idr = (avals[int(0.9 * (len(avals) - 1))] - avals[int(0.1 * (len(avals) - 1))]) or 1e-9
        rel = med_abs / idr
    else:
        med_abs = abs(lm - la)
        rel = med_abs / (abs(la) or 1e-9)

    # verdict
    if is_rate:
        if med_abs <= 0.1:
            v = "MATCH"
        elif med_abs <= 0.5:
            v = "MINOR"
        else:
            v = "MISMATCH"
    else:
        if rel <= 0.03:
            v = "MATCH"
        elif rel <= 0.10:
            v = "MINOR"
        else:
            v = "MISMATCH"
    row["verdict"] = v

    # reason notes
    notes = []
    if v != "MATCH" and not is_rate and pairs:
        ratio = st.median([m / a for m, a in pairs if a]) if any(a for _, a in pairs) else None
        if ratio and (ratio > 3 or ratio < 0.33):
            notes.append(f"scale x{ratio:.4g}")
    if row["last_mine"] and row["last_api"]:
        if _period_gap(row["last_mine"], row["last_api"], median_spacing(api)) >= 1.5:
            dgap = _to_ord(row["last_mine"]) - _to_ord(row["last_api"])
            notes.append(f"freshness {dgap:+d}d")
    row["note"] = "; ".join(notes)
    return row


# --------------------------------------------------------------------------- #
def main():
    api = load_api()
    units = load_units()
    mine, backfilled = load_mine()

    keys = sorted(set(api) | set(mine))
    rows = [classify(c, n, mine.get((c, n), []), api.get((c, n)), units, backfilled)
            for (c, n) in keys]

    cols = list(rows[0].keys())
    with open(REPORT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    # ---- summary ----
    def tally(pred):
        c = {}
        for r in rows:
            if pred(r):
                c[r["verdict"]] = c.get(r["verdict"], 0) + 1
        return c

    print(f"=== TE vs API comparison ({len(rows)} indicators) ===")
    print(f"report -> {REPORT}\n")
    order = ["MATCH", "MINOR", "MISMATCH", "MISSING_MINE", "NOT_IN_API"]
    for label, pred in [("ALL", lambda r: True),
                        ("scraped", lambda r: r["source"] == "scraped"),
                        ("backfilled", lambda r: r["source"] == "backfilled")]:
        t = tally(pred)
        tot = sum(t.values())
        line = "  ".join(f"{k}={t.get(k,0)}" for k in order if t.get(k))
        print(f"{label:11s} (n={tot}): {line}")

    print("\n--- Supplemented indicators (backfilled) detail ---")
    print(f"{'ctry':4s} {'indicator':32s} {'verdict':9s} {'latest_mine':>12s} "
          f"{'latest_api':>12s} {'%diff':>8s}  note")
    for r in rows:
        if r["source"] != "backfilled":
            continue
        pd = r["latest_pct_diff"]
        print(f"{r['country']:4s} {r['indicator'][:32]:32s} {r['verdict']:9s} "
              f"{str(r['latest_mine'])[:12]:>12s} {str(r['latest_api'])[:12]:>12s} "
              f"{(str(pd) if pd!='' else '-'):>8s}  {r['note']}")

    worst = sorted((r for r in rows if r["verdict"] == "MISMATCH"
                    and r["overlap_n"]),
                   key=lambda r: -(r["overlap_median_absdiff"] or 0))
    if worst:
        print(f"\n--- Worst scraped/other MISMATCHes (top 25 of {len([r for r in rows if r['verdict']=='MISMATCH'])}) ---")
        for r in worst[:25]:
            print(f"{r['country']:4s} {r['indicator'][:34]:34s} "
                  f"med|d|={r['overlap_median_absdiff']} unit={r['unit'][:14]:14s} "
                  f"latest m={r['latest_mine']} a={r['latest_api']}  {r['note']}")


if __name__ == "__main__":
    main()
