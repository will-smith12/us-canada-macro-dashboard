"""
FRED + Bank of Canada (Valet) source.

Appends/refreshes the FRED-vintage, US financial-conditions, SLOOS, commodity
and Canada (BoC) sheets in the master workbook. Wraps the proven
`fetch_fred_boc.py` logic, injecting the FRED key from config and targeting the
master path. BoC Valet needs no key.
"""
from __future__ import annotations

from . import config
from ._legacy import run_legacy_main

import fetch_fred_boc as ffb  # noqa: E402  (path wired up in config)


def run(target=None, log=print) -> None:
    target = str(target or config.MASTER)
    ffb.FRED_KEY = config.FRED_API_KEY
    ffb.WORKBOOK = target
    log(f"FRED+BoC -> {target}")
    run_legacy_main(ffb.main, ["fetch_fred_boc"], log)


if __name__ == "__main__":
    run()
