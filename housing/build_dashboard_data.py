#!/usr/bin/env python3
"""
Build data.js / data.json for the Canada Housing Indices dashboard.

Reads the deliverable workbook (~/Downloads/canada_housing_indices.xlsx, produced
by ~/Downloads/housing_indices/build_housing_indices.py) and emits a single
compact JSON payload consumed by index.html (offline, file://).

Shape (window.HOUSING_DATA):
{
  generated, source_note,
  families: {
    teranet: { name, method, freq:"monthly", base, source, unit_note,
               dates:[YYYY-MM], geographies:[...], national:"Composite 11",
               measures:[{key,label,unit,fmt}],
               series:{ geo:{ measure:[floats|null] } } },
    crea:    { ... property_types:[...], national:"Canada (National aggregate)",
               series:{ geo:{ ptype:{ measure:[...] } } } },
    statcan: { name, method, freq:"annual", source, caveat,
               years:[...], geographies:[...], national:"Canada",
               measures:[...], series:{ geo:{ measure:[...] , _src:[labels] } } }
  },
  compare: { dates:[YYYY-MM], series:{ teranet_c11_yoy, crea_national_yoy,
             statcan_canada_yoy, teranet_c11_index, crea_national_index,
             statcan_canada_value_Mcad } }
}

Usage: ~/.venv-relanalysis/bin/python build_dashboard_data.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path

import pandas as pd

SRC = Path(os.path.expanduser("~/Downloads/canada_housing_indices.xlsx"))
HERE = Path(__file__).resolve().parent


def _num(v):
    """JSON-safe float (NaN/inf -> None)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 4)


def _mkey(d: pd.DataFrame) -> str:
    return d.columns[0]


def build_teranet(xl: pd.ExcelFile) -> dict:
    df = xl.parse("Teranet_NB")
    df["ym"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
    dates = sorted(df["ym"].unique())
    idx = {d: i for i, d in enumerate(dates)}
    measures = [
        {"key": "index_nsa", "label": "Index level (NSA)", "unit": "index, Jun 2005 = 100", "fmt": "num1"},
        {"key": "index_sa", "label": "Index level (SA)", "unit": "index, Jun 2005 = 100", "fmt": "num1"},
        {"key": "mom_pct_nsa", "label": "MoM % change (NSA)", "unit": "% m/m", "fmt": "pct2"},
        {"key": "yoy_pct_nsa", "label": "YoY % change (NSA)", "unit": "% y/y", "fmt": "pct2"},
    ]
    geos = sorted(df["geography"].unique(), key=lambda g: (g != "Composite 11", g))
    series: dict = {}
    for geo, g in df.groupby("geography"):
        series[geo] = {}
        for m in measures:
            arr = [None] * len(dates)
            for _, r in g.iterrows():
                arr[idx[r["ym"]]] = _num(r[m["key"]])
            series[geo][m["key"]] = arr
    return {
        "name": "Teranet–National Bank HPI",
        "short": "Teranet–NB",
        "method": "Repeat-sales (matched resale pairs)",
        "freq": "monthly",
        "base": "Jun 2005 = 100",
        "source": str(df["source"].iloc[0]),
        "dates": dates,
        "geographies": geos,
        "national": "Composite 11",
        "measures": measures,
        "series": series,
    }


def build_crea(xl: pd.ExcelFile) -> dict:
    df = xl.parse("CREA_MLS_HPI")
    df["ym"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
    dates = sorted(df["ym"].unique())
    idx = {d: i for i, d in enumerate(dates)}
    measures = [
        {"key": "index_sa", "label": "Index level (SA)", "unit": "index, Jan 2005 = 100", "fmt": "num1"},
        {"key": "benchmark_cad_sa", "label": "Benchmark price (SA)", "unit": "C$", "fmt": "cad0"},
        {"key": "mom_pct", "label": "MoM % change", "unit": "% m/m", "fmt": "pct2"},
        {"key": "yoy_pct", "label": "YoY % change", "unit": "% y/y", "fmt": "pct2"},
    ]
    ptypes = ["Composite", "Single Family", "One Storey", "Two Storey", "Townhouse", "Apartment"]
    natl = "Canada (National aggregate)"
    geos = sorted(df["geography"].unique(), key=lambda g: (g != natl, g))
    series: dict = {}
    for (geo, pt), g in df.groupby(["geography", "property_type"]):
        series.setdefault(geo, {})
        series[geo][pt] = {}
        for m in measures:
            arr = [None] * len(dates)
            for _, r in g.iterrows():
                arr[idx[r["ym"]]] = _num(r[m["key"]])
            series[geo][pt][m["key"]] = arr
    return {
        "name": "CREA MLS® Home Price Index",
        "short": "CREA MLS HPI",
        "method": "Hedonic / benchmark (quality-adjusted benchmark home)",
        "freq": "monthly",
        "base": "Jan 2005 = 100",
        "source": str(df["source"].iloc[0]),
        "dates": dates,
        "geographies": geos,
        "property_types": [p for p in ptypes if p in df["property_type"].unique()],
        "national": natl,
        "measures": measures,
        "series": series,
    }


def build_statcan(xl: pd.ExcelFile) -> dict:
    df = xl.parse("StatCan_Assessment")
    years = sorted(int(y) for y in df["year"].unique())
    idx = {y: i for i, y in enumerate(years)}
    measures = [
        {"key": "value_cad_millions", "label": "Assessment value", "unit": "C$ millions", "fmt": "cadM"},
        {"key": "yoy_pct", "label": "YoY % change", "unit": "% y/y", "fmt": "pct2"},
    ]
    order = ["Canada", "British Columbia", "Alberta", "Saskatchewan", "Manitoba",
             "Ontario", "Quebec", "New Brunswick", "Nova Scotia",
             "Prince Edward Island", "Newfoundland and Labrador",
             "Yukon", "Northwest Territories", "Nunavut"]
    geos = [g for g in order if g in set(df["geography"])]
    series: dict = {}
    for geo, g in df.groupby("geography"):
        series[geo] = {"value_cad_millions": [None] * len(years),
                       "yoy_pct": [None] * len(years),
                       "_src": [None] * len(years)}
        for _, r in g.iterrows():
            i = idx[int(r["year"])]
            series[geo]["value_cad_millions"][i] = _num(r["value_cad_millions"])
            series[geo]["yoy_pct"][i] = _num(r["yoy_pct"])
            src = str(r["source"])
            series[geo]["_src"][i] = "extension" if "provincial-authority" in src else "statcan"
    return {
        "name": "StatCan Residential Property Values",
        "short": "StatCan assessment",
        "method": "Appraisal / assessment based",
        "freq": "annual",
        "base": "Total residential assessment value (C$)",
        "source": "StatCan table 34-10-0013 (record #5191 vintage) + provincial-authority extension",
        "caveat": ("StatCan series ends 2015 (program discontinued). Post-2015 rows are Alberta "
                   "equalized assessment (market-audited) — an authority-specific extension, not a "
                   "continuation of the harmonized national total. See workbook Provincial_Sources."),
        "years": years,
        "geographies": geos,
        "national": "Canada",
        "measures": measures,
        "series": series,
    }


def build_compare(xl: pd.ExcelFile) -> dict:
    df = xl.parse("Compare_National")
    df["ym"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
    df = df.sort_values("ym")
    cols = ["teranet_c11_index", "teranet_c11_yoy", "crea_national_index",
            "crea_national_yoy", "statcan_canada_value_Mcad", "statcan_canada_yoy"]
    return {
        "dates": df["ym"].tolist(),
        "series": {c: [_num(v) for v in df[c]] for c in cols},
    }


def main() -> int:
    if not SRC.exists():
        raise SystemExit(f"Workbook not found: {SRC}. Run build_housing_indices.py first.")
    xl = pd.ExcelFile(SRC)
    payload = {
        "generated": dt.date.today().isoformat(),
        "source_note": ("Teranet–National Bank HPI (repeat-sales), CREA MLS HPI (hedonic/benchmark) "
                        "and StatCan / provincial assessment values (appraisal). Pulled from source; "
                        "see ~/Downloads/canada_housing_indices.xlsx."),
        "families": {
            "teranet": build_teranet(xl),
            "crea": build_crea(xl),
            "statcan": build_statcan(xl),
        },
        "compare": build_compare(xl),
    }
    js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    (HERE / "data.json").write_text(js, encoding="utf-8")
    (HERE / "data.js").write_text("window.HOUSING_DATA = " + js + ";\n", encoding="utf-8")

    t, c, s = payload["families"]["teranet"], payload["families"]["crea"], payload["families"]["statcan"]
    print(f"data.js / data.json written to {HERE}")
    print(f"  Teranet : {len(t['geographies'])} geos, {len(t['dates'])} months "
          f"({t['dates'][0]}..{t['dates'][-1]})")
    print(f"  CREA    : {len(c['geographies'])} geos x {len(c['property_types'])} types, "
          f"{len(c['dates'])} months ({c['dates'][0]}..{c['dates'][-1]})")
    print(f"  StatCan : {len(s['geographies'])} geos, years {s['years'][0]}..{s['years'][-1]}")
    print(f"  Compare : {len(payload['compare']['dates'])} months")
    print(f"  size    : {len(js)/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
