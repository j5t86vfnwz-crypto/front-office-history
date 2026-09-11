#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("refiner", ROOT / "scripts" / "refine_bundle.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def p(name, role, tier=1, group="WR"):
    return {
        "full_name": name,
        "room_group": group,
        "room_order": 1,
        "_officialRoomOrder": 1,
        "_officialDepthTier": tier,
        "_role_score": role,
        "_starter_rate": 1,
        "_depth_presence": 1,
        "status": "ACT",
    }


def test_dallas_anchor_and_role_tie_break():
    roster = [p("Camden Brown", 70), p("George Pickens", 700), p("CeeDee Lamb", 850)]
    r.refine_team_roster(2026, "Dallas Cowboys", roster)
    roster.sort(key=lambda x: x["room_order"])
    assert [x["full_name"] for x in roster] == ["CeeDee Lamb", "George Pickens", "Camden Brown"]


def test_depth_tier_remains_authoritative_without_anchor():
    roster = [p("First Team", 120, tier=1), p("Second Team Star", 2000, tier=2)]
    r.refine_team_roster(2024, "Detroit Lions", roster)
    roster.sort(key=lambda x: x["room_order"])
    assert [x["full_name"] for x in roster] == ["First Team", "Second Team Star"]


def test_role_breaks_same_tier_tie():
    roster = [p("Low Usage", 40), p("Primary Option", 700)]
    r.refine_team_roster(2024, "Detroit Lions", roster)
    roster.sort(key=lambda x: x["room_order"])
    assert [x["full_name"] for x in roster] == ["Primary Option", "Low Usage"]


if __name__ == "__main__":
    test_dallas_anchor_and_role_tie_break()
    test_depth_tier_remains_authoritative_without_anchor()
    test_role_breaks_same_tier_tie()
    print("ROOM REFINEMENT TESTS: PASS")
