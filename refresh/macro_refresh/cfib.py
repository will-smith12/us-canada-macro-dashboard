"""
CFIB Business Barometer source.

Downloads the latest monthly CFIB workbook (via curl, which uses the system CA
store — the legacy urllib path fails TLS verification on this Python build) and
wires the "CFIB Barometer" and "CFIB Barometer (Tidy)" sheets into the master
workbook via the proven `cfib_to_master.py` logic.
"""
from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path

from . import config
from ._legacy import run_legacy_main

import cfib_refresh as cr      # noqa: E402  (path wired up in config)
import cfib_to_master as c2m   # noqa: E402


def _curl(url: str, dest: Path) -> bool:
    try:
        subprocess.run(["curl", "-sL", "--fail", "-o", str(dest), url],
                       check=True, timeout=120)
        return dest.exists() and dest.read_bytes()[:2] == b"PK"
    except Exception:
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def _fetch_latest(log, lookback: int = 6) -> Path | None:
    """Find the newest published CFIB monthly workbook by walking months back."""
    today = dt.date.today().replace(day=1)
    y, m = today.year, today.month
    for _ in range(lookback):
        url = cr.build_url(y, m)
        dest = config.DOWNLOADS / f"CFIB_MBB-data-{y}-{m:02d}.xlsx"
        if dest.exists() and dest.read_bytes()[:2] == b"PK":
            log(f"  using cached {dest.name}")
            return dest
        if _curl(url, dest):
            log(f"  downloaded {dest.name}")
            return dest
        log(f"  miss {y}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return None


def _newest_local(log) -> Path | None:
    files = sorted(config.DOWNLOADS.glob("CFIB_MBB-data-*.xlsx"))
    if files:
        log(f"  falling back to local {files[-1].name}")
        return files[-1]
    return None


def run(target=None, source=None, log=print) -> None:
    target = str(target or config.MASTER)
    src = Path(source) if source else (_fetch_latest(log) or _newest_local(log))
    if not src:
        raise RuntimeError("No CFIB source workbook available (download failed, no local file).")

    c2m.TARGET = target
    log(f"CFIB ({src.name}) -> {target}")
    run_legacy_main(c2m.main, ["cfib_to_master", "--target", target, "--source", str(src)], log)


if __name__ == "__main__":
    run()
