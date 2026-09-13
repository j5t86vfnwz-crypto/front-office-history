#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("refiner", ROOT / "scripts" / "refine_bundle.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def p(name, role, tier=1, group="WR", starter_rate=1.0, status="ACT"):
    return {
        "full_name": name,
        "room_group": group,
        "room_order": 1,
        "_officialRoomOrder": 1,
        "_officialDepthTier": tier,
        "_role_score": role,
        "_starter_rate": starter_rate,
        "_depth_presence": 1,
        "status": status,
    }


def names(roster):
    roster.sort(key=lambda x: x["room_order"])
    return [x["full_name"] for x in roster]


def test_dallas_anchor_and_role_tie_break():
    roster = [p("Camden Brown", 70), p("George Pickens", 700), p("CeeDee Lamb", 850)]
    r.refine_team_roster(2026, "Dallas Cowboys", roster)
    assert names(roster) == ["CeeDee Lamb", "George Pickens", "Camden Brown"]


def test_obvious_one_tier_anomaly_is_corrected():
    roster = [
        p("Fringe First Team", 90, tier=1, starter_rate=0.05),
        p("Established Starter", 1400, tier=2, starter_rate=0.95),
    ]
    r.refine_team_roster(2024, "Detroit Lions", roster)
    assert names(roster) == ["Established Starter", "Fringe First Team"]


def test_star_can_split_true_starter_and_fringe_same_tier():
    roster = [
        p("True Starter", 1200, tier=1, starter_rate=0.95),
        p("Fringe Slot", 70, tier=1, starter_rate=0.05),
        p("Established Starter", 900, tier=2, starter_rate=0.9),
    ]
    r.refine_team_roster(2024, "Detroit Lions", roster)
    assert names(roster) == ["True Starter", "Established Starter", "Fringe Slot"]


def test_normal_depth_tier_stays_authoritative():
    roster = [
        p("First Team", 520, tier=1, starter_rate=0.7),
        p("Second Team Contributor", 760, tier=2, starter_rate=0.55),
    ]
    r.refine_team_roster(2024, "Detroit Lions", roster)
    assert names(roster) == ["First Team", "Second Team Contributor"]


def test_two_tier_jump_is_never_allowed():
    roster = [
        p("First Team", 100, tier=1, starter_rate=0.1),
        p("Third Tier Star", 2200, tier=3, starter_rate=1.0),
    ]
    r.refine_team_roster(2024, "Detroit Lions", roster)
    assert names(roster) == ["First Team", "Third Tier Star"]


def test_low_usage_player_cannot_override_depth():
    roster = [
        p("First Team", 100, tier=1, starter_rate=0.6),
        p("Flash Player", 1600, tier=2, starter_rate=0.1),
    ]
    r.refine_team_roster(2024, "Detroit Lions", roster)
    assert names(roster) == ["First Team", "Flash Player"]


def test_role_breaks_same_tier_tie():
    roster = [p("Low Usage", 40), p("Primary Option", 700)]
    r.refine_team_roster(2024, "Detroit Lions", roster)
    assert names(roster) == ["Primary Option", "Low Usage"]


if __name__ == "__main__":
    test_dallas_anchor_and_role_tie_break()
    test_obvious_one_tier_anomaly_is_corrected()
    test_star_can_split_true_starter_and_fringe_same_tier()
    test_normal_depth_tier_stays_authoritative()
    test_two_tier_jump_is_never_allowed()
    test_low_usage_player_cannot_override_depth()
    test_role_breaks_same_tier_tie()
    print("ROOM REFINEMENT TESTS: PASS")
