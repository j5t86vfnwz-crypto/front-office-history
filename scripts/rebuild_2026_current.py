#!/usr/bin/env python3
"""Replace the 2026 roster section with a current all-32-team snapshot.

Membership authority: NFL.com 2026 roster sitemap for each team.
Position/status authority: NFL.com current team roster page when parseable.
Metadata fallbacks: ESPN current roster, then nflverse 2026 roster/weekly data.
Depth charts/stats are ordering evidence only and may never create membership.
"""
from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import build_data as b

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_YEAR = 2026
SNAPSHOT_DATE = "2026-09-12"


class Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            text = str(data).strip()
            if text:
                self.cell.append(text)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            self.row.append(" ".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None
            self.cell = None


def slug(team: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", team.lower()).strip("-")


def fetch_text(url: str, key: str) -> str:
    return b.download_bytes(url, key, timeout=90, retries=4).decode("utf-8", errors="replace")


def nfl_membership(team: str) -> tuple[str, list[str]]:
    url = f"https://www.nfl.com/sitemap/html/rosters/2026/{slug(team)}"
    html = fetch_text(url, f"nfl_sitemap_2026_{slug(team)}_{SNAPSHOT_DATE}.html")
    parser = Rows(); parser.feed(html)
    names: list[str] = []
    seen: set[str] = set()
    for row in parser.rows:
        if len(row) < 2:
            continue
        # sitemap rows are jersey number + player name
        candidate = row[-1].strip()
        nk = b.norm_name(candidate)
        if not nk or nk in {"player", "jerseyplayer"}:
            continue
        first = row[0].strip()
        if first:
            try:
                int(first)
            except Exception:
                continue
        if nk not in seen:
            seen.add(nk); names.append(candidate)
    if len(names) < 45:
        raise RuntimeError(f"{team}: NFL.com sitemap yielded only {len(names)} players")
    return url, names


def nfl_roster_metadata(team: str, official_names: list[str]) -> tuple[str, dict[str, dict[str, Any]]]:
    url = f"https://www.nfl.com/teams/{slug(team)}/roster"
    html = fetch_text(url, f"nfl_team_roster_2026_{slug(team)}_{SNAPSHOT_DATE}.html")
    parser = Rows(); parser.feed(html)
    official = {b.norm_name(n): n for n in official_names}
    out: dict[str, dict[str, Any]] = {}
    for row in parser.rows:
        if len(row) < 4:
            continue
        # NFL table columns: Player, No, Pos, Status, Height, Weight, Experience, College
        name = row[0].replace("Image", "", 1).strip()
        nk = b.norm_name(name)
        if nk not in official:
            continue
        pos = row[2].strip() if len(row) > 2 else ""
        status = row[3].strip() if len(row) > 3 else ""
        out[nk] = {
            "full_name": official[nk],
            "display_name": official[nk],
            "jersey_number": row[1].strip() if len(row) > 1 else "",
            "position": pos,
            "status": status,
            "height": row[4].strip() if len(row) > 4 else "",
            "weight": row[5].strip() if len(row) > 5 else "",
            "years_exp": row[6].strip() if len(row) > 6 else "",
            "college": row[7].strip() if len(row) > 7 else "",
        }
    return url, out


def unwrap(value: Any, *keys: str) -> str:
    if isinstance(value, dict):
        for key in keys:
            if value.get(key) not in (None, ""):
                return str(value[key])
        return ""
    return str(value or "")


def espn_metadata(team: str) -> tuple[str, dict[str, dict[str, Any]]]:
    tid = b.ESPN_TEAM_ID[team]
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{tid}/roster"
    try:
        data = b.read_json_url(url, f"espn_current_roster_{tid}_{SNAPSHOT_DATE}.json")
    except Exception as exc:
        print(f"WARN {team}: ESPN roster unavailable: {exc}")
        return url, {}
    out: dict[str, dict[str, Any]] = {}
    for group in data.get("athletes") or []:
        for raw in group.get("items") or []:
            athlete = raw.get("athlete") if isinstance(raw, dict) and isinstance(raw.get("athlete"), dict) else raw
            if not isinstance(athlete, dict):
                continue
            name = athlete.get("fullName") or athlete.get("displayName") or athlete.get("name")
            if not name:
                continue
            headshot = unwrap(athlete.get("headshot"), "href")
            college = unwrap(athlete.get("college"), "name")
            exp = athlete.get("experience") or {}
            out[b.norm_name(name)] = {
                "full_name": str(name).strip(),
                "display_name": str(name).strip(),
                "position": unwrap(athlete.get("position") or raw.get("position") or group.get("position"), "abbreviation", "name"),
                "status": unwrap(athlete.get("status") or raw.get("status"), "abbreviation", "type", "name"),
                "jersey_number": athlete.get("jersey") or raw.get("jersey") or "",
                "college": college,
                "years_exp": exp.get("years") if isinstance(exp, dict) else exp,
                "espn_id": str(athlete.get("id") or ""),
                "headshot_url": headshot,
                "height": athlete.get("height") or "",
                "weight": athlete.get("weight") or "",
            }
    return url, out


def nflverse_index(sd, master_idx) -> dict[str, dict[str, Any]]:
    latest = b.latest_weekly_membership(sd.get("weekly") or [])
    merged: dict[str, dict[str, Any]] = {}
    for raw in (sd.get("roster") or []) + list(latest.values()):
        p = b.enrich(raw, master_idx)
        name = b.player_name(p)
        if name:
            merged[b.norm_name(name)] = p
    return merged


def specific_position(*values: Any) -> str:
    cleaned = [str(v or "").upper().strip() for v in values if v not in (None, "")]
    # Prefer a specific current position over generic DB/OL/DL labels.
    for p in cleaned:
        cp = b.canonical_pos(p)
        if p not in {"DB", "OL", "DL", "DEF", "OFF", ""} and b.group_for_pos(cp) != "OTHER":
            return cp
    for p in cleaned:
        cp = b.canonical_pos(p)
        if b.group_for_pos(cp) != "OTHER":
            return cp
    return "OTHER"


def current_player(name: str, team: str, nfl: dict[str, Any], espn: dict[str, Any], nv: dict[str, Any], master_idx):
    p: dict[str, Any] = {"full_name": name, "display_name": name, "team": b.BASE_ABBR[team]}
    if nv:
        p.update(nv)
    if espn:
        p.update({k: v for k, v in espn.items() if v not in (None, "")})
    if nfl:
        # Official NFL current fields override metadata fallbacks.
        p.update({k: v for k, v in nfl.items() if v not in (None, "")})
    p["full_name"] = name; p["display_name"] = name; p["team"] = b.BASE_ABBR[team]
    p = b.enrich(p, master_idx)
    p["position"] = specific_position(nfl.get("position"), espn.get("position"), nv.get("position"), p.get("position"))
    p["status"] = b.normalize_status_code(nfl.get("status") or espn.get("status") or nv.get("status") or p.get("status"))
    if b.group_for_pos(p["position"]) == "OTHER":
        raise RuntimeError(f"{team}: unresolved position for official roster player {name}")
    return p


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--file", default=str(ROOT / "dist/data/offline-data.json")); args = ap.parse_args()
    path = Path(args.file)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    year = (bundle.get("years") or {}).get("2026")
    if not year:
        raise RuntimeError("2026 pack missing")

    master = b.read_csv_url(b.URLS["players"], "players.csv")
    master_idx = b.build_master_index(master)
    current = b.download_season_dataset(2026)
    prior = b.download_season_dataset(2025)
    nv = nflverse_index(current, master_idx)

    ownership: dict[str, str] = {}
    manifest: dict[str, Any] = {"snapshotDate": SNAPSHOT_DATE, "season": 2026, "teams": {}}
    total = 0

    for team in b.TEAMS:
        sitemap_url, names = nfl_membership(team)
        nfl_url, nfl_meta = nfl_roster_metadata(team, names)
        espn_url, espn_meta = espn_metadata(team)
        official = {b.norm_name(n): n for n in names}
        roster: list[dict[str, Any]] = []
        for nk, name in official.items():
            if nk in ownership and ownership[nk] != team:
                raise RuntimeError(f"NFL.com duplicate membership: {name} on {ownership[nk]} and {team}")
            ownership[nk] = team
            roster.append(current_player(name, team, nfl_meta.get(nk, {}), espn_meta.get(nk, {}), nv.get(nk, {}), master_idx))

        # Ordering evidence only; explicitly remove any player that depth fallback tries to add.
        roster = b.attach_player_evidence(roster, current.get("depth") or [], current.get("stats") or [], current.get("snaps") or [], prior.get("stats") or [], team, 2026)
        roster = [p for p in roster if b.norm_name(b.player_name(p)) in official]
        if len(roster) != len(official):
            raise RuntimeError(f"{team}: official membership count changed during enrichment")
        roster = b.assign_room_order(roster, team, 2026)

        td = year["teams"][team]
        td["rosterSeason"] = 2026
        td["snapshotDate"] = SNAPSHOT_DATE
        td["snapshotType"] = "current"
        td["roster"] = [b.compact_player(p) for p in roster]
        manifest["teams"][team] = {
            "membership": sitemap_url,
            "officialRoster": nfl_url,
            "espnFallback": espn_url,
            "players": len(roster),
            "nflMetadataMatches": len(nfl_meta),
            "espnMetadataMatches": sum(1 for nk in official if nk in espn_meta),
        }
        total += len(roster)
        print(f"2026 VERIFIED {team}: {len(roster)} players; NFL metadata {len(nfl_meta)}/{len(roster)}")

    year["rosterSeason"] = 2026
    year["snapshotDate"] = SNAPSHOT_DATE
    year["snapshotType"] = "current"
    year["snapshotLabel"] = "Current roster snapshot — September 12, 2026"

    text = json.dumps(bundle, separators=(",", ":"), ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    path.with_suffix(".js").write_text("window.FOH_OFFLINE_BUNDLE=" + text + ";\n", encoding="utf-8")
    (path.parent / "roster-2026-source-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"2026 CURRENT REBUILD COMPLETE: {total} roster rows, {len(ownership)} unique players")


if __name__ == "__main__":
    main()
