#!/usr/bin/env python3
"""Direct live-source release gate for the current 2026 roster section."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import build_data as b
import rebuild_2026_current as cur

ROOT = Path(__file__).resolve().parents[1]
ROOMS = {"QB","RB","FB","WR","TE","OT","G","C","EDGE","DT","LB","CB","S","K","P","LS"}


def norm(v):
    return b.norm_name(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(ROOT / "dist/data/offline-data.json"))
    args = ap.parse_args()
    bundle = json.loads(Path(args.file).read_text(encoding="utf-8"))
    year = (bundle.get("years") or {}).get("2026") or {}
    teams = year.get("teams") or {}
    errors: list[str] = []
    checks = 0
    league = defaultdict(list)
    total = 0

    checks += 3
    if year.get("rosterSeason") != 2026: errors.append("2026 year pack is not based on 2026 roster data")
    if year.get("snapshotDate") != cur.SNAPSHOT_DATE: errors.append(f"2026 snapshot date is not {cur.SNAPSHOT_DATE}")
    if year.get("snapshotType") != "current": errors.append("2026 year pack is not labeled current")

    for team in b.TEAMS:
        td = teams.get(team)
        if not td:
            errors.append(f"{team}: missing team pack"); continue
        _, official_names = cur.nfl_membership(team)
        _, nfl_meta = cur.nfl_roster_metadata(team, official_names)
        roster = td.get("roster") or []
        expected = {norm(n): n for n in official_names}
        actual = {norm(p.get("full_name") or p.get("display_name")): p for p in roster}
        checks += 8 + len(expected) + len(actual) * 8

        if td.get("rosterSeason") != 2026: errors.append(f"{team}: rosterSeason is not 2026")
        if td.get("snapshotDate") != cur.SNAPSHOT_DATE: errors.append(f"{team}: snapshot date mismatch")
        if td.get("snapshotType") != "current": errors.append(f"{team}: snapshotType is not current")
        if len(roster) < 45: errors.append(f"{team}: only {len(roster)} current roster rows")
        if len(roster) > 100: errors.append(f"{team}: implausible {len(roster)} current roster rows")
        if len(actual) != len(roster): errors.append(f"{team}: duplicate player names inside roster")
        if set(actual) != set(expected):
            missing = [expected[k] for k in sorted(set(expected)-set(actual))]
            extra = [actual[k].get("full_name") for k in sorted(set(actual)-set(expected))]
            errors.append(f"{team}: NFL.com membership mismatch; missing={missing[:12]} extra={extra[:12]}")
        if len(nfl_meta) < max(40, int(len(expected) * .75)):
            errors.append(f"{team}: NFL.com position metadata only matched {len(nfl_meta)}/{len(expected)} players")

        rooms = defaultdict(list)
        for nk, player in actual.items():
            name = player.get("full_name") or expected.get(nk) or nk
            league[nk].append(team)
            pos = str(player.get("position") or "").upper()
            group = str(player.get("room_group") or "").upper()
            if not pos or pos == "OTHER": errors.append(f"{team} {name}: unresolved position")
            if group not in ROOMS: errors.append(f"{team} {name}: invalid room {group!r}")
            order = player.get("room_order")
            if not isinstance(order, int) or order < 1: errors.append(f"{team} {name}: invalid room_order {order}")
            if str(player.get("team") or "").upper() != b.BASE_ABBR[team]:
                errors.append(f"{team} {name}: embedded team {player.get('team')} does not match")

            src = nfl_meta.get(nk)
            if src:
                src_pos = b.canonical_pos(src.get("position"))
                site_pos = b.canonical_pos(pos)
                # NFL may use broad DB; allow a more specific CB/S site label in that case.
                if src_pos == "DB":
                    if b.group_for_pos(site_pos) not in {"CB","S"}: errors.append(f"{team} {name}: position {site_pos} disagrees with NFL DB")
                elif src_pos != "OTHER" and site_pos != src_pos:
                    errors.append(f"{team} {name}: position {site_pos} != NFL.com {src_pos}")
            rooms[group].append(player)

        for group, players in rooms.items():
            ranks = sorted(int(p.get("room_order") or 999) for p in players)
            checks += len(players) + 1
            if ranks != list(range(1, len(players)+1)):
                errors.append(f"{team} {group}: room ranks are not exactly sequential")
        total += len(roster)

    for nk, owners in league.items():
        checks += 1
        if len(set(owners)) > 1:
            errors.append(f"player {nk} appears on multiple 2026 teams: {sorted(set(owners))}")

    lions = {norm(p.get("full_name")) for p in (teams.get("Detroit Lions") or {}).get("roster", [])}
    texans = {norm(p.get("full_name")) for p in (teams.get("Houston Texans") or {}).get("roster", [])}
    checks += 4
    if norm("David Montgomery") in lions: errors.append("David Montgomery still incorrectly appears on Detroit")
    if norm("David Montgomery") not in texans: errors.append("David Montgomery is missing from Houston")
    if norm("Isiah Pacheco") not in lions: errors.append("Isiah Pacheco is missing from Detroit")
    if norm("Isiah Pacheco") in texans: errors.append("Isiah Pacheco incorrectly appears on Houston")

    print(f"2026 LIVE NFL AUDIT: {checks:,} checks; {total} roster rows; {len(league)} unique names; {len(errors)} errors")
    for e in errors:
        print("ERROR", e)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
