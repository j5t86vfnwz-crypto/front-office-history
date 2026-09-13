#!/usr/bin/env python3
"""Delete only cache entries that must be fresh for the current 2026 roster.

Historical seasons remain cached for fast/reproducible builds. Current-team pages,
current ESPN roster JSON, and current-season nflverse roster/depth evidence are
refetched on every live-roster build.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
PATTERNS = (
    "nfl_sitemap_2026_*",
    "nfl_team_roster_2026_*",
    "espn_current_roster_*",
    "roster_2026.csv",
    "weekly_2026.csv",
    "depth_2026.csv",
    "stats_2026.csv",
    "snaps_2026.csv",
)

removed = 0
for pattern in PATTERNS:
    for path in CACHE.glob(pattern):
        if path.is_file():
            path.unlink()
            removed += 1

print(f"LIVE ROSTER CACHE: removed {removed} current-source cache files")
