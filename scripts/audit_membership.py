#!/usr/bin/env python3
"""Hard-fail impossible cross-team roster memberships in every season pack."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def norm(value):
    return "".join(c for c in str(value or "").lower() if c.isalnum())


def identity(player):
    # Prefer stable IDs so different NFL players with the same name are not merged.
    stable = player.get("gsis_id") or player.get("pfr_id") or player.get("espn_id")
    if stable:
        return f"id:{stable}"
    # Fallback is deliberately more specific than name-only.
    return f"fallback:{norm(player.get('full_name') or player.get('display_name'))}:{str(player.get('position') or '').upper()}"


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--file",required=True);args=parser.parse_args()
    bundle=json.loads(Path(args.file).read_text(encoding="utf-8"));errors=[];checks=0

    for year,year_data in sorted((bundle.get("years") or {}).items()):
        appearances=defaultdict(list)
        expected_year=int(year)
        if year_data.get("rosterSeason") != expected_year:
            errors.append(f"{year}: year pack rosterSeason={year_data.get('rosterSeason')} expected {expected_year}")
        for team,team_data in (year_data.get("teams") or {}).items():
            checks+=1
            if team_data.get("rosterSeason") != expected_year:
                errors.append(f"{year} {team}: rosterSeason={team_data.get('rosterSeason')} expected {expected_year}")
            for player in team_data.get("roster") or []:
                checks+=1;key=identity(player)
                if key:appearances[key].append((team,player.get("full_name") or player.get("display_name") or key))
        for key,items in appearances.items():
            teams=sorted({team for team,_ in items});checks+=1
            if len(teams)>1:
                errors.append(f"{year} {items[0][1]}: same player identity appears on multiple teams: {', '.join(teams)}")

    print(f"MEMBERSHIP AUDIT: {checks:,} checks; {len(errors)} errors")
    for error in errors:print("ERROR",error)
    if errors:raise SystemExit(1)

if __name__=="__main__":main()
