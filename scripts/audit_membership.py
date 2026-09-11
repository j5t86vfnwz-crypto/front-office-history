#!/usr/bin/env python3
"""Hard-fail impossible cross-team roster memberships in every offseason pack."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def norm(value):
    return "".join(c for c in str(value or "").lower() if c.isalnum())


def identity(player):
    return str(
        player.get("gsis_id")
        or player.get("pfr_id")
        or player.get("espn_id")
        or norm(player.get("full_name") or player.get("display_name"))
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args = parser.parse_args()

    bundle = json.loads(Path(args.file).read_text(encoding="utf-8"))
    errors = []
    checks = 0

    for year, year_data in sorted((bundle.get("years") or {}).items()):
        appearances = defaultdict(list)
        for team, team_data in (year_data.get("teams") or {}).items():
            for player in team_data.get("roster") or []:
                checks += 1
                key = identity(player)
                if key:
                    appearances[key].append(
                        (team, player.get("full_name") or player.get("display_name") or key)
                    )

        for key, items in appearances.items():
            teams = sorted({team for team, _ in items})
            checks += 1
            if len(teams) > 1:
                name = items[0][1]
                errors.append(
                    f"{year} {name}: appears on multiple teams: {', '.join(teams)}"
                )

    # 2026 is an opening-offseason replay snapshot. Montgomery's real trade to
    # Houston occurred after the opening snapshot, so he must never exist on both
    # Detroit and Houston in the starting roster data.
    y26 = (bundle.get("years") or {}).get("2026") or {}
    montgomery = []
    for team, team_data in (y26.get("teams") or {}).items():
        for player in team_data.get("roster") or []:
            if norm(player.get("full_name")) == norm("David Montgomery"):
                montgomery.append(team)
    checks += 1
    if montgomery != ["Detroit Lions"]:
        errors.append(
            f"2026 David Montgomery opening snapshot is {montgomery}, expected ['Detroit Lions']"
        )

    print(f"MEMBERSHIP AUDIT: {checks:,} checks; {len(errors)} errors")
    for error in errors:
        print("ERROR", error)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
