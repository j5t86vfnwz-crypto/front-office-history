#!/usr/bin/env python3
"""Build a source-consensus health report for the current 2026 NFL rosters.

NFL.com remains authoritative for membership. ESPN and nflverse are independent
cross-checks. This script never silently rewrites the official roster; it exposes
source disagreements so they can be reviewed instead of hidden.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import build_data as b
import rebuild_2026_current as cur

ROOT = Path(__file__).resolve().parents[1]


def names_from_espn(team: str) -> set[str]:
    _, meta = cur.espn_metadata(team)
    return set(meta)


def names_from_nflverse(team: str, current, master_idx) -> set[str]:
    index = cur.nflverse_index(current, master_idx)
    return {nk for (t, nk) in index if t == team}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist/data/roster-source-health.json"))
    args = ap.parse_args()

    master = b.read_csv_url(b.URLS["players"], "players.csv")
    master_idx = b.build_master_index(master)
    current = b.download_season_dataset(2026)

    report = {
        "season": 2026,
        "snapshotDate": cur.SNAPSHOT_DATE,
        "authority": "NFL.com team roster membership",
        "crossChecks": ["ESPN current roster", "nflverse 2026 roster/weekly"],
        "teams": {},
        "summary": {},
    }

    total_official = total_supported_both = total_unsupported = 0
    teams_with_disagreements = 0

    for team in b.TEAMS:
        _, official_names = cur.nfl_membership(team)
        official = {b.norm_name(n): n for n in official_names}
        espn = names_from_espn(team)
        nv = names_from_nflverse(team, current, master_idx)

        unsupported = sorted(
            official[k] for k in official if k not in espn and k not in nv
        )
        espn_only = sorted(k for k in espn if k not in official)
        nflverse_only = sorted(k for k in nv if k not in official)
        supported_both = sum(1 for k in official if k in espn and k in nv)
        supported_one = sum(1 for k in official if (k in espn) ^ (k in nv))

        if unsupported or espn_only or nflverse_only:
            teams_with_disagreements += 1

        report["teams"][team] = {
            "officialCount": len(official),
            "espnCount": len(espn),
            "nflverseCount": len(nv),
            "officialSupportedByBoth": supported_both,
            "officialSupportedByOne": supported_one,
            "officialUnsupportedBySecondarySources": unsupported,
            "espnOnlyNormalizedNames": espn_only,
            "nflverseOnlyNormalizedNames": nflverse_only,
        }
        total_official += len(official)
        total_supported_both += supported_both
        total_unsupported += len(unsupported)

    report["summary"] = {
        "officialPlayers": total_official,
        "supportedByBothSecondaries": total_supported_both,
        "unsupportedByEitherSecondary": total_unsupported,
        "teamsWithAnyDisagreement": teams_with_disagreements,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        "2026 SOURCE CONSENSUS: "
        f"{total_official} official players; "
        f"{total_supported_both} supported by both secondaries; "
        f"{total_unsupported} unsupported by either secondary; "
        f"{teams_with_disagreements} teams with at least one disagreement"
    )


if __name__ == "__main__":
    main()
