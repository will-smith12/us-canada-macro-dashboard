#!/usr/bin/env python3
"""
macro_refresh orchestrator — weekly refresh of master_economics_data.xlsx.

Pipelines (run in this order; each isolated so one failure won't abort the rest):

  1. te        Trading Economics (headless website scrape) — rebuilds the base
               workbook: Summary + category sheets + key-indicator sheets.
  2. fredboc   FRED + Bank of Canada (Valet) sheets.
  3. cfib      CFIB Business Barometer sheets.
  4. potgdp    Potential GDP & Output Gap sheet.

Because step 1 rebuilds the workbook from scratch, a full refresh runs all four
in order. Individual pipelines can be run with --only / --skip (they append to
the existing master).

Examples:
    python3 -m macro_refresh.refresh                 # full weekly refresh
    python3 -m macro_refresh.refresh --te-scope key  # faster TE (key indicators only)
    python3 -m macro_refresh.refresh --only fredboc  # just refresh FRED/BoC
    python3 -m macro_refresh.refresh --skip te       # keep TE sheets, refresh the rest
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

from . import config, te_scrape, fred_boc, cfib, potential_gdp

PIPELINES = ["te", "fredboc", "cfib", "potgdp"]


class Logger:
    def __init__(self, log_path: Path):
        self.fh = open(log_path, "a", buffering=1)

    def __call__(self, msg: str = "") -> None:
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {msg}"
        # Use the real stdout so this never recurses into a redirect_stdout()
        # forwarder installed while a legacy main() is running.
        print(line, file=sys.__stdout__)
        self.fh.write(line + "\n")

    def close(self):
        self.fh.close()


def backup(master: Path, log) -> None:
    if not master.exists():
        log("No existing workbook to back up (will be created).")
        return
    stamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    dest = master.with_name(f"{master.stem}.BACKUP-{stamp}{master.suffix}")
    shutil.copy2(master, dest)
    log(f"Backup written -> {dest.name}")


def lock_present(master: Path) -> bool:
    return (master.parent / f"~${master.name}").exists()


def run(selected, te_scope, do_backup, target, log, backfill=True) -> dict:
    results = {}

    if do_backup:
        backup(target, log)

    runners = {
        "te": lambda: te_scrape.run(target=target, scope=te_scope, log=log,
                                    backfill=backfill),
        "fredboc": lambda: fred_boc.run(target=target, log=log),
        "cfib": lambda: cfib.run(target=target, log=log),
        "potgdp": lambda: potential_gdp.run(target=target, log=log),
    }

    for name in PIPELINES:
        if name not in selected:
            continue
        log("")
        log(f"########## pipeline: {name} ##########")
        try:
            runners[name]()
            results[name] = "ok"
            log(f"pipeline {name}: OK")
        except (Exception, SystemExit) as e:  # isolate failures incl. legacy sys.exit()
            import traceback
            results[name] = f"FAILED: {e}"
            log(f"pipeline {name}: FAILED — {e!r}")
            for ln in traceback.format_exc().splitlines():
                log("    " + ln)
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", choices=PIPELINES,
                    help="Run only these pipelines.")
    ap.add_argument("--skip", nargs="+", choices=PIPELINES, default=[],
                    help="Skip these pipelines.")
    ap.add_argument("--te-scope", choices=["full", "key"], default="full",
                    help="TE scrape breadth: full (all in-scope indicators) or key.")
    ap.add_argument("--no-backfill", action="store_true",
                    help="Skip FRED/BoC/StatCan backfill of missing/truncated TE indicators.")
    ap.add_argument("--no-backup", action="store_true",
                    help="Skip the pre-run timestamped backup.")
    ap.add_argument("--target", default=str(config.MASTER),
                    help="Workbook path (defaults to the configured master).")
    args = ap.parse_args(argv)

    target = Path(args.target)
    selected = set(args.only) if args.only else set(PIPELINES)
    selected -= set(args.skip)

    log_path = config.LOG_DIR / f"refresh-{dt.datetime.now():%Y%m%d-%H%M%S}.log"
    log = Logger(log_path)

    started = dt.datetime.now()
    log(f"=== macro_refresh start {started:%Y-%m-%d %H:%M:%S} ===")
    log(f"target   : {target}")
    log(f"pipelines: {[p for p in PIPELINES if p in selected]}")
    log(f"te-scope : {args.te_scope}")
    log(f"log file : {log_path}")

    if lock_present(target):
        log(f"ABORT: {target.name} appears open in Excel (lock file present). Close it and retry.")
        log.close()
        return 2

    try:
        results = run(selected, args.te_scope, not args.no_backup, target, log,
                      backfill=not args.no_backfill)
    finally:
        pass

    elapsed = dt.datetime.now() - started
    log("")
    log("=== summary ===")
    for name in PIPELINES:
        if name in selected:
            log(f"  {name:8s}: {results.get(name, 'not run')}")
    failed = [n for n, r in results.items() if r != "ok"]
    log(f"elapsed: {elapsed}")
    log(f"=== macro_refresh done ({'FAILURES' if failed else 'all OK'}) ===")
    log.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
