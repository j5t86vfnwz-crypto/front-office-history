#!/usr/bin/env python3
"""Final roster-room quality pass for the generated Front Office History bundle.

The historical builder already determines membership and broad depth tiers. This pass
resolves ordering *inside* a position room, where formation-based depth charts can mark
several receivers/backs/defensive backs as co-starters or occasionally put a fringe
player one tier above a clearly established starter. Exact verified anchors remain the
strongest correction. Outside anchors, official depth tier is authoritative unless
season-long role evidence overwhelmingly identifies a one-tier anomaly.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILE = ROOT / "dist" / "data" / "offline-data.json"

# Narrow, auditable anchors for cases the user has specifically caught and verified.
VERIFIED_ROOM_PRIORITY: dict[tuple[int, str, str], tuple[str, ...]] = {
    (2025, "Dallas Cowboys", "WR"): ("CeeDee Lamb",),
    (2026, "Dallas Cowboys", "WR"): ("CeeDee Lamb", "George Pickens"),
}

# Deliberately conservative: only a one-tier discrepancy can be corrected, and only
# when the lower-listed player has both strong usage and overwhelming role evidence.
ONE_TIER_PROMOTION_GAP = 420.0
ONE_TIER_PROMOTION_RATIO = 2.15
ONE_TIER_PROMOTION_MIN_EVIDENCE = 650.0
ONE_TIER_PROMOTION_MIN_USAGE = 0.45


def norm(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def num(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def intval(value: Any, default: int = 99) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def status_priority(value: Any) -> int:
    status = str(value or "").upper()
    if status in {"ACT", "ACTIVE", "DEPTH"}:
        return 0
    if status in {"RES", "IR", "PUP", "NFI", "SUS", "RESERVE"}:
        return 1
    if status in {"RFA", "ERFA"}:
        return 2
    if status == "UFA":
        return 3
    return 4


def usage_fraction(player: dict[str, Any]) -> float:
    stats = player.get("_stats") or {}
    games = max(1.0, num(player.get("games") or stats.get("games") or stats.get("games_played"), 1.0))
    starts = max(0.0, num(player.get("starts") or stats.get("starts") or stats.get("games_started")))
    return max(num(player.get("_starter_rate")), min(1.0, starts / games))


def role_evidence(player: dict[str, Any]) -> float:
    """Comparable same-room evidence; ordinary cases still respect depth tier."""
    score = num(player.get("_role_score"))
    stats = player.get("_stats") or {}
    games = max(1.0, num(player.get("games") or stats.get("games") or stats.get("games_played"), 1.0))
    starts = max(0.0, num(player.get("starts") or stats.get("starts") or stats.get("games_started")))
    score += (starts / games) * 260.0
    score += num(player.get("_starter_rate")) * 180.0
    score += num(player.get("_depth_presence")) * 45.0
    score += min(30.0, num(player.get("av"))) * 5.0
    return score


def should_promote_one_tier(player: dict[str, Any], stronger_tier_players: list[dict[str, Any]]) -> bool:
    """Return True only for an obvious one-tier source anomaly.

    This is intentionally difficult to trigger. A player must have substantial starter
    usage and must beat at least one clearly weaker entry in the immediately higher tier by both a large
    absolute gap and a large ratio. It cannot leap two or more official tiers.
    """
    if not stronger_tier_players:
        return False
    evidence = role_evidence(player)
    reference = min(role_evidence(p) for p in stronger_tier_players)
    return (
        usage_fraction(player) >= ONE_TIER_PROMOTION_MIN_USAGE
        and evidence >= ONE_TIER_PROMOTION_MIN_EVIDENCE
        and evidence - reference >= ONE_TIER_PROMOTION_GAP
        and evidence >= max(1.0, reference) * ONE_TIER_PROMOTION_RATIO
    )


def effective_tiers(players: list[dict[str, Any]]) -> dict[int, int]:
    """Compute temporary sort tiers without mutating source depth evidence."""
    by_tier: dict[int, list[dict[str, Any]]] = {}
    for player in players:
        tier = intval(player.get("_officialDepthTier"), 99)
        if tier < 99:
            by_tier.setdefault(tier, []).append(player)

    adjusted: dict[int, int] = {}
    for player in players:
        tier = intval(player.get("_officialDepthTier"), 99)
        effective = tier
        if tier < 99 and tier > 1:
            previous = by_tier.get(tier - 1, [])
            if should_promote_one_tier(player, previous):
                effective = tier - 1
        adjusted[id(player)] = effective
    return adjusted


def room_sort_key(
    player: dict[str, Any], anchor_rank: dict[str, int], adjusted_tier: int
) -> tuple[Any, ...]:
    name = player.get("full_name") or player.get("display_name") or ""
    normalized = norm(name)
    tier = adjusted_tier
    has_tier = tier < 99
    old_order = intval(player.get("room_order") or player.get("_officialRoomOrder"), 999)
    anchored = normalized in anchor_rank

    return (
        0 if anchored else 1,
        anchor_rank.get(normalized, 999),
        0 if has_tier else 1,
        tier,
        -role_evidence(player),
        status_priority(player.get("status")),
        old_order,
        normalized,
    )


def refine_team_roster(year: int, team: str, roster: list[dict[str, Any]]) -> int:
    rooms: dict[str, list[dict[str, Any]]] = {}
    for player in roster:
        group = str(player.get("room_group") or "OTHER")
        rooms.setdefault(group, []).append(player)

    changed = 0
    for group, players in rooms.items():
        anchor = VERIFIED_ROOM_PRIORITY.get((year, team, group), ())
        anchor_rank = {norm(name): index for index, name in enumerate(anchor)}
        adjusted = effective_tiers(players)
        before = [
            norm(p.get("full_name") or p.get("display_name"))
            for p in sorted(players, key=lambda p: intval(p.get("room_order"), 999))
        ]
        players.sort(key=lambda p: room_sort_key(p, anchor_rank, adjusted[id(p)]))
        after = [norm(p.get("full_name") or p.get("display_name")) for p in players]
        if before != after:
            changed += 1
        for index, player in enumerate(players, 1):
            player["room_order"] = index
            player["_officialRoomOrder"] = index
    return changed


def refine_bundle(bundle: dict[str, Any]) -> tuple[int, int]:
    teams_seen = 0
    rooms_changed = 0
    for year_key, year_data in (bundle.get("years") or {}).items():
        try:
            year = int(year_key)
        except Exception:
            continue
        for team, team_data in (year_data.get("teams") or {}).items():
            roster = team_data.get("roster") or []
            if not roster:
                continue
            teams_seen += 1
            rooms_changed += refine_team_roster(year, team, roster)
    bundle["roomOrderRefinement"] = {
        "version": 3,
        "rule": (
            "verified exact anchors first; otherwise official depth tier with conservative "
            "one-tier anomaly correction, then season role evidence"
        ),
    }
    return teams_seen, rooms_changed


def write_bundle(path: Path, bundle: dict[str, Any]) -> None:
    text = json.dumps(bundle, separators=(",", ":"), ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    js_path = path.with_suffix(".js")
    js_path.write_text("window.FOH_OFFLINE_BUNDLE=" + text + ";\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(DEFAULT_FILE))
    args = parser.parse_args()
    path = Path(args.file)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    teams_seen, rooms_changed = refine_bundle(bundle)
    write_bundle(path, bundle)
    print(f"ROOM ORDER REFINEMENT: {teams_seen} team packs checked; {rooms_changed} rooms reordered")


if __name__ == "__main__":
    main()
