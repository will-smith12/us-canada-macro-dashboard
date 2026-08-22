"""
Backfill layer for the Trading Economics scrape.

Some TE indicators scrape *missing* or *truncated* (the encrypted CloudFront
chart only ever exposes a short window for them). For a curated set of those
gaps we substitute full-history data from authoritative **free** providers
(FRED, Bank of Canada Valet, StatCan WDS) at the data layer, *before* the
workbook builders run. The existing builders then emit complete category and
key-indicator sheets exactly as if TE had served the full series.

The registry below IS the curated gap list (from `te_coverage_diag.py`), so the
substitution is deterministic — we always source these from their mapped
provider rather than trying to detect truncation at runtime.

Disable with `--no-backfill` (te_scrape) or `backfill=False`.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

import requests

from . import config

# Reuse the proven FRED/BoC fetchers (FRED key is overridden from config).
import fetch_fred_boc as ffb  # noqa: E402  (path wired up in config)

ffb.FRED_KEY = config.FRED_API_KEY

STATCAN_URL = ("https://www150.statcan.gc.ca/t1/wds/rest/"
               "getDataFromVectorsAndLatestNPeriods")
STATCAN_CPI_VECTOR = 41690973  # CPI, all-items, Canada (fresher than FRED's OECD series)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SourceSpec:
    provider: str                     # 'fred' | 'boc' | 'statcan' | 'splice'
    code: object                      # series id, valet code, vector, or list (splice)
    units: str = "lin"                # FRED transform: lin | pc1 (YoY%) | pch (MoM%) | chg
    scale: float = 1.0                # multiply provider values to match TE's stated unit
    transform: Optional[str] = None   # statcan local transform: 'yoy' | 'mom' | None
    note: str = ""

    @property
    def codes(self):
        return self.code if isinstance(self.code, list) else [self.code]


# (country, te_indicator_name) -> SourceSpec
REGISTRY: dict[tuple[str, str], SourceSpec] = {
    # ---- United States (FRED) ------------------------------------------- #
    ("US", "Inflation Rate"):
        SourceSpec("fred", "CPIAUCSL", units="pc1", note="CPI YoY %"),
    ("US", "Inflation Rate MoM"):
        SourceSpec("fred", "CPIAUCSL", units="pch", note="CPI MoM %"),
    ("US", "Interest Rate"):
        SourceSpec("splice", ["DFEDTAR", "DFEDTARU"],
                   note="Fed funds target: DFEDTAR(->2008) + DFEDTARU(2008->)"),
    ("US", "Effective Federal Funds Rate"):
        SourceSpec("fred", "DFF", note="daily effective fed funds"),
    ("US", "Government Bond 10Y"):
        SourceSpec("fred", "DGS10"),
    ("US", "Initial Jobless Claims"):
        SourceSpec("fred", "ICSA", scale=0.001, note="persons -> thousands"),
    ("US", "Continuing Jobless Claims"):
        SourceSpec("fred", "CCSA", scale=0.001, note="persons -> thousands"),
    ("US", "Jobless Claims 4-week Average"):
        SourceSpec("fred", "IC4WSA", scale=0.001, note="persons -> thousands"),
    ("US", "15 Year Mortgage Rate"):
        SourceSpec("fred", "MORTGAGE15US"),
    ("US", "30 Year Mortgage Rate"):
        SourceSpec("fred", "MORTGAGE30US"),
    ("US", "Mortgage Rate"):
        SourceSpec("fred", "MORTGAGE30US"),
    ("US", "Central Bank Balance Sheet"):
        SourceSpec("fred", "WALCL", note="USD millions (matches TE)"),
    ("US", "Job Vacancies"):
        SourceSpec("fred", "JTSJOL", note="JOLTS openings (thousands)"),
    ("US", "Factory Orders"):
        SourceSpec("fred", "AMTMNO", units="pch", note="MoM % change"),
    ("US", "Retail Trade Payrolls"):
        SourceSpec("fred", "USTRADE", units="chg", note="MoM change, thousands"),
    ("US", "Exports"):
        SourceSpec("fred", "BOPTEXP", scale=0.001, note="USD millions -> billions"),
    ("US", "Secured Overnight Financing Rate"):
        SourceSpec("fred", "SOFR"),

    # ---- Canada (Bank of Canada Valet) ---------------------------------- #
    ("CA", "Interest Rate"):
        SourceSpec("boc", "V39079", note="target overnight rate"),
    ("CA", "Government Bond 10Y"):
        SourceSpec("boc", "BD.CDN.10YR.DQ.YLD", note="GoC 10Y benchmark yield"),

    # ---- Canada (StatCan WDS) ------------------------------------------- #
    ("CA", "Inflation Rate"):
        SourceSpec("statcan", STATCAN_CPI_VECTOR, transform="yoy",
                   note="CPI all-items YoY %"),
    ("CA", "Inflation Rate MoM"):
        SourceSpec("statcan", STATCAN_CPI_VECTOR, transform="mom",
                   note="CPI all-items MoM %"),
    ("CA", "Capacity Utilization"):
        SourceSpec("statcan", 4331081, transform=None,
                   note="Total industrial capacity utilization rate, % (16-10-0109)"),

    # ---- United States — flaky-scrape indicators swapped to FRED -------- #
    # These scrape intermittently (empty chart) but have exact FRED equivalents.
    ("US", "Employment Rate"):
        SourceSpec("fred", "EMRATIO", note="employment-population ratio %"),
    ("US", "Energy Inflation"):
        SourceSpec("fred", "CPIENGNS", units="pc1",
                   note="CPI energy NSA YoY % (NSA matches TE; SA is ~0.5pp off)"),
    ("US", "Existing Home Sales"):
        SourceSpec("fred", "EXHOSLUSM495S", scale=0.001,
                   note="units -> thousands"),
    ("US", "Existing Home Sales MoM"):
        SourceSpec("fred", "EXHOSLUSM495S", units="pch", note="MoM %"),
    ("US", "Job Layoffs and Discharges"):
        SourceSpec("fred", "JTSLDL", note="JOLTS layoffs & discharges (thousands)"),
    ("US", "Job Offers"):
        SourceSpec("fred", "JTSJOL", note="JOLTS job openings (thousands)"),
    ("US", "Job Quits"):
        SourceSpec("fred", "JTSQUL", note="JOLTS quits (thousands)"),
    ("US", "Job Quits Rate"):
        SourceSpec("fred", "JTSQUR", note="JOLTS quits rate %"),
    ("US", "Retail Sales Ex Gas and Autos MoM"):
        SourceSpec("fred", "MARTSSM44W72USS", units="pch",
                   note="advance retail ex motor-vehicle & gasoline, MoM %"),
    ("US", "Retail Sales Food and Beverage Stores MoM"):
        SourceSpec("fred", "RSDBS", units="pch",
                   note="advance retail, food & beverage stores, MoM %"),
    ("US", "Retail Sales Furniture Stores MoM"):
        SourceSpec("fred", "RSFHFS", units="pch",
                   note="advance retail, furniture & home furnishings, MoM %"),
    ("US", "Retail Sales Gasoline Stations MoM"):
        SourceSpec("fred", "RSGASS", units="pch",
                   note="advance retail, gasoline stations, MoM %"),
    ("US", "Philly Fed CAPEX Index"):
        SourceSpec("fred", "CEFDFSA066MSFRBPHI",
                   note="Philly Fed future capital expenditures diffusion index, SA"),

    # ---- United States — transient MISSING_MINE scrape dropouts ---------- #
    # Same flaky-scrape pattern; exact free equivalents verified vs TE API.
    ("US", "Employment Cost Index Wages"):
        SourceSpec("fred", "CIS1020000000000I", units="pch",
                   note="ECI wages&salaries, All Civilian workers, SA, QoQ % "
                        "(All-Civilian matches TE; private ECIWAG is ~0.1pp off)"),
    ("US", "Retail Sales Ex Autos"):
        SourceSpec("fred", "RSFSXMV", units="pch",
                   note="advance retail ex motor-vehicle & parts, MoM %"),
    ("US", "Retail Sales ex Fuel"):
        SourceSpec("fred", "MARTSMPCSM44Z72USS",
                   note="advance retail ex gasoline stations, precomputed MoM %"),
    ("US", "Retail Sales Electronics Stores MoM"):
        SourceSpec("fred", "MARTSMPCSM443USS",
                   note="advance retail electronics & appliance, precomputed MoM %"),

    # ---- Canada — GDP by industry (StatCan 36-10-0434, level) ------------ #
    # Chained (2017) dollars, SAAR, CAD Million; raw level (transform=None).
    ("CA", "GDP from Mining"):
        SourceSpec("statcan", 65201236, transform=None,
                   note="GDP mining, quarrying & oil/gas extraction (36-10-0434)"),
    ("CA", "GDP from Public Administration"):
        SourceSpec("statcan", 65201476, transform=None,
                   note="GDP public administration (36-10-0434)"),
    ("CA", "GDP from Services"):
        SourceSpec("statcan", 65201212, transform=None,
                   note="GDP services-producing industries (36-10-0434)"),
    ("CA", "GDP from Transport"):
        SourceSpec("statcan", 65201381, transform=None,
                   note="GDP transportation & warehousing (36-10-0434)"),
}

# Indicators with no clean free source — documented, intentionally not filled.
OUT_OF_SCOPE = {
    "US": ["External Debt", "Factory Orders Ex Transportation",
           "Jobless Claims - Federal Workers", "Continued Claims - Federal Workers",
           "Kansas Fed Manufacturing Index", "Richmond Fed Manufacturing Index",
           "Retirement Age Men", "Retirement Age Women", "Challenger Job Cuts",
           "MBA Mortgage Market Index", "MBA Mortgage Refinance Index",
           "MBA Purchase Index", "Mortgage Applications", "Banks Balance Sheet",
           "Average Mortgage Size", "Stock Market", "Weekly Crude Oil Production",
           # ISM Services PMI sub-indices: proprietary, pulled from FRED over
           # licensing (no free FRED/BoC/StatCan equivalent) -> scrape-only.
           "ISM Non Manufacturing Employment", "ISM Non Manufacturing New Orders",
           "ISM Non Manufacturing Prices"],
    "CA": ["Government Spending", "Gross Average Monthly Wages",
           "Gross National Product", "Home Ownership Rate", "Stock Market",
           "Gross Fixed Capital Formation"],
}


# --------------------------------------------------------------------------- #
# Fetchers
# --------------------------------------------------------------------------- #
def _fred_pairs(series_id: str, units: str = "lin") -> list[tuple[str, float]]:
    obs = ffb.fred_obs(series_id, units=units)
    out = []
    for o in obs:
        v = ffb.to_num(o.get("value"))
        if v is not None:
            out.append((o["date"], v))
    out.sort(key=lambda p: p[0])
    return out


def _splice_pairs(codes: list[str], units: str = "lin") -> list[tuple[str, float]]:
    """Concatenate successive FRED series, earlier series first; later series wins overlaps."""
    merged: dict[str, float] = {}
    for sid in codes:
        for d, v in _fred_pairs(sid, units):
            merged[d] = v
    return sorted(merged.items(), key=lambda p: p[0])


def _boc_pairs(code: str) -> list[tuple[str, float]]:
    m = ffb.boc_observations([code], start="1980-01-01")
    return sorted(m.get(code, {}).items(), key=lambda p: p[0])


def _statcan_index(vector: int, n: int = 1200) -> list[tuple[str, float]]:
    r = requests.post(STATCAN_URL,
                      json=[{"vectorId": vector, "latestN": n}],
                      headers={"Content-Type": "application/json"},
                      timeout=60)
    r.raise_for_status()
    dp = r.json()[0]["object"]["vectorDataPoint"]
    out = []
    for p in dp:
        v = p.get("value")
        if v is not None:
            out.append((p["refPer"], float(v)))
    out.sort(key=lambda p: p[0])
    return out


def _statcan_pairs(vector: int, transform: str) -> list[tuple[str, float]]:
    idx = _statcan_index(vector)
    if transform is None:          # raw level series (e.g. a rate already in %)
        return idx
    lag = 12 if transform == "yoy" else 1
    out = []
    for i in range(lag, len(idx)):
        prev = idx[i - lag][1]
        if prev:
            out.append((idx[i][0], round((idx[i][1] / prev - 1.0) * 100.0, 4)))
    return out


def _fetch(spec: SourceSpec) -> list[tuple[str, float]]:
    if spec.provider == "fred":
        pairs = _fred_pairs(spec.code, spec.units)
    elif spec.provider == "splice":
        pairs = _splice_pairs(spec.code, spec.units)
    elif spec.provider == "boc":
        pairs = _boc_pairs(spec.code)
    elif spec.provider == "statcan":
        pairs = _statcan_pairs(spec.code, spec.transform)
    else:
        raise ValueError(f"unknown provider {spec.provider!r}")
    if spec.scale != 1.0:
        pairs = [(d, v * spec.scale) for d, v in pairs]
    return pairs


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def _refresh_latest_row(latest_rows, name, pairs) -> None:
    for row in latest_rows:
        if row.get("Category") != name:
            continue
        row["LatestValue"] = pairs[-1][1]
        row["LatestValueDate"] = pairs[-1][0]
        if len(pairs) >= 2:
            row["PreviousValue"] = pairs[-2][1]
            row["PreviousValueDate"] = pairs[-2][0]
        break


def backfill(us_hist, ca_hist, us_latest, ca_latest, log=print) -> None:
    """
    Overwrite the histories (and latest/previous fields) of the registered gap
    indicators with full-history provider data, in place.
    """
    targets = {"US": (us_hist, us_latest), "CA": (ca_hist, ca_latest)}
    filled = 0
    log(f"=== Backfilling {len(REGISTRY)} gap indicators from FRED / BoC / StatCan ===")
    for (country, name), spec in REGISTRY.items():
        hist, latest = targets[country]
        try:
            pairs = _fetch(spec)
        except Exception as e:  # noqa: BLE001 — never let a backfill failure abort the scrape
            log(f"    [{country}] {name}: backfill FAILED ({spec.provider} "
                f"{spec.code}): {e!r}")
            continue
        if not pairs:
            log(f"    [{country}] {name}: backfill returned no data ({spec.provider})")
            continue
        hist[name] = pairs
        _refresh_latest_row(latest, name, pairs)
        filled += 1
        log(f"    [{country}] {name}: {len(pairs)} pts "
            f"({pairs[0][0]}..{pairs[-1][0]}, latest={pairs[-1][1]:g}) "
            f"<- {spec.provider}:{spec.code}")
    log(f"=== Backfill complete: {filled}/{len(REGISTRY)} indicators filled ===")
