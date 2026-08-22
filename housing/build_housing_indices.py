#!/usr/bin/env python3
"""
Build housing/data/canada_housing_indices.xlsx — Canada's three main house-price
index families, each from a different methodology, pulled from source:

  1. Teranet-National Bank HPI   — repeat-sales method (housepriceindex.ca JSON, decoded)
  2. CREA MLS(R) HPI             — hedonic / benchmark method (crea.ca zip of workbooks)
  3. StatCan Property Values     — appraisal / assessment based (WDS table 34-10-0013,
                                   record #5191), + provincial-authority extension (2016+)

All sources are public (no API key). External fetches go through the system `curl`
(the corporate MITM proxy breaks Python's SSL trust store; curl trusts it).

Usage:
    python build_housing_indices.py [--no-fetch]

Fetched files land in housing/_work/ and the workbook in housing/data/; both are
resolved next to this script, so a fresh clone works with no configuration.
Override with HOUSING_WORK / HOUSING_XLSX if you need them elsewhere.

--no-fetch reuses already-downloaded files in the working dir (offline / re-run).
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import glob
import json
import math
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
# Paths resolve next to this script so a fresh clone works anywhere. The env
# vars are escape hatches, not the normal path.
WORK = Path(os.environ.get("HOUSING_WORK") or HERE / "_work")
OUT = Path(os.environ.get("HOUSING_XLSX") or HERE / "data" / "canada_housing_indices.xlsx")
WORK.mkdir(parents=True, exist_ok=True)
OUT.parent.mkdir(parents=True, exist_ok=True)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
PULL_DATE = dt.date.today().isoformat()

WORK.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# fetch helpers (curl subprocess)
# --------------------------------------------------------------------------- #
def curl(url: str, dest: Path, headers: dict | None = None, tries: int = 3) -> Path:
    """Download `url` to `dest` via curl. Raises on failure."""
    cmd = ["curl", "-sS", "--fail", "--max-time", "180", "-A", UA]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    cmd += [url, "-o", str(dest)]
    last = None
    for i in range(tries):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            return dest
        last = r.stderr.strip()
    raise RuntimeError(f"curl failed for {url}: {last}")


def curl_head_ok(url: str) -> bool:
    r = subprocess.run(["curl", "-sS", "-I", "--max-time", "40", "-A", UA, url],
                       capture_output=True, text=True)
    first = (r.stdout.splitlines() or [""])[0]
    return " 200" in first or " 302" in first


def month_iter(start: str, n: int):
    """Yield n monthly `YYYY-MM-01` date strings from start='YYYY-MM-01'."""
    y, m = int(start[:4]), int(start[5:7])
    for _ in range(n):
        yield dt.date(y, m, 1)
        m += 1
        if m > 12:
            m = 1
            y += 1


def add_changes(df: pd.DataFrame, group_cols, value_col, periods_year: int) -> pd.DataFrame:
    """Add mom_pct / period-over-period and yoy_pct within each group (sorted by date)."""
    df = df.sort_values(group_cols + [df.columns[0]]).copy()
    g = df.groupby(group_cols, dropna=False)[value_col]
    if periods_year == 12:  # monthly
        df["mom_pct"] = (g.pct_change(1) * 100).round(2)
        df["yoy_pct"] = (g.pct_change(12) * 100).round(2)
    elif periods_year == 4:  # quarterly
        df["qoq_pct"] = (g.pct_change(1) * 100).round(2)
        df["yoy_pct"] = (g.pct_change(4) * 100).round(2)
    else:  # annual
        df["yoy_pct"] = (g.pct_change(1) * 100).round(2)
    return df


# --------------------------------------------------------------------------- #
# 1. Teranet-National Bank HPI  (repeat-sales)
# --------------------------------------------------------------------------- #
TERANET_URL = "https://housepriceindex.ca/_data/indx_data.json"
# Composite 11 + the 11 CMAs that make up the Composite 11.
TERANET_CODES = ["c11", "bc_victoria", "bc_vancouver", "ab_calgary", "ab_edmonton",
                 "mb_winnipeg", "on_hamilton", "on_toronto", "on_ottawa",
                 "qc_montreal", "qc_quebec_city", "ns_halifax"]


def _unmunge(v):
    """Reverse Teranet's client-side obfuscation (hpi.js unmunge): v - round(frac(v)*100)."""
    if v is None or v == 0:
        return None if v is None else v
    d = round((v - math.floor(v)) * 100)
    if not d:
        return v
    return round((v - d) * 100) / 100


def build_teranet(fetch: bool) -> pd.DataFrame:
    raw = WORK / "teranet_indx_data.json"
    if fetch or not raw.exists():
        curl(TERANET_URL, raw,
             headers={"Referer": "https://housepriceindex.ca/index-history/",
                      "Accept": "application/json,*/*"})
    d = json.loads(raw.read_text())
    data, prof = d["data"], d["profiles"]
    start = data["meta"]["start_date"]        # e.g. 1990-06-01
    n = len(data["indx"]["c11"])
    dates = list(month_iter(start, n))

    rows = []
    for code in TERANET_CODES:
        name = prof.get(code, {}).get("name", code)
        nsa = [_unmunge(v) for v in data["indx"][code]]
        sa = [_unmunge(v) for v in data["sa_indx"][code]]
        for i, day in enumerate(dates):
            if nsa[i] is None and sa[i] is None:
                continue
            rows.append({
                "date": day, "geography": name,
                "index_nsa": nsa[i], "index_sa": sa[i],
            })
    df = pd.DataFrame(rows)
    df = add_changes(df, ["geography"], "index_nsa", 12)
    df = df.rename(columns={"mom_pct": "mom_pct_nsa", "yoy_pct": "yoy_pct_nsa"})
    df["source"] = "Teranet-National Bank HPI (repeat-sales)"
    df["index_base"] = "Jun 2005 = 100"
    print(f"  Teranet: {len(df):,} rows, {df['geography'].nunique()} geographies, "
          f"{df['date'].min()}..{df['date'].max()}")
    return df[["date", "geography", "index_nsa", "index_sa",
               "mom_pct_nsa", "yoy_pct_nsa", "index_base", "source"]]


# --------------------------------------------------------------------------- #
# 2. CREA MLS(R) HPI  (hedonic / benchmark)
# --------------------------------------------------------------------------- #
CREA_URL = "https://www.crea.ca/files/mls-hpi-data/MLS_HPI_{month}_{year}.zip"
# AGGREGATE(national) + the province-level sheets present in the workbook.
CREA_PROVINCE_SHEETS = {
    "AGGREGATE": "Canada (National aggregate)",
    "BRITISH_COLUMBIA": "British Columbia",
    "ALBERTA": "Alberta",
    "SASKATCHEWAN": "Saskatchewan",
    "ONTARIO": "Ontario",
    "QUEBEC": "Quebec",
    "NEW_BRUNSWICK": "New Brunswick",
    "NOVA_SCOTIA": "Nova Scotia",
    "PRINCE_EDWARD_ISLAND": "Prince Edward Island",
    "NEWFOUNDLAND_AND_LABRADOR": "Newfoundland and Labrador",
}
CREA_PTYPES = ["Composite", "Single_Family", "One_Storey", "Two_Storey",
               "Townhouse", "Apartment"]


def resolve_crea_zip(fetch: bool) -> Path:
    existing = sorted(WORK.glob("MLS_HPI_*.zip"))
    if not fetch and existing:
        return existing[-1]
    today = dt.date.today().replace(day=1)
    for back in range(0, 6):
        y = today.year
        m = today.month - back
        while m <= 0:
            m += 12
            y -= 1
        month_name = calendar.month_name[m]
        url = CREA_URL.format(month=month_name, year=y)
        if curl_head_ok(url):
            dest = WORK / f"MLS_HPI_{month_name}_{y}.zip"
            if fetch or not dest.exists():
                curl(url, dest)
            print(f"  CREA zip: {dest.name}")
            return dest
    raise RuntimeError("No CREA HPI zip found in the last 6 months.")


def build_crea(fetch: bool) -> pd.DataFrame:
    zpath = resolve_crea_zip(fetch)
    extract = WORK / "crea_extract"
    extract.mkdir(exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(extract)
    xlsx = extract / "Seasonally Adjusted (M).xlsx"
    xl = pd.ExcelFile(xlsx)

    frames = []
    for sheet, geo in CREA_PROVINCE_SHEETS.items():
        if sheet not in xl.sheet_names:
            print(f"    CREA: sheet {sheet} missing, skipping")
            continue
        raw = xl.parse(sheet)
        raw = raw.rename(columns={raw.columns[0]: "date"})
        raw["date"] = pd.to_datetime(raw["date"]).dt.date
        for pt in CREA_PTYPES:
            icol = f"{pt}_HPI_SA"
            bcol = f"{pt}_Benchmark_SA"
            if icol not in raw.columns:
                continue
            sub = raw[["date", icol] + ([bcol] if bcol in raw.columns else [])].copy()
            sub = sub.rename(columns={icol: "index_sa", bcol: "benchmark_cad_sa"})
            if "benchmark_cad_sa" not in sub.columns:
                sub["benchmark_cad_sa"] = pd.NA
            sub["geography"] = geo
            sub["property_type"] = pt.replace("_", " ")
            sub = sub.dropna(subset=["index_sa"])
            frames.append(sub)
    df = pd.concat(frames, ignore_index=True)
    df = add_changes(df, ["geography", "property_type"], "index_sa", 12)
    df["source"] = "CREA MLS HPI (hedonic/benchmark, seasonally adjusted)"
    df["index_base"] = "Jan 2005 = 100"
    print(f"  CREA: {len(df):,} rows, {df['geography'].nunique()} geographies, "
          f"{df['property_type'].nunique()} property types, "
          f"{df['date'].min()}..{df['date'].max()}")
    return df[["date", "geography", "property_type", "index_sa", "benchmark_cad_sa",
               "mom_pct", "yoy_pct", "index_base", "source"]]


# --------------------------------------------------------------------------- #
# 3. StatCan Property Values 34-10-0013  (appraisal / assessment) + extension
# --------------------------------------------------------------------------- #
STATCAN_PID = "34100013"
STATCAN_GEOS = [
    "Canada", "Newfoundland and Labrador", "Prince Edward Island", "Nova Scotia",
    "New Brunswick", "Quebec", "Ontario", "Manitoba", "Saskatchewan", "Alberta",
    "British Columbia", "Yukon", "Northwest Territories", "Nunavut",
]


def build_statcan(fetch: bool) -> pd.DataFrame:
    zpath = WORK / "sc_34100013.zip"
    if fetch or not zpath.exists():
        meta = subprocess.run(
            ["curl", "-sS", "--max-time", "60", "-A", UA,
             f"https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/{STATCAN_PID}/en"],
            capture_output=True, text=True)
        link = json.loads(meta.stdout)["object"]
        curl(link, zpath)
    extract = WORK / "sc_34100013"
    extract.mkdir(exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(extract)
    csv = [x for x in glob.glob(str(extract / "*.csv")) if "MetaData" not in x][0]
    raw = pd.read_csv(csv, dtype=str)
    raw = raw[raw["GEO"].isin(STATCAN_GEOS)].copy()
    raw["value_cad_millions"] = pd.to_numeric(raw["VALUE"], errors="coerce")
    df = raw[["REF_DATE", "GEO", "value_cad_millions"]].rename(
        columns={"REF_DATE": "year", "GEO": "geography"})
    df["year"] = df["year"].astype(int)
    df = df.dropna(subset=["value_cad_millions"])
    df = add_changes(df.rename(columns={"year": "date"}), ["geography"],
                     "value_cad_millions", 1).rename(columns={"date": "year"})
    df["source"] = "StatCan 34-10-0013 Residential property values (assessment-based, #5191 vintage)"
    print(f"  StatCan: {len(df):,} rows, {df['geography'].nunique()} geographies, "
          f"{df['year'].min()}..{df['year'].max()}")
    # provincial-authority extension (2016+): Alberta equalized assessment (scriptable),
    # plus anything the user drops into provincial_extension.csv.
    exts = [e for e in (build_alberta_extension(fetch), load_provincial_extension())
            if e is not None and len(e)]
    if exts:
        df = pd.concat([df] + exts, ignore_index=True)
        print(f"  StatCan + provincial extension(s): {len(df):,} total rows")
    return df[["year", "geography", "value_cad_millions", "yoy_pct", "source"]]


# Alberta Municipal Affairs "Updated equalized assessment" (open.alberta.ca).
# Per-municipality XLSX; residential column summed to a province-wide total.
# The full 2005+ time series lives on regionaldashboard.alberta.ca (not fetched here);
# open.alberta.ca currently exposes the three most recent years.
ALBERTA_XLSX = {
    2024: ("https://open.alberta.ca/dataset/c41ae976-81fd-43e8-8094-adde75dc3ffc/resource/"
           "7beda02a-23a7-4a4a-a0ba-c4efcd11d1e3/download/"
           "ma-updated-equalized-assessment-report-2024.xlsx"),
    2025: ("https://open.alberta.ca/dataset/c41ae976-81fd-43e8-8094-adde75dc3ffc/resource/"
           "a3f97676-0355-4858-927a-2d99fae7d0e2/download/"
           "ma-updated-equalized-assessment-report-2025.xlsx"),
    2026: ("https://open.alberta.ca/dataset/c41ae976-81fd-43e8-8094-adde75dc3ffc/resource/"
           "40a9f8cc-d87a-4a4d-b5b7-37deda763cd0/download/"
           "ma-updated-equalized-assessment-report-2026.xlsx"),
}


def build_alberta_extension(fetch: bool) -> pd.DataFrame | None:
    """Alberta residential equalized assessment total ($M), summed over municipalities."""
    rows = []
    for year, url in ALBERTA_XLSX.items():
        dest = WORK / f"ab_{year}.xlsx"
        try:
            if fetch or not dest.exists():
                curl(url, dest)
            raw = pd.read_excel(dest, header=6, dtype=str)
            rescol = [c for c in raw.columns
                      if "Residential Equalized" in str(c) and "Non" not in str(c)]
            if not rescol:
                print(f"    Alberta {year}: residential column not found, skipping")
                continue
            vals = pd.to_numeric(raw[rescol[0]], errors="coerce")
            code = pd.to_numeric(raw[raw.columns[0]], errors="coerce")
            mask = code.notna() & vals.notna()          # real municipality rows only
            rows.append({"year": year, "geography": "Alberta",
                         "value_cad_millions": round(float(vals[mask].sum()) / 1e6, 1)})
        except Exception as e:
            print(f"    Alberta {year}: {e}")
    if not rows:
        return None
    ext = pd.DataFrame(rows).sort_values("year")
    ext["yoy_pct"] = (ext["value_cad_millions"].pct_change(1) * 100).round(2)
    ext["source"] = ("Alberta Municipal Affairs, Updated Equalized Assessment "
                     "(residential, market-audited; open.alberta.ca) [provincial-authority extension]")
    print(f"  Alberta extension: {len(ext)} years {ext['year'].min()}..{ext['year'].max()}")
    return ext[["year", "geography", "value_cad_millions", "yoy_pct", "source"]]


def load_provincial_extension() -> pd.DataFrame | None:
    """Optional: read provincial_extension.csv (year,geography,value_cad_millions,source)
    assembled from provincial assessment authorities. Returns None if absent."""
    p = WORK / "provincial_extension.csv"
    if not p.exists():
        return None
    ext = pd.read_csv(p)
    need = {"year", "geography", "value_cad_millions", "source"}
    if not need.issubset(ext.columns):
        print(f"    provincial_extension.csv missing cols {need - set(ext.columns)}; ignoring")
        return None
    ext["year"] = ext["year"].astype(int)
    ext = ext.sort_values(["geography", "year"])
    ext["yoy_pct"] = (ext.groupby("geography")["value_cad_millions"].pct_change(1) * 100).round(2)
    return ext[["year", "geography", "value_cad_millions", "yoy_pct", "source"]]


# --------------------------------------------------------------------------- #
# National comparison
# --------------------------------------------------------------------------- #
def build_compare(teranet: pd.DataFrame, crea: pd.DataFrame,
                  statcan: pd.DataFrame) -> pd.DataFrame:
    t = (teranet[teranet["geography"] == "Composite 11"][["date", "index_nsa", "yoy_pct_nsa"]]
         .rename(columns={"index_nsa": "teranet_c11_index", "yoy_pct_nsa": "teranet_c11_yoy"}))
    c = (crea[(crea["geography"].str.startswith("Canada")) &
              (crea["property_type"] == "Composite")][["date", "index_sa", "yoy_pct"]]
         .rename(columns={"index_sa": "crea_national_index", "yoy_pct": "crea_national_yoy"}))
    comp = pd.merge(t, c, on="date", how="outer").sort_values("date")
    comp["year"] = pd.to_datetime(comp["date"]).dt.year
    s = (statcan[statcan["geography"] == "Canada"][["year", "value_cad_millions", "yoy_pct"]]
         .rename(columns={"value_cad_millions": "statcan_canada_value_Mcad",
                          "yoy_pct": "statcan_canada_yoy"}))
    comp = pd.merge(comp, s, on="year", how="left")
    return comp[["date", "teranet_c11_index", "teranet_c11_yoy",
                 "crea_national_index", "crea_national_yoy",
                 "statcan_canada_value_Mcad", "statcan_canada_yoy"]]


def provincial_sources_frame() -> pd.DataFrame:
    """Roadmap for extending the appraisal/assessment pillar past StatCan's 2015 cutoff.
    Each provincial assessment authority differs in format, base date and comparability."""
    cols = ["Jurisdiction", "Best source", "Format / scriptable",
            "2016-2026 coverage", "Provincial total?", "Key caveat vs 34-10-0013", "URL"]
    rows = [
        ["Alberta", "Municipal Affairs 'Updated / Total Equalized Assessment'",
         "XLSX/CSV/JSON - yes (INCLUDED here, 2024-26)", "Full (2005+ on regional dashboard)",
         "Aggregate muni -> province (single file)",
         "Equalized = market-audited; includes farmland line. Best/cleanest source.",
         "https://open.alberta.ca/opendata/total-equalized-assessment-by-municipality"],
        ["Ontario", "Financial Information Return (FIR), Schedule 26",
         "CSV by year - yes", "Full", "Aggregate muni -> province",
         "CRITICAL: assessed values FROZEN at Jan 1 2016 valuation (reassessment postponed) "
         "-> does NOT reflect 2016-26 market growth.",
         "https://data.ontario.ca/dataset/financial-information-return-fir-for-municipalities"],
        ["Quebec", "MAMH 'Donnees statistiques sur l'evaluation fonciere'",
         "Excel - yes (portal JS-rendered)", "2016-2026",
         "Province tables published",
         "Triennial rolls; use 'valeur uniformisee' for cross-year comparability; imposable "
         "excludes exempt properties.",
         "https://www.quebec.ca/habitation-territoire/information-fonciere/evaluation-fonciere/statistiques"],
        ["British Columbia", "BC Assessment completed-roll reports (Class 1 residential)",
         "PDF/HTML; open bulk extract access-restricted", "Full (not clean-open)",
         "Province total (in reports)",
         "Concept closest to 34-10-0013, but not a clean download; property-level extract is "
         "'Access Only' (BCeID/government).",
         "https://info.bcassessment.ca/property-information-trends"],
        ["Nova Scotia", "PVSC datazONE 'Assessed Value ... History' (bt58-qu28)",
         "Socrata API/CSV - yes", "Rolling last 5 tax years only", "Aggregate per-account",
         "Use uncapped Assessed Value (NOT CAP-limited Taxable). Only ~2021+ available now.",
         "https://www.thedatazone.ca/Assessment/Assessed-Value-and-Taxable-Assessed-Value-History/bt58-qu28"],
        ["New Brunswick", "Service NB / GeoNB 'Property Assessment Data'",
         "TSV/CSV per-property - yes", "Full (annual)", "Aggregate per-property",
         "Market-current (assessed as of Jan 1 each year). Split residential from the "
         "per-property file yourself.",
         "https://geonb.snb.ca/downloads/evan/geonb_evan_tsv.zip"],
        ["Manitoba", "MB geoportal 'ROLL ENTRY' + City of Winnipeg Socrata",
         "CSV/API per-property - yes", "Current + history", "Aggregate (2 portals)",
         "Use full (not portioned) assessed value; biennial reassessment; stitch province "
         "(ex-Winnipeg) + Winnipeg.",
         "https://geoportal.gov.mb.ca/datasets/manitoba::roll-entry"],
        ["Saskatchewan", "SAMA Annual Reports (totals by class)",
         "PDF only", "Full (PDF)", "Province total (PDF)",
         "4-year revaluation cycle (2013/17/21/25) -> stepwise jumps; PDF extraction required.",
         "https://www.sama.sk.ca/document-library-news/annual-reports"],
        ["Newfoundland & Labrador", "Municipal Assessment Agency (MAA) annual reports",
         "PDF only", "Full (PDF)", "MAA total EXCLUDES City of St. John's",
         "PDF extraction; add St. John's (self-assessed) separately for a true provincial total.",
         "https://www.maa.ca"],
        ["Prince Edward Island", "Finance PEI / MATI",
         "HTML/PDF; data request", "Sparse", "n/a",
         "No machine-readable provincial residential total; owner-occ taxable capped at CPI/5%.",
         "https://www.princeedwardisland.ca/en/information/finance-and-affordability/property-assessment"],
        ["Territories (YT/NT/NU)", "Municipal rolls only (e.g. City of Yellowknife)",
         "None aggregate", "Largely none", "Municipal only",
         "No territory-wide residential assessment total; historical 34-10-0013 may be the only basis.",
         "https://open.data.gov.nt.ca"],
        ["-- Note --",
         "StatCan program #5191 (harmonized Property Values) was discontinued ~2016; 34-10-0013 "
         "ends 2015. StatCan CHSP publishes assessment-value tables (46-10-xxxx) but only single-year "
         "snapshots for a subset of provinces, not a comparable annual national series.",
         "", "", "", "", ""],
    ]
    return pd.DataFrame(rows, columns=cols)


def readme_frame() -> pd.DataFrame:
    rows = [
        ("Workbook", "Canada's three main house-price index families, pulled from source."),
        ("Pull date", PULL_DATE),
        ("", ""),
        ("SHEET: Teranet_NB", "Teranet-National Bank HPI. Method: REPEAT-SALES (matched resale pairs)."),
        ("  source", "housepriceindex.ca public JSON (decoded); no API key."),
        ("  coverage", "Composite 11 + its 11 metropolitan areas (CMAs). Monthly."),
        ("  columns", "index_nsa, index_sa (seasonally adj.), mom_pct_nsa, yoy_pct_nsa. Base Jun 2005 = 100."),
        ("", ""),
        ("SHEET: CREA_MLS_HPI", "CREA MLS HPI. Method: HEDONIC / BENCHMARK (quality-adjusted benchmark home)."),
        ("  source", "crea.ca MLS_HPI monthly zip (Seasonally Adjusted). No API key."),
        ("  coverage", "National aggregate + 9 provinces (Manitoba has no province-level CREA series). 6 property types. Monthly."),
        ("  columns", "index_sa, benchmark_cad_sa ($), mom_pct, yoy_pct. Base Jan 2005 = 100."),
        ("", ""),
        ("SHEET: StatCan_Assessment", "StatCan Property Values. Method: APPRAISAL / ASSESSMENT based."),
        ("  source", "StatCan WDS table 34-10-0013 'Residential property values' (record #5191 vintage)."),
        ("  coverage", "Canada + provinces/territories. ANNUAL. Total residential assessment value ($ millions)."),
        ("  caveat", "Public table ends 2015 (program #5191 discontinued ~2016). Aggregate STOCK value: reflects price AND volume (new construction), not a pure price index."),
        ("  extension", "Rows after 2015 are a provincial-authority extension: Alberta residential equalized assessment (2024-2026, market-audited), summed from open.alberta.ca. Distinguished by the 'source' column. There is an Alberta 2016-2023 GAP (open portal exposes only recent years) and coverage is Alberta-only, because no other province offers a clean, comparable, scriptable annual total (see Provincial_Sources)."),
        ("", ""),
        ("SHEET: Provincial_Sources", "Roadmap to extend the appraisal pillar province-by-province: best source, format, coverage, and comparability caveats (Ontario frozen at 2016, NS capped, SK stepwise, differing base dates/units, territories unavailable)."),
        ("", ""),
        ("SHEET: Compare_National", "National headline of all three on a common axis (StatCan is annual)."),
        ("", ""),
        ("Methodology note", "Repeat-sales (Teranet), hedonic/benchmark (CREA) and appraisal (StatCan) measure different things; levels are not directly comparable, but growth rates are informative."),
        ("Comparability warning", "The appraisal/assessment pillar is NOT a clean pan-Canadian post-2015 series: provincial authorities differ in valuation base date, reassessment cadence, caps, and units. Treat the provincial extension as authority-specific, not as a continuation of the StatCan harmonized total."),
    ]
    return pd.DataFrame(rows, columns=["Item", "Description"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="reuse downloaded files")
    args = ap.parse_args()
    fetch = not args.no_fetch

    print("Building Canada housing indices workbook...")
    teranet = build_teranet(fetch)
    crea = build_crea(fetch)
    statcan = build_statcan(fetch)
    compare = build_compare(teranet, crea, statcan)

    with pd.ExcelWriter(OUT, engine="openpyxl", datetime_format="yyyy-mm-dd") as xw:
        readme_frame().to_excel(xw, sheet_name="README", index=False)
        teranet.to_excel(xw, sheet_name="Teranet_NB", index=False)
        crea.to_excel(xw, sheet_name="CREA_MLS_HPI", index=False)
        statcan.to_excel(xw, sheet_name="StatCan_Assessment", index=False)
        provincial_sources_frame().to_excel(xw, sheet_name="Provincial_Sources", index=False)
        compare.to_excel(xw, sheet_name="Compare_National", index=False)
        # widen a few columns for readability
        for name, sh in xw.sheets.items():
            sh.column_dimensions["A"].width = 22
            sh.column_dimensions["B"].width = 30
            if name == "Provincial_Sources":
                for col, w in zip("ABCDEFG", [20, 42, 30, 26, 30, 60, 60]):
                    sh.column_dimensions[col].width = w
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
