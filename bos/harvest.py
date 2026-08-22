#!/usr/bin/env python3
"""Harvest BoC Business Outlook Survey (BOS) sector/region chart data from the Valet API.

Stages (run via subcommands):
  enumerate  -> list BOS-related Valet groups
  fetch      -> download observations-by-group JSON for each candidate (cached)
  build      -> classify + assemble the xlsx workbook

Data source: https://www.bankofcanada.ca/valet  (public, no key).
"""
import json
import os
import re
import subprocess
import sys
import time

BASE = "https://www.bankofcanada.ca/valet"
WORK = os.environ.get("BOS_WORK") or os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(WORK, "cache")
GROUPS_JSON = os.path.join(WORK, "groups_all.json")
CANDIDATES_JSON = os.path.join(WORK, "candidates.json")
UA = "Mozilla/5.0 (macOS; data-harvest; contact: local script)"


def _get(url, tries=3, pause=0.5):
    """Fetch JSON via curl (system CA trusts the corporate proxy root; Python's does not)."""
    last = None
    for i in range(tries):
        try:
            out = subprocess.run(
                ["curl", "-sS", "--fail", "--max-time", "60", "-A", UA, url],
                capture_output=True, text=True,
            )
            if out.returncode != 0:
                raise RuntimeError(f"curl rc={out.returncode}: {out.stderr.strip()[:200]}")
            return json.loads(out.stdout)
        except (RuntimeError, json.JSONDecodeError) as e:
            last = e
            time.sleep(pause * (i + 1))
    raise last


def is_bos_group(code, label, desc):
    c = code.lower()
    if c == "bos" or c.startswith("bos_") or c.startswith("bosbg") or c.startswith("bosdatapage"):
        return True
    blob = f"{label} {desc}".lower()
    return "business outlook survey" in blob


def enumerate_groups():
    data = _get(f"{BASE}/lists/groups/json")
    groups = data.get("groups", {})
    with open(GROUPS_JSON, "w") as f:
        json.dump(groups, f)
    cands = []
    for code, meta in groups.items():
        label = (meta or {}).get("label", "") or ""
        desc = (meta or {}).get("description", "") or ""
        if is_bos_group(code, label, desc):
            cands.append({"code": code, "label": label, "description": desc})
    cands.sort(key=lambda x: x["code"])
    with open(CANDIDATES_JSON, "w") as f:
        json.dump(cands, f, indent=2)
    print(f"total groups: {len(groups)}")
    print(f"BOS candidate groups: {len(cands)}")
    for c in cands:
        print(f"  {c['code']:<28} | {c['label'][:80]}")
    return cands


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "enumerate"
    if cmd == "enumerate":
        enumerate_groups()
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(2)
