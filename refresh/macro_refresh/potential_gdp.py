"""
Potential GDP & Output Gap source.

Adds the "Potential GDP & Output Gap" sheet (US CBO potential GDP via FRED +
Canada output gap via BoC Valet) to the master workbook. Wraps the proven
`add_potential_gdp.py` logic.
"""
from __future__ import annotations

from . import config
from ._legacy import run_legacy_main

import add_potential_gdp as apg  # noqa: E402  (path wired up in config)


def run(target=None, offline=False, log=print) -> None:
    target = str(target or config.MASTER)
    apg.TARGET = target
    argv = ["add_potential_gdp", "--target", target]
    if offline:
        argv.append("--offline")
    log(f"Potential GDP / Output Gap -> {target}")
    run_legacy_main(apg.main, argv, log)


if __name__ == "__main__":
    run()
