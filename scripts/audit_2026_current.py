#!/usr/bin/env python3
"""Hard release gate for the September 12, 2026 current roster snapshot."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DATE = "2026-09-12"
TEAMS = [
    "Arizona Cardinals","Atlanta Falcons","Baltimore Ravens","Buffalo Bills","Carolina Panthers","Chicago Bears",
    "Cincinnati Bengals","Cleveland Browns","Dallas Cowboys","Denver Broncos","Detroit Lions","Green Bay Packers",
    "Houston Texans","Indianapolis Colts","Jacksonville Jaguars","Kansas City Chiefs","Las Vegas Raiders",
    "Los Angeles Chargers","Los Angeles Rams","Miami Dolphins","Minnesota Vikings","New England Patriots",
    "New Orleans Saints","New York Giants","New York Jets","Philadelphia Eagles","Pittsburgh Steelers",
    "San Francisco 49ers","Seattle Seahawks","Tampa Bay Buccaneers","Tennessee Titans","Washington Commanders",
]
ROOMS = {"QB","RB","FB","WR","TE","OT","G","C","EDGE","DT","LB","CB","S","K","P","LS"}
TEAM_ABBR = {
    "Arizona Cardinals":"ARI","Atlanta Falcons":"ATL","Baltimore Ravens":"BAL","Buffalo Bills":"BUF",
    "Carolina Panthers":"CAR","Chicago Bears":"CHI","Cincinnati Bengals":"CIN","Cleveland Browns":"CLE",
    "Dallas Cowboys":"DAL","Denver Broncos":"DEN","Detroit Lions":"DET","Green Bay Packers":"GB",
    "Houston Texans":"HOU","Indianapolis Colts":"IND","Jacksonville Jaguars":"JAX","Kansas City Chiefs":"KC",
    "Las Vegas Raiders":"LV","Los Angeles Chargers":"LAC","Los Angeles Rams":"LAR","Miami Dolphins":"MIA",
    "Minnesota Vikings":"MIN","New England Patriots":"NE","New Orleans Saints":"NO","New York Giants":"NYG",
    "New York Jets":"NYJ","Philadelphia Eagles":"PHI","Pittsburgh Steelers":"PIT","San Francisco 49ers":"SF",
    "Seattle Seahawks":"SEA","Tampa Bay Buccaneers":"TB","Tennessee Titans":"TEN","Washington Commanders":"WAS",
}


def norm(value):
    return "".join(c for c in str(value or "").lower() if c.isalnum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(ROOT / "dist/data/offline-data.json"))
    ap.add_argument("--manifest", default=str(ROOT / "dist/data/roster-2026-source-manifest.json"))
    args = ap.parse_args()

    bundle = json.loads(Path(args.file).read_text(encoding="utf-8"))
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    errors = []
    checks = 0

    year = (bundle.get("years") or {}).get("2026")
    if not year:
        raise SystemExit("2026 CURRENT AUDIT: missing 2026 pack")
    checks += 4
    if year.get("rosterSeason") != 2026: errors.append(f"2026 rosterSeason is {year.get('rosterSeason')}, expected 2026")
    if year.get("snapshotDate") != SNAPSHOT_DATE: errors.append(f"2026 snapshotDate is {year.get('snapshotDate')}, expected {SNAPSHOT_DATE}")
    if year.get("snapshotType") != "current": errors.append("2026 snapshotType is not current")
    if manifest.get("snapshotDate") != SNAPSHOT_DATE: errors.append("2026 source manifest snapshot date mismatch")

    teams = year.get("teams") or {}
    mteams = manifest.get("teams") or {}
    checks += 2
    if set(teams) != set(TEAMS): errors.append("2026 team set is not exactly all 32 NFL teams")
    if set(mteams) != set(TEAMS): errors.append("2026 source manifest is not exactly all 32 NFL teams")

    league_owners = defaultdict(list)
    total = 0
    for team in TEAMS:
        td = teams.get(team) or {}
        md = mteams.get(team) or {}
        roster = td.get("roster") or []
        source_names = md.get("officialNames") or []
        checks += 8
        if td.get("rosterSeason") != 2026: errors.append(f"{team}: rosterSeason is not 2026")
        if td.get("snapshotDate") != SNAPSHOT_DATE: errors.append(f"{team}: snapshotDate mismatch")
        if td.get("snapshotType") != "current": errors.append(f"{team}: snapshotType is not current")
        if not str(md.get("membership") or "").startswith("https://www.nfl.com/"): errors.append(f"{team}: missing NFL.com membership source")
        if len(roster) < 45: errors.append(f"{team}: only {len(roster)} roster rows")
        if len(roster) > 100: errors.append(f"{team}: implausible {len(roster)} roster rows")
        if not source_names: errors.append(f"{team}: no official source names recorded")
        if len(source_names) != len(set(map(norm, source_names))): errors.append(f"{team}: duplicate names in official membership source")

        actual = {norm(p.get("full_name") or p.get("display_name")): p for p in roster}
        expected = {norm(name): name for name in source_names}
        checks += len(roster) * 7 + len(source_names)
        if set(actual) != set(expected):
            missing = sorted(expected[k] for k in set(expected) - set(actual))
            extra = sorted((actual[k].get("full_name") or k) for k in set(actual) - set(expected))
            errors.append(f"{team}: exact NFL.com membership mismatch; missing={missing[:10]} extra={extra[:10]}")

        rooms = defaultdict(list)
        for key, p in actual.items():
            name = p.get("full_name") or p.get("display_name") or ""
            league_owners[key].append(team)
            if not name: errors.append(f"{team}: unnamed player")
            if str(p.get("team") or "").upper() != TEAM_ABBR[team]: errors.append(f"{team} {name}: embedded team={p.get('team')} expected {TEAM_ABBR[team]}")
            pos = str(p.get("position") or "").upper()
            group = str(p.get("room_group") or "").upper()
            if not pos or pos == "OTHER": errors.append(f"{team} {name}: unresolved position {pos!r}")
            if group not in ROOMS: errors.append(f"{team} {name}: invalid room_group {group!r}")
            if group == "OTHER": errors.append(f"{team} {name}: OTHER room is forbidden in current 2026")
            order = p.get("room_order")
            if not isinstance(order, int) or order < 1: errors.append(f"{team} {name}: invalid room_order {order}")
            rooms[group].append(p)

        for group, ps in rooms.items():
            checks += len(ps) + 1
            ranks = sorted(int(p["room_order"]) for p in ps)
            expected_ranks = list(range(1, len(ps) + 1))
            if ranks != expected_ranks: errors.append(f"{team} {group}: non-sequential ranks {ranks}")
        total += len(roster)

    for key, owners in league_owners.items():
        checks += 1
        if len(set(owners)) != 1:
            errors.append(f"2026 duplicate player identity {key}: {sorted(set(owners))}")

    # Explicit regressions from user-reported failures and current NFL.com source truth.
    lions = {norm(p.get("full_name")): p for p in (teams.get("Detroit Lions") or {}).get("roster", [])}
    texans = {norm(p.get("full_name")): p for p in (teams.get("Houston Texans") or {}).get("roster", [])}
    checks += 4
    if norm("David Montgomery") in lions: errors.append("David Montgomery incorrectly remains on Detroit in current 2026")
    if norm("David Montgomery") not in texans: errors.append("David Montgomery missing from Houston in current 2026")
    if norm("Isiah Pacheco") not in lions: errors.append("Isiah Pacheco missing from Detroit in current 2026")
    if norm("Isiah Pacheco") in texans: errors.append("Isiah Pacheco incorrectly appears on Houston in current 2026")

    print(f"2026 CURRENT AUDIT: {checks:,} checks; {total} roster rows; {len(league_owners)} unique player identities; {len(errors)} errors")
    for error in errors:
        print("ERROR", error)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
