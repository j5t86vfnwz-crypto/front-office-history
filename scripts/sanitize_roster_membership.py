#!/usr/bin/env python3
"""Resolve impossible cross-team duplicate roster memberships.

The historical builder may use depth charts as a fallback when roster exports are
incomplete. A depth-chart fallback is evidence about role, not stronger evidence
of membership than an actual roster/weekly row. This pass makes that distinction
explicit and guarantees one roster membership per player per offseason pack.
"""
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


def candidate_score(team, player):
    status = str(player.get("status") or "").upper()
    non_depth = 1 if status != "DEPTH" else 0
    status_rank = {
        "ACT": 8,
        "RES": 7,
        "IR": 7,
        "PUP": 7,
        "NFI": 7,
        "SUS": 6,
        "DEV": 5,
        "INA": 4,
        "TRC": 3,
        "TRD": 3,
        "TRT": 3,
        "CUT": 2,
        "UFA": 1,
        "RFA": 1,
        "ERFA": 1,
        "DEPTH": 0,
    }.get(status, 2)
    return (
        non_depth,
        status_rank,
        float(player.get("_depth_presence") or 0),
        float(player.get("_starter_rate") or 0),
        float(player.get("_role_score") or 0),
        -int(player.get("_officialDepthTier") or 99),
        -int(player.get("room_order") or 999),
        team,
    )


def sanitize_year(year_data):
    teams = year_data.get("teams") or {}
    appearances = defaultdict(list)
    for team, team_data in teams.items():
        for index, player in enumerate(team_data.get("roster") or []):
            key = identity(player)
            if key:
                appearances[key].append((team, index, player))

    remove = defaultdict(set)
    resolved = 0
    for items in appearances.values():
        if len({team for team, _, _ in items}) <= 1:
            continue
        winner_team, winner_index, _ = max(
            items, key=lambda item: candidate_score(item[0], item[2])
        )
        for team, index, _ in items:
            if team != winner_team or index != winner_index:
                remove[team].add(index)
        resolved += 1

    removed = 0
    for team, team_data in teams.items():
        roster = team_data.get("roster") or []
        if team in remove:
            cleaned = [p for i, p in enumerate(roster) if i not in remove[team]]
            removed += len(roster) - len(cleaned)
        else:
            cleaned = roster

        rooms = defaultdict(list)
        for player in cleaned:
            rooms[player.get("room_group") or "OTHER"].append(player)
        for room in rooms.values():
            room.sort(
                key=lambda p: (
                    int(p.get("room_order") or 999),
                    str(p.get("full_name") or ""),
                )
            )
            for rank, player in enumerate(room, 1):
                player["room_order"] = rank
                player["_officialRoomOrder"] = rank
        team_data["roster"] = cleaned

    return resolved, removed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args = parser.parse_args()

    path = Path(args.file)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    resolved = removed = 0
    for year_data in (bundle.get("years") or {}).values():
        r, m = sanitize_year(year_data)
        resolved += r
        removed += m

    text = json.dumps(bundle, separators=(",", ":"), ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    path.with_suffix(".js").write_text(
        "window.FOH_OFFLINE_BUNDLE=" + text + ";\n", encoding="utf-8"
    )
    print(
        f"ROSTER MEMBERSHIP SANITIZER: resolved {resolved} cross-team duplicates; "
        f"removed {removed} duplicate rows"
    )


if __name__ == "__main__":
    main()
