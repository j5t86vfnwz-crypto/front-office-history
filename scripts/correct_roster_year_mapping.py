#!/usr/bin/env python3
"""Move each historical roster snapshot onto the season year it actually represents.

The legacy builder labeled year Y with rosterSeason Y-1. Because the bundle already
contains consecutive years, the roster sitting under Y+1 is exactly the roster for Y.
This pass corrects 2010-2025 without disturbing each year's draft/free-agency/pick data.
2026 is rebuilt separately from live 2026 NFL sources later in the workflow.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--start", type=int, default=2010)
    parser.add_argument("--end", type=int, default=2025)
    args = parser.parse_args()

    path = Path(args.file)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    years = bundle.get("years") or {}
    original = copy.deepcopy(years)
    moved = 0

    for year in range(args.start, args.end + 1):
        target = years.get(str(year))
        source = original.get(str(year + 1))
        if not target or not source:
            raise RuntimeError(f"cannot correct {year}: missing target/source year pack")
        source_teams = source.get("teams") or {}
        target_teams = target.get("teams") or {}
        if set(source_teams) != set(target_teams):
            raise RuntimeError(f"{year}: source/target team sets differ")

        for team, target_team in target_teams.items():
            source_team = source_teams[team]
            target_team["roster"] = copy.deepcopy(source_team.get("roster") or [])
            target_team["rosterSeason"] = year
            target_team.pop("snapshotDate", None)
            target_team.pop("snapshotType", None)
            moved += 1

        target["rosterSeason"] = year
        target.pop("snapshotDate", None)
        target.pop("snapshotType", None)
        target["rosterLabel"] = f"{year} season roster"

    text = json.dumps(bundle, separators=(",", ":"), ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    path.with_suffix(".js").write_text("window.FOH_OFFLINE_BUNDLE=" + text + ";\n", encoding="utf-8")
    print(f"ROSTER YEAR MAPPING: corrected {moved} team snapshots across {args.start}-{args.end}")


if __name__ == "__main__":
    main()
