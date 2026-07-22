#!/usr/bin/env python3
"""
Build the BoS dashboard's data files from the Bank of Canada Business Outlook
Survey (BOS) disaggregated spreadsheet.

Reads the tidy sheets (Sector_tidy, Region_tidy, Size_tidy) plus Definitions /
Notes from ``~/Downloads/BoC_BOS_sector_region.xlsx`` (no network needed) and
writes two byte-identical payloads next to this script:

  * ``data.js``   ->  ``window.BOS_DATA = { ... };``   (used when opened via file://)
  * ``data.json`` ->  the same object as JSON            (used when served over HTTP)

Data model
----------
A single global quarter axis is shared by every chart; each member series is
aligned to it with ``null`` where a quarter is missing (so discontinued series
such as *Past sales growth* simply trail off).

    {
      "generated": "YYYY-MM-DD",
      "source": "...", "caveat": "...", "coverage": "2004 Q1 – 2026 Q2",
      "quarters": ["2004 Q1", ...],
      "members": { "sector": [...], "region": [...], "size": [...] },
      "indicators": [
        { "id","name","unit","definition","defaultBreakdown",
          "subcomponents": [
            { "id","name",
              "breakdowns": {
                 "sector": { "members":[...], "series": { member: [vals...] } },
                 "region": {...}, "size": {...} } } ] } ]
    }

Regenerate after refreshing the underlying workbook
(``~/Downloads/bos_harvest/build_xlsx.py``):

    ~/.venv-relanalysis/bin/python build_bos_data.py
"""
from __future__ import annotations

import json
import os
import re
from datetime import date

import pandas as pd

SRC = os.path.expanduser("~/Downloads/BoC_BOS_sector_region.xlsx")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "data.json")
OUT_JS = os.path.join(HERE, "data.js")

# Already-pulled Canada-vs-U.S. small-business sentiment lives in the sibling
# us-canada-macro-dashboard payload (CFIB Business Barometer vs NFIB Small
# Business Optimism Index). We reuse it here as an extra "comparison" card.
SENT_SRC = os.path.expanduser("~/us-canada-macro-dashboard/data.json")

SOURCE_LABEL = "Bank of Canada, Business Outlook Survey (Valet API, public)"

# ---- member display (short) + stable order per dimension ------------------
SECTOR_SHORT = {
    "Primary": "Primary",
    "Manufacturing": "Manufacturing",
    "CITU (constr./info/transp./util.)": "CITU",
    "Trade": "Trade",
    "FIRE (finance/insur./real estate)": "FIRE",
    "CPBS (comm./pers./bus. services)": "CPBS",
}
SECTOR_ORDER = ["Primary", "Manufacturing", "CITU", "Trade", "FIRE", "CPBS"]

REGION_SHORT = {
    "Atlantic": "Atlantic", "Quebec": "Quebec", "Ontario": "Ontario",
    "Prairies": "Prairies", "British Columbia": "BC",
    "All regions (indicator)": "All regions",
}
REGION_ORDER = ["Atlantic", "Quebec", "Ontario", "Prairies", "BC", "All regions"]

SIZE_SHORT = {"Small": "Small", "Medium-sized": "Medium", "Large": "Large"}
SIZE_ORDER = ["Small", "Medium", "Large"]

DIM_SHEETS = {"sector": "Sector_tidy", "region": "Region_tidy", "size": "Size_tidy"}
DIM_SHORT = {"sector": SECTOR_SHORT, "region": REGION_SHORT, "size": SIZE_SHORT}
DIM_ORDER = {"sector": SECTOR_ORDER, "region": REGION_ORDER, "size": SIZE_ORDER}

# indicator display order (top -> bottom on the overview page)
INDICATOR_ORDER = [
    "Past sales growth", "Past sales declines", "Future sales growth",
    "Investment in machinery & equipment", "Employment", "Capacity pressures",
    "Labour shortages", "Labour shortage intensity", "Wages",
    "Input prices", "Output prices", "Credit conditions",
    "Inflation expectations (next 2 years)", "Regional BOS indicator",
]

# preferred subcomponent order within an indicator (logical, not alphabetical)
SUB_ORDER = {
    "Inflation expectations (next 2 years)":
        ["Below 1%", "1% to 2%", "2% to 3%", "Above 3%", "No response"],
    "Capacity pressures":
        ["Some difficulty meeting demand", "Significant difficulty meeting demand"],
    "Future sales growth":
        ["Future sales (balance of opinion)", "Indicators of future sales"],
}

# Manual definition fallbacks where the workbook's Definitions text is missing
# or misleading (the harvester grabbed one example series' description).
DEF_OVERRIDE = {
    ("Past sales declines", "Share of firms reporting declines"):
        "Over the past 12 months, did your firm experience a decline in the "
        "level of sales? Shown as the share of firms reporting a decline.",
    ("Regional BOS indicator", "Contribution to regional indicator"):
        "Each region's contribution to a standardized regional Business Outlook "
        "Survey indicator (different scale and a shorter history than the "
        "by-region balance-of-opinion series).",
}


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s or "x"


def qkey(q: str) -> int:
    """'2004Q1' -> sortable int."""
    return int(q[:4]) * 4 + int(q[5])


def qlabel(q: str) -> str:
    """'2004Q1' -> '2004 Q1'."""
    return f"{q[:4]} Q{q[5]}"


def clean_definition(indicator: str, sub: str, raw) -> str:
    """Return a readable survey question for the (indicator, sub) pair."""
    override = DEF_OVERRIDE.get((indicator, sub or ""))
    if override:
        return override
    text = "" if raw is None or (isinstance(raw, float) and pd.isna(raw)) else str(raw).strip()
    if not text or text.lower() == "nan":
        return ""
    # Format is "<preamble>, four-quarter moving average - <question>"; keep the
    # question part after the first " - " (drops any region-specific preamble,
    # e.g. the inflation-expectations rows that mention "the Atlantic region").
    if " - " in text:
        text = text.split(" - ", 1)[1].strip()
    return text


def load_caveat() -> str:
    notes = pd.read_excel(SRC, sheet_name="Notes")
    for _, row in notes.iterrows():
        field = str(row.iloc[0])
        if "caveat" in field.lower() or "IMPORTANT" in field:
            return str(row.iloc[1]).strip()
    return ("Because the responses are presented as four-quarter moving averages, "
            "these charts may not show the same movements as the aggregate BOS "
            "data published each quarter.")


def build_comparison():
    """Canada (CFIB Business Barometer) vs U.S. (NFIB Small Business Optimism)
    small-business sentiment, taken from the already-pulled
    ``us-canada-macro-dashboard`` payload.

    Returns a special ``kind='comparison'`` indicator (monthly, dual-axis, two
    country series instead of sector/region/size breakdowns), or ``None`` when
    the source payload isn't available so the BoS build still succeeds.
    """
    if not os.path.exists(SENT_SRC):
        print(f"NOTE: sentiment source not found — skipping comparison card: {SENT_SRC}")
        return None
    with open(SENT_SRC) as f:
        payload = json.load(f)
    match = [i for i in payload.get("indicators", [])
             if i.get("name") == "Small Business Sentiment"]
    if not match:
        print("NOTE: 'Small Business Sentiment' not found in sentiment source — skipping.")
        return None
    si = match[0]
    dates = si["dates"]

    def rnd(v):
        return None if v is None else round(float(v), 2)

    def side(key, label, axis):
        s = si[key]
        return {
            "key": label,
            "label": label,
            "axis": axis,
            "unit": s.get("unit", ""),
            "source": s.get("source", ""),
            "values": [rnd(v) for v in s["values"]],
        }

    ca = side("canada", "Canada", "left")
    us = side("us", "United States", "right")

    def span(vals):
        idx = [i for i, v in enumerate(vals) if v is not None]
        return (idx[0], idx[-1]) if idx else (None, None)

    los = [span(ca["values"])[0], span(us["values"])[0]]
    his = [span(ca["values"])[1], span(us["values"])[1]]
    lo = min(x for x in los if x is not None)
    hi = max(x for x in his if x is not None)

    return {
        "id": "business_sentiment",
        "kind": "comparison",
        "name": "Business sentiment — Canada vs U.S.",
        "unit": "Index",
        "dates": dates,
        "coverage": f"{dates[lo]} \u2013 {dates[hi]}",
        "definition": si.get("description", ""),
        "source": "Trading Economics — CFIB Business Barometer (Canada) & "
                  "NFIB Small Business Optimism Index (U.S.)",
        "series": [ca, us],
    }


def build():
    frames = {dim: pd.read_excel(SRC, sheet_name=sheet)
              for dim, sheet in DIM_SHEETS.items()}
    for dim, df in frames.items():
        df["sub"] = df["subcomponent"].fillna("").astype(str).str.strip()

    defs = pd.read_excel(SRC, sheet_name="Definitions")
    defs["sub"] = defs["subcomponent"].fillna("").astype(str).str.strip()
    def_lookup = {(r["indicator"], r["sub"]): r["survey_definition"]
                  for _, r in defs.iterrows()}

    # ---- master quarter axis (union across every dimension) ----
    all_q = set()
    for df in frames.values():
        all_q.update(df["quarter"].dropna().unique().tolist())
    quarters = sorted(all_q, key=qkey)
    q_index = {q: i for i, q in enumerate(quarters)}
    n = len(quarters)

    # ---- catalogue of (indicator, unit, sub) present anywhere, ordered ----
    combos = (pd.concat([f[["indicator", "sub", "unit"]] for f in frames.values()])
              .drop_duplicates())
    ind_rank = {name: i for i, name in enumerate(INDICATOR_ORDER)}
    unit_of = {}
    subs_of: dict[str, list[str]] = {}
    for _, r in combos.iterrows():
        unit_of[r["indicator"]] = r["unit"]
        subs_of.setdefault(r["indicator"], [])
        if r["sub"] not in subs_of[r["indicator"]]:
            subs_of[r["indicator"]].append(r["sub"])
    # apply preferred subcomponent ordering where defined
    for indicator, order in SUB_ORDER.items():
        if indicator in subs_of:
            rank = {s: i for i, s in enumerate(order)}
            subs_of[indicator].sort(key=lambda s: rank.get(s, 999))
    indicators_sorted = sorted(subs_of, key=lambda x: ind_rank.get(x, 999))

    def breakdown_for(dim, indicator, sub):
        df = frames[dim]
        m = df[(df["indicator"] == indicator) & (df["sub"] == sub)]
        if m.empty:
            return None
        short_map, order = DIM_SHORT[dim], DIM_ORDER[dim]
        pivot = m.pivot_table(index="quarter", columns="member",
                              values="value", aggfunc="first")
        pivot.columns = [short_map.get(c, c) for c in pivot.columns]
        present = [c for c in order if c in pivot.columns]
        series = {}
        for member in present:
            col = [None] * n
            for q, v in pivot[member].items():
                if q in q_index and pd.notna(v):
                    col[q_index[q]] = round(float(v), 2)
            series[member] = col
        return {"members": present, "series": series}

    indicators = []
    for indicator in indicators_sorted:
        unit = unit_of[indicator]
        subs = subs_of[indicator]
        sub_objs = []
        dims_seen = set()
        for sub in subs:
            breakdowns = {}
            for dim in ("sector", "region", "size"):
                bd = breakdown_for(dim, indicator, sub)
                if bd:
                    breakdowns[dim] = bd
                    dims_seen.add(dim)
            if not breakdowns:
                continue
            sub_objs.append({
                "id": slug(sub) if sub else "main",
                "name": sub,
                "definition": clean_definition(indicator, sub, def_lookup.get((indicator, sub), "")),
                "breakdowns": breakdowns,
            })
        if not sub_objs:
            continue
        default_bd = "sector" if "sector" in dims_seen else (
            "region" if "region" in dims_seen else "size")
        # indicator-level definition = first subcomponent's (for the overview card)
        indicators.append({
            "id": slug(indicator),
            "name": indicator,
            "unit": unit,
            "definition": sub_objs[0]["definition"],
            "defaultBreakdown": default_bd,
            "subcomponents": sub_objs,
        })

    # Extra: Canada-vs-U.S. small-business sentiment (already-pulled), appended
    # last so it shows as a final card without disturbing the BoS indicators.
    comparison = build_comparison()
    if comparison:
        indicators.append(comparison)

    payload = {
        "generated": date.today().isoformat(),
        "source": SOURCE_LABEL,
        "caveat": load_caveat(),
        "coverage": f"{qlabel(quarters[0])} \u2013 {qlabel(quarters[-1])}",
        "quarters": [qlabel(q) for q in quarters],
        "members": {
            "sector": [SECTOR_SHORT[m] for m in
                       ["Primary", "Manufacturing", "CITU (constr./info/transp./util.)",
                        "Trade", "FIRE (finance/insur./real estate)",
                        "CPBS (comm./pers./bus. services)"]],
            "region": ["Atlantic", "Quebec", "Ontario", "Prairies", "BC", "All regions"],
            "size": ["Small", "Medium", "Large"],
        },
        "indicators": indicators,
    }
    return payload


def verify(payload):
    print("=== VERIFICATION ===")
    print(f"generated : {payload['generated']}")
    print(f"coverage  : {payload['coverage']}  ({len(payload['quarters'])} quarters)")
    print(f"indicators: {len(payload['indicators'])}")
    for ind in payload["indicators"]:
        if ind.get("kind") == "comparison":
            pts = sum(1 for s in ind["series"] for v in s["values"] if v is not None)
            print(f"  {ind['name'][:38]:38s} unit={ind['unit'][:12]:12s} "
                  f"kind=comparison       series={len(ind['series'])} "
                  f"pts={pts:5d}  [{ind['coverage']}]")
            continue
        dims = set()
        pts = 0
        for s in ind["subcomponents"]:
            for dim, bd in s["breakdowns"].items():
                dims.add(dim)
                for vals in bd["series"].values():
                    pts += sum(1 for v in vals if v is not None)
        subs = ", ".join(s["name"] or "(main)" for s in ind["subcomponents"])
        print(f"  {ind['name'][:38]:38s} unit={ind['unit'][:12]:12s} "
              f"dims={','.join(sorted(dims)):18s} subs={len(ind['subcomponents'])} "
              f"pts={pts:5d}  [{subs[:60]}]")


def main():
    if not os.path.exists(SRC):
        raise SystemExit(f"ERROR: source workbook not found: {SRC}")
    payload = build()
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, separators=(",", ":"), ensure_ascii=False)
    with open(OUT_JS, "w") as f:
        f.write("window.BOS_DATA = ")
        json.dump(payload, f, separators=(",", ":"), ensure_ascii=False)
        f.write(";\n")
    verify(payload)
    print(f"\nWrote {OUT_JSON}")
    print(f"Wrote {OUT_JS}")


if __name__ == "__main__":
    main()
