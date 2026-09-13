#!/usr/bin/env python3
"""Make NFL.com current 2026 positions authoritative after depth enrichment.

Depth/stats may order a room, but they must never rewrite a specific current NFL
position. Broad NFL labels such as OL and DB may keep a more specific subtype
already resolved from ESPN/depth evidence.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import build_data as b
import rebuild_2026_current as cur

ROOT = Path(__file__).resolve().parents[1]
BROAD = {"OL", "DB", "DL", "DEF", "OFF", ""}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(ROOT / "dist/data/offline-data.json"))
    args = ap.parse_args()

    path = Path(args.file)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    year = (bundle.get("years") or {}).get("2026")
    if not year:
        raise RuntimeError("2026 pack missing")

    changed = 0
    checked = 0
    for team in b.TEAMS:
        td = (year.get("teams") or {}).get(team)
        if not td:
            raise RuntimeError(f"{team}: missing 2026 team pack")
        _, official_names = cur.nfl_membership(team)
        _, nfl_meta = cur.nfl_roster_metadata(team, official_names)
        by_name = {b.norm_name(p.get("full_name") or p.get("display_name")): p for p in (td.get("roster") or [])}

        for nk, src in nfl_meta.items():
            p = by_name.get(nk)
            if not p:
                continue
            checked += 1
            raw = str(src.get("position") or "").upper().strip()
            if raw in BROAD:
                continue
            official = b.canonical_pos(raw)
            if b.group_for_pos(official) == "OTHER":
                continue
            if b.canonical_pos(p.get("position")) != official:
                p["position"] = official
                p["room_group"] = b.group_for_pos(official)
                changed += 1

        # Rebuild sequential room order after any player changed rooms.
        rooms = defaultdict(list)
        for p in td.get("roster") or []:
            group = b.group_for_pos(p.get("position"))
            p["room_group"] = group
            rooms[group].append(p)
        for room in rooms.values():
            room.sort(key=lambda p: (int(p.get("room_order") or 999), str(p.get("full_name") or "")))
            for rank, p in enumerate(room, 1):
                p["room_order"] = rank
                p["_officialRoomOrder"] = rank

    text = json.dumps(bundle, separators=(",", ":"), ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    path.with_suffix(".js").write_text("window.FOH_OFFLINE_BUNDLE=" + text + ";\n", encoding="utf-8")
    print(f"2026 OFFICIAL POSITION LOCK: checked {checked} NFL rows; corrected {changed} positions")


if __name__ == "__main__":
    main()
