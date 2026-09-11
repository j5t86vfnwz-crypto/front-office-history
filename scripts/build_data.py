#!/usr/bin/env python3
"""Build deterministic offline data for Front Office History.

The browser must never infer historical roster order. This builder assigns an
explicit room_order to every player for every team/offseason pack.

Primary sources:
- nflverse season rosters / weekly rosters / depth charts / players / stats / snap counts
- nflverse nfldata draft picks, trades, games
- ESPN historical free-agent API as a supplement when available

Only simulation/model fields are generated. Historical fields are copied from sources.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
DIST = ROOT / "dist" / "data"
CACHE.mkdir(parents=True, exist_ok=True)
DIST.mkdir(parents=True, exist_ok=True)

RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"
RAW = "https://raw.githubusercontent.com/nflverse/nfldata/master/data"
URLS = {
    "draft": f"{RELEASE}/draft_picks/draft_picks.csv",
    "trades": f"{RAW}/trades.csv",
    "games": f"{RAW}/games.csv",
    "logos": f"{RAW}/logos.csv",
    "players": f"{RELEASE}/players/players.csv",
}

# Official nflreadr coverage. Keep this explicit so expected historical gaps do not
# masquerade as failed downloads in production QA.
DATASET_COVERAGE = {
    "roster": 1920,
    "weekly": 2002,
    "depth": 2001,
    "stats": 1999,
    "snaps": 2012,
}
SOURCE_DOCS = {
    "roster": "https://github.com/nflverse/nflreadr/blob/main/R/load_rosters.R",
    "weekly": "https://github.com/nflverse/nflreadr/blob/main/R/load_rosters_weekly.R",
    "depth": "https://github.com/nflverse/nflreadr/blob/main/R/load_depth_charts.R",
    "stats": "https://github.com/nflverse/nflreadr/blob/main/R/load_stats.R",
    "snaps": "https://github.com/nflverse/nflreadr/blob/main/R/load_snap_counts.R",
    "players": "https://github.com/nflverse/nflreadr/blob/main/R/load_players.R",
}

TEAMS = [
    "Arizona Cardinals","Atlanta Falcons","Baltimore Ravens","Buffalo Bills","Carolina Panthers","Chicago Bears",
    "Cincinnati Bengals","Cleveland Browns","Dallas Cowboys","Denver Broncos","Detroit Lions","Green Bay Packers",
    "Houston Texans","Indianapolis Colts","Jacksonville Jaguars","Kansas City Chiefs","Las Vegas Raiders",
    "Los Angeles Chargers","Los Angeles Rams","Miami Dolphins","Minnesota Vikings","New England Patriots",
    "New Orleans Saints","New York Giants","New York Jets","Philadelphia Eagles","Pittsburgh Steelers",
    "San Francisco 49ers","Seattle Seahawks","Tampa Bay Buccaneers","Tennessee Titans","Washington Commanders",
]

BASE_ABBR = {
    "Arizona Cardinals":"ARI","Atlanta Falcons":"ATL","Baltimore Ravens":"BAL","Buffalo Bills":"BUF",
    "Carolina Panthers":"CAR","Chicago Bears":"CHI","Cincinnati Bengals":"CIN","Cleveland Browns":"CLE",
    "Dallas Cowboys":"DAL","Denver Broncos":"DEN","Detroit Lions":"DET","Green Bay Packers":"GB",
    "Houston Texans":"HOU","Indianapolis Colts":"IND","Jacksonville Jaguars":"JAX","Kansas City Chiefs":"KC",
    "Las Vegas Raiders":"LV","Los Angeles Chargers":"LAC","Los Angeles Rams":"LAR","Miami Dolphins":"MIA",
    "Minnesota Vikings":"MIN","New England Patriots":"NE","New Orleans Saints":"NO","New York Giants":"NYG",
    "New York Jets":"NYJ","Philadelphia Eagles":"PHI","Pittsburgh Steelers":"PIT","San Francisco 49ers":"SF",
    "Seattle Seahawks":"SEA","Tampa Bay Buccaneers":"TB","Tennessee Titans":"TEN","Washington Commanders":"WAS",
}

ALIASES_TO_TEAM = {
    **{v:k for k,v in BASE_ABBR.items()},
    "OAK":"Las Vegas Raiders","SD":"Los Angeles Chargers","STL":"Los Angeles Rams","LA":"Los Angeles Rams",
    "WSH":"Washington Commanders","JAC":"Jacksonville Jaguars",
}

ESPN_TEAM_ID = {
    "Atlanta Falcons":1,"Buffalo Bills":2,"Chicago Bears":3,"Cincinnati Bengals":4,"Cleveland Browns":5,
    "Dallas Cowboys":6,"Denver Broncos":7,"Detroit Lions":8,"Green Bay Packers":9,"Tennessee Titans":10,
    "Indianapolis Colts":11,"Kansas City Chiefs":12,"Las Vegas Raiders":13,"Los Angeles Rams":14,"Miami Dolphins":15,
    "Minnesota Vikings":16,"New England Patriots":17,"New Orleans Saints":18,"New York Giants":19,"New York Jets":20,
    "Philadelphia Eagles":21,"Arizona Cardinals":22,"Pittsburgh Steelers":23,"Los Angeles Chargers":24,
    "San Francisco 49ers":25,"Seattle Seahawks":26,"Tampa Bay Buccaneers":27,"Washington Commanders":28,
    "Carolina Panthers":29,"Jacksonville Jaguars":30,"Baltimore Ravens":33,"Houston Texans":34,
}
ESPN_ID_TEAM = {str(v):k for k,v in ESPN_TEAM_ID.items()}

# These are broad *room* groups, intentionally not formation slots.
GROUP_ORDER = ["QB","RB","FB","WR","TE","OT","G","C","EDGE","DT","LB","CB","S","K","P","LS","OTHER"]
POSITION_MAP = {
    "LWR":"WR","RWR":"WR","SWR":"WR","SLWR":"WR","SRWR":"WR","XWR":"WR","ZWR":"WR","FL":"WR","SE":"WR",
    "HB":"RB","TB":"RB","B":"RB","H":"RB",
    "T":"OT","LOT":"OT","ROT":"OT","LT":"OT","RT":"OT",
    "LG":"G","RG":"G","OG":"G",
    "LDE":"EDGE","RDE":"EDGE","LE":"EDGE","RE":"EDGE","DE":"EDGE","ED":"EDGE","OLB":"LB",
    "LDT":"DT","RDT":"DT","LNT":"DT","RNT":"DT","NT":"DT","IDL":"DT","DL":"DT",
    "MLB":"LB","ILB":"LB","WLB":"LB","SLB":"LB","LILB":"LB","RILB":"LB","LOLB":"LB","ROLB":"LB",
    "LCB":"CB","RCB":"CB","NB":"CB","NCB":"CB","SCB":"CB","DB":"S",
    "FS":"S","SS":"S","SAF":"S",
    "PK":"K","PT":"P",
}

PENDING_FA = {"UFA","RFA","ERFA"}
FREE_AGENT_STATUSES = {"UFA","RFA","ERFA","CUT","NWT","RSR"}

VERIFIED_TEAM_CAP: dict[str, int] = {
    # Snapshot-specific facts only. Do not fill other clubs with estimates.
    "2018|Cleveland Browns": 108_692_537,
}

# Source-table repairs are deliberately narrow and auditable. The nfldata trade
# table does not represent every hop when a pick is traded multiple times.
VERIFIED_PICK_OWNERS: dict[tuple[int, int], str] = {
    **{(2018, pick): "CLE" for pick in (1, 4, 33, 35, 64, 65, 101, 123, 138, 159, 175, 219)},
    (2018, 188): "WAS",  # Acquired by Cleveland from Washington on April 5.
}

# When official depth evidence leaves formation starters tied, preserve a
# documented team room order instead of letting a noisy stat tie-break decide.
VERIFIED_ROOM_PRIORITY: dict[tuple[int, str, str], tuple[str, ...]] = {
    (2026, "Dallas Cowboys", "WR"): ("CeeDee Lamb", "George Pickens"),
}


def norm_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def num(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def intval(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def canonical_pos(value: Any) -> str:
    p = str(value or "").upper().strip()
    if not p:
        return "OTHER"
    return POSITION_MAP.get(p, p)


def group_for_pos(value: Any) -> str:
    p = canonical_pos(value)
    if p == "QB": return "QB"
    if p == "RB": return "RB"
    if p == "FB": return "FB"
    if p == "WR": return "WR"
    if p == "TE": return "TE"
    if p in {"OT","LT","RT","T"}: return "OT"
    if p in {"G","OG","LG","RG"}: return "G"
    if p == "C": return "C"
    if p in {"EDGE","DE"}: return "EDGE"
    if p in {"DT","NT","DL","IDL"}: return "DT"
    if p in {"LB","ILB","OLB","MLB","WLB","SLB"}: return "LB"
    if p == "CB": return "CB"
    if p in {"S","FS","SS","DB"}: return "S"
    if p == "K": return "K"
    if p == "P": return "P"
    if p == "LS": return "LS"
    return "OTHER"



def normalize_status_code(value: Any) -> str:
    raw=str(value or "").strip()
    u=raw.upper()
    if not u:
        return ""
    direct={
        "ACT":"ACT","ACTIVE":"ACT","UFA":"UFA","RFA":"RFA","ERFA":"ERFA",
        "CUT":"CUT","NWT":"NWT","RSR":"RSR","PUP":"PUP","RES":"RES","SUS":"SUS",
        "DEV":"DEV","INA":"INA","RET":"RET","EXE":"EXE","TRC":"TRC","TRD":"TRD","TRT":"TRT",
    }
    if u in direct:return direct[u]
    text=re.sub(r"[^A-Z0-9]+"," ",u).strip()
    if "UNRESTRICTED FREE AGENT" in text:return "UFA"
    if "EXCLUSIVE RIGHTS FREE AGENT" in text:return "ERFA"
    if "RESTRICTED FREE AGENT" in text:return "RFA"
    if "PRACTICE SQUAD" in text:return "DEV"
    if "WAIVER" in text:return "NWT"
    if "RELEASE" in text or "CUT" in text:return "CUT"
    if "SUSP" in text:return "SUS"
    if "PHYSICALLY UNABLE" in text or text=="PUP":return "PUP"
    if "INJURED" in text or text.startswith("R "):return "RES"
    if "RETIRED" in text:return "RET"
    if "INACTIVE" in text:return "INA"
    if "ACTIVE" in text:return "ACT"
    return u

def historical_abbr(team: str, roster_season: int) -> list[str]:
    if team == "Las Vegas Raiders": return ["OAK"] if roster_season < 2020 else ["LV"]
    if team == "Los Angeles Chargers": return ["SD"] if roster_season < 2017 else ["LAC"]
    if team == "Los Angeles Rams": return ["STL"] if roster_season < 2016 else ["LA","LAR"]
    if team == "Washington Commanders": return ["WAS","WSH"]
    return [BASE_ABBR[team]]


def draft_abbr(team: str, year: int) -> list[str]:
    if team == "Las Vegas Raiders": return ["OAK"] if year < 2020 else ["LV"]
    if team == "Los Angeles Chargers": return ["SD"] if year < 2017 else ["LAC"]
    if team == "Los Angeles Rams": return ["STL"] if year < 2016 else ["LA","LAR"]
    if team == "Washington Commanders": return ["WAS","WSH"]
    return [BASE_ABBR[team]]


def canonical_team(abbr: str) -> str | None:
    return ALIASES_TO_TEAM.get(str(abbr or "").upper())


def player_name(row: dict[str, Any]) -> str:
    return str(row.get("full_name") or row.get("display_name") or row.get("player_name") or row.get("football_name") or row.get("pfr_name") or row.get("name") or "").strip()


def player_key(row: dict[str, Any]) -> str:
    return str(row.get("gsis_id") or row.get("player_id") or row.get("pfr_id") or row.get("playerid") or row.get("espn_id") or norm_name(player_name(row)))


def source_position(row: dict[str, Any]) -> str:
    return canonical_pos(row.get("position") or row.get("ngs_position") or row.get("pos_abb") or row.get("depth_position") or row.get("depth_chart_position"))


def cache_path(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", key)
    return CACHE / safe


def download_bytes(url: str, key: str, timeout: int = 90, retries: int = 3) -> bytes:
    path = cache_path(key)
    if path.exists() and path.stat().st_size:
        return path.read_bytes()
    last: Exception | None = None
    headers = {"User-Agent":"FrontOfficeHistoryBuilder/1.0", "Accept":"*/*"}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if not data:
                raise RuntimeError(f"empty response: {url}")
            path.write_bytes(data)
            return data
        except Exception as e:
            last = e
            time.sleep(1.0 + attempt * 1.5)
    raise RuntimeError(f"failed to download {url}: {last}")


def read_csv_url(url: str, key: str) -> list[dict[str, str]]:
    data = download_bytes(url, key)
    text = data.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def read_json_url(url: str, key: str) -> Any:
    return json.loads(download_bytes(url, key).decode("utf-8"))


def season_urls(season: int) -> dict[str,str]:
    return {
        "roster": f"{RELEASE}/rosters/roster_{season}.csv",
        "weekly": f"{RELEASE}/weekly_rosters/roster_weekly_{season}.csv",
        "depth": f"{RELEASE}/depth_charts/depth_charts_{season}.csv",
        "stats": f"{RELEASE}/stats_player/stats_player_reg_{season}.csv",
        "snaps": f"{RELEASE}/snap_counts/snap_counts_{season}.csv",
    }


def download_season_dataset(season: int) -> dict[str,list[dict[str,str]]]:
    urls = season_urls(season)
    out: dict[str,list[dict[str,str]]] = {}
    for name,url in urls.items():
        min_season=DATASET_COVERAGE[name]
        if season < min_season:
            out[name] = []
            continue
        try:
            out[name] = read_csv_url(url, f"{name}_{season}.csv")
        except Exception as e:
            # Roster/depth/weekly data are core inputs. Stats and snaps are evidence only;
            # the strict audit decides whether the resulting pack is publishable.
            print(f"WARN {season} {name}: {e}", file=sys.stderr)
            out[name] = []
    return out


def build_master_index(rows: list[dict[str,str]]) -> dict[str,dict[str,dict[str,str]]]:
    idx = {"gsis":{},"pfr":{},"espn":{},"name":{}}
    for r in rows:
        if r.get("gsis_id"): idx["gsis"][r["gsis_id"]] = r
        if r.get("pfr_id"): idx["pfr"][r["pfr_id"]] = r
        if r.get("espn_id"): idx["espn"][str(r["espn_id"])] = r
        n=norm_name(player_name(r))
        if n: idx["name"][n]=r
    return idx


def enrich(row: dict[str,Any], master: dict[str,dict[str,dict[str,str]]]) -> dict[str,Any]:
    # nfldata's draft/roster tables historically call the PFR identifier `playerid`.
    # Normalize it before joining to the nflverse players master.
    if row.get("playerid") and not row.get("pfr_id"):
        row={**row,"pfr_id":row.get("playerid")}
    m: dict[str,Any] = {}
    for kind,key in (("gsis","gsis_id"),("pfr","pfr_id"),("espn","espn_id")):
        value=row.get(key)
        if value and str(value) in master[kind]:
            m=master[kind][str(value)]; break
    if not m:
        m=master["name"].get(norm_name(player_name(row)), {})
    merged={**m,**row}
    merged["full_name"] = player_name(merged)
    merged["position"] = source_position(merged)
    return merged


def row_identity(row: dict[str,Any]) -> tuple[str,str]:
    key=player_key(row)
    return ("id",key) if key and not key.startswith("unknown") else ("name",norm_name(player_name(row)))


def match_index(rows: Iterable[dict[str,Any]]) -> dict[str,dict[str,Any]]:
    out={}
    for r in rows:
        for key in (r.get("gsis_id"),r.get("player_id"),r.get("pfr_id"),r.get("espn_id"),norm_name(player_name(r))):
            if key: out[str(key)]=r
    return out


def latest_weekly_membership(rows: list[dict[str,str]]) -> dict[str,dict[str,str]]:
    """Latest leaguewide row for each player, not merely latest row on one team."""
    latest: dict[str,tuple[tuple[int,int,str],dict[str,str]]] = {}
    for r in rows:
        k=player_key(r)
        if not k: continue
        season_type=str(r.get("game_type") or r.get("season_type") or "REG").upper()
        # Offseason snapshots must use the chronologically latest club membership.
        # Postseason rows come after regular-season rows; the old ordering had this backwards.
        type_rank = 3 if "POST" in season_type else (2 if "REG" in season_type else (1 if "PRE" in season_type else 0))
        week=intval(r.get("week"),0)
        date=str(r.get("date") or r.get("week_date") or r.get("last_game") or "")
        rank=(type_rank,week,date)
        if k not in latest or rank>latest[k][0]: latest[k]=(rank,r)
    return {k:v[1] for k,v in latest.items()}


def roster_membership(season_rows:list[dict[str,str]], weekly_rows:list[dict[str,str]], team:str, offseason:int, master_idx) -> list[dict[str,Any]]:
    aliases={x.upper() for x in historical_abbr(team, offseason-1)}
    latest=latest_weekly_membership(weekly_rows)
    pool: dict[str,dict[str,Any]]={}
    # Season roster is a source of players/status; weekly leaguewide rows decide final club where possible.
    for r in season_rows:
        if str(r.get("team") or r.get("club_code") or "").upper() not in aliases: continue
        e=enrich(r,master_idx); k=player_key(e)
        lw=latest.get(k)
        if lw:
            latest_team=str(lw.get("team") or lw.get("club_code") or "").upper()
            status=normalize_status_code(e.get("status"))
            if latest_team not in aliases and status not in PENDING_FA:
                continue
            e={**e,**{kk:vv for kk,vv in lw.items() if vv not in (None,"")}}
            e=enrich(e,master_idx)
        pool[k]=e
    # Weekly-only names can fill omissions.
    for k,r in latest.items():
        if str(r.get("team") or r.get("club_code") or "").upper() in aliases and k not in pool:
            pool[k]=enrich(r,master_idx)
    return list(pool.values())


def depth_team_rows(rows:list[dict[str,str]], team:str, season:int) -> list[dict[str,str]]:
    aliases={x.upper() for x in historical_abbr(team, season)}
    all_rows=[r for r in rows if str(r.get("club_code") or r.get("team") or "").upper() in aliases]
    if not all_rows:return []
    if not any(r.get("dt") for r in all_rows):
        reg=[r for r in all_rows if str(r.get("game_type") or "REG").upper()=="REG"]
        return reg or all_rows
    return all_rows


def snapshot_key(r:dict[str,str]) -> str:
    if r.get("dt"): return "D:"+str(r.get("dt"))
    return f"W:{str(r.get('game_type') or 'REG').upper()}:{intval(r.get('week')):02d}"


def complete_snapshots(rows:list[dict[str,str]]) -> list[list[dict[str,str]]]:
    groups:dict[str,list[dict[str,str]]]=defaultdict(list)
    for r in rows: groups[snapshot_key(r)].append(r)
    if not groups:return []
    max_count=max(len(v) for v in groups.values())
    threshold=max(18,int(max_count*.68))
    items=[(k,v) for k,v in groups.items() if len(v)>=threshold]
    if not items: items=list(groups.items())
    items.sort(key=lambda kv:kv[0])
    return [v for _,v in items]


def depth_player_key(r:dict[str,str]) -> str:
    return str(r.get("gsis_id") or r.get("player_id") or r.get("espn_id") or norm_name(player_name(r)))


def mode_rank(values:list[int]) -> int:
    vals=[v for v in values if 0<v<99]
    if not vals:return 99
    c=Counter(vals)
    return sorted(c.items(), key=lambda kv:(-kv[1],kv[0]))[0][0]


def depth_profiles(rows:list[dict[str,str]], team:str, season:int) -> dict[str,dict[str,Any]]:
    relevant=depth_team_rows(rows,team,season)
    snaps=complete_snapshots(relevant)
    if not snaps:return {}
    obs:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for si,snap in enumerate(snaps):
        for source_order,r in enumerate(snap):
            name=player_name(r)
            if not name:continue
            rank=intval(r.get("depth_team") or r.get("pos_rank"),99)
            if rank<=0:rank=99
            slot=intval(r.get("pos_slot"),source_order+1)
            pos=canonical_pos(r.get("depth_position") or r.get("pos_abb") or r.get("position") or r.get("pos_name"))
            item={"rank":rank,"slot":slot,"source_order":source_order+1,"pos":pos,"snapshot":si,"name":name,"gsis_id":r.get("gsis_id") or "","espn_id":str(r.get("espn_id") or "")}
            keys={depth_player_key(r),norm_name(name)}
            if item["gsis_id"]:keys.add(item["gsis_id"])
            if item["espn_id"]:keys.add(item["espn_id"])
            for k in keys:
                if k:obs[k].append(item)
    out={}
    total=max(1,len(snaps))
    for k,items in obs.items():
        # Avoid duplicate aliases inflating statistics: one observation per snapshot for this key.
        bysnap={}
        for x in items:
            old=bysnap.get(x["snapshot"])
            if old is None or (x["rank"],x["source_order"])<(old["rank"],old["source_order"]):bysnap[x["snapshot"]]=x
        xs=list(bysnap.values())
        ranks=[x["rank"] for x in xs]
        positions=[x["pos"] for x in xs if x["pos"]!="OTHER"]
        latest=max(xs,key=lambda x:x["snapshot"])
        out[k]={
            "tier":mode_rank(ranks),
            "best_tier":min(ranks) if ranks else 99,
            "starter_rate":sum(1 for x in xs if x["rank"]==1)/total,
            "second_rate":sum(1 for x in xs if x["rank"]==2)/total,
            "presence_rate":len(xs)/total,
            "latest_tier":latest["rank"],
            "latest_slot":latest["slot"],
            "latest_order":latest["source_order"],
            "position":Counter(positions).most_common(1)[0][0] if positions else latest["pos"],
            "snapshots":len(xs),
        }
    return out


def get_profile(p:dict[str,Any], profiles:dict[str,dict[str,Any]]) -> dict[str,Any]|None:
    for k in (p.get("gsis_id"),p.get("player_id"),p.get("espn_id"),norm_name(player_name(p))):
        if k is not None and str(k) in profiles:return profiles[str(k)]
    return None


def aggregate_stats(rows:list[dict[str,str]], team:str, season:int) -> dict[str,dict[str,float]]:
    aliases=set(historical_abbr(team, season))|{BASE_ABBR[team]}
    by:dict[str,dict[str,float]]=defaultdict(lambda:defaultdict(float))
    for r in rows:
        rt=str(r.get("recent_team") or r.get("team") or r.get("club_code") or "").upper()
        if rt and rt not in aliases:continue
        k=player_key(r)
        if not k:continue
        for col,val in r.items():
            if col in {"season","week","player_id","player_name","player_display_name","position","position_group","recent_team","team"}:continue
            try:
                x=float(val)
                if math.isfinite(x):by[k][col]+=x
            except Exception:pass
        by[k]["__rows"]+=1
    return {k:dict(v) for k,v in by.items()}


def aggregate_snaps(rows:list[dict[str,str]], team:str, season:int) -> dict[str,dict[str,float]]:
    aliases={x.upper() for x in historical_abbr(team, season)}|{BASE_ABBR[team]}
    by:dict[str,dict[str,float]]=defaultdict(lambda:defaultdict(float))
    for r in rows:
        rt=str(r.get("team") or r.get("club_code") or "").upper()
        if rt and rt not in aliases:continue
        k=player_key(r)
        if not k:continue
        for col in ("offense_snaps","defense_snaps","special_teams_snaps","offense_pct","defense_pct","st_pct"):
            by[k][col]+=num(r.get(col))
    return {k:dict(v) for k,v in by.items()}


def lookup_any(index:dict[str,dict[str,Any]], p:dict[str,Any]) -> dict[str,Any]:
    for k in (p.get("gsis_id"),p.get("player_id"),p.get("pfr_id"),p.get("espn_id"),norm_name(player_name(p))):
        if k and str(k) in index:return index[str(k)]
    return {}


def role_score(p:dict[str,Any], stats:dict[str,Any], snaps:dict[str,Any], prior:dict[str,Any]) -> float:
    group=group_for_pos(p.get("position"))
    games=max(1,num(p.get("games") or stats.get("games") or stats.get("games_played"),1))
    starts=max(num(p.get("starts") or stats.get("starts") or stats.get("games_started")),0)
    off=max(num(stats.get("offense_snaps")),num(snaps.get("offense_snaps")))
    deff=max(num(stats.get("defense_snaps")),num(snaps.get("defense_snaps")))
    st=max(num(stats.get("special_teams_snaps")),num(snaps.get("special_teams_snaps")))
    score=(starts/games)*1200 + min(max(off,deff),1300)*.28 + min(st,600)*.04
    if group=="QB": score+=num(stats.get("passing_attempts"))*1.4+num(stats.get("passing_yards"))*.035+num(stats.get("passing_tds"))*8
    elif group=="RB": score+=num(stats.get("carries"))*.95+num(stats.get("rushing_yards"))*.065+num(stats.get("targets"))*.55+num(stats.get("receiving_yards"))*.035
    elif group=="WR": score+=num(stats.get("targets"))*1.15+num(stats.get("receptions"))*.7+num(stats.get("receiving_yards"))*.10
    elif group=="TE": score+=num(stats.get("targets"))*.95+num(stats.get("receptions"))*.55+num(stats.get("receiving_yards"))*.075
    elif group in {"OT","G","C"}: score+=off*.35
    elif group in {"EDGE","DT","LB","CB","S"}: score+=deff*.32+num(stats.get("tackles"),0)*.5+num(stats.get("sacks"))*8+num(stats.get("interceptions"))*10
    elif group=="K": score+=num(stats.get("fg_made"))*4+num(stats.get("pat_made"))
    elif group=="P": score+=num(stats.get("punts"))*2
    # Prior-year evidence is deliberately small and only separates otherwise similar same-tier players.
    prior_usage=sum(num(prior.get(k)) for k in ("passing_attempts","carries","targets","offense_snaps","defense_snaps"))
    return score + min(prior_usage,1500)*.035


def attach_player_evidence(players:list[dict[str,Any]], depth_rows, stats_rows, snap_rows, prior_stats_rows, team, season):
    profiles=depth_profiles(depth_rows,team,season)
    stats_idx=aggregate_stats(stats_rows,team,season)
    prior_idx=aggregate_stats(prior_stats_rows,team,season-1)
    snap_idx=aggregate_snaps(snap_rows,team,season)
    # Add players that appear on historical depth charts but were missing from roster exports.
    roster_by_name={norm_name(player_name(p)):p for p in players}
    master_depth_names={}
    for r in depth_team_rows(depth_rows,team,season):
        n=player_name(r)
        if n:master_depth_names[norm_name(n)]=r
    for nk,r in master_depth_names.items():
        if nk not in roster_by_name:
            players.append({"full_name":player_name(r),"display_name":player_name(r),"position":canonical_pos(r.get("depth_position") or r.get("pos_abb")),"gsis_id":r.get("gsis_id") or "","espn_id":r.get("espn_id") or "","team":BASE_ABBR[team],"status":"DEPTH"})
    for p in players:
        prof=get_profile(p,profiles)
        if prof:
            p["_depth_tier"]=prof["tier"]
            p["_starter_rate"]=round(prof["starter_rate"],5)
            p["_second_rate"]=round(prof["second_rate"],5)
            p["_depth_presence"]=round(prof["presence_rate"],5)
            p["_latest_depth_tier"]=prof["latest_tier"]
            p["_latest_slot"]=prof["latest_slot"]
            # refine only generic base positions
            base=source_position(p); dp=canonical_pos(prof["position"])
            if base in {"OTHER","OL"} and group_for_pos(dp) in {"OT","G","C"}:p["position"]=dp
            elif base in {"OTHER","DL","DT"} and group_for_pos(dp) in {"EDGE","DT"}:p["position"]=dp
            elif base in {"OTHER","DB","S"} and group_for_pos(dp) in {"CB","S"}:p["position"]=dp
        else:
            p["_depth_tier"]=99;p["_starter_rate"]=0;p["_second_rate"]=0;p["_depth_presence"]=0;p["_latest_depth_tier"]=99;p["_latest_slot"]=99
        si=lookup_any(stats_idx,p); sn=lookup_any(snap_idx,p); pr=lookup_any(prior_idx,p)
        p["_role_score"]=round(role_score(p,si,sn,pr),4)
        p["_stats"]={k:round(v,3) for k,v in si.items() if k in {"games","games_played","starts","games_started","passing_attempts","passing_yards","passing_tds","carries","rushing_yards","targets","receptions","receiving_yards","receiving_tds","tackles","sacks","interceptions","offense_snaps","defense_snaps"} and v}
    return players


def status_priority(status:str)->int:
    s=normalize_status_code(status)
    if s=="ACT":return 0
    if s in {"RES","IR","PUP","NFI","SUS","RESERVE"}:return 1
    if s in {"RFA","ERFA"}:return 2
    if s=="UFA":return 3
    return 4


def assign_room_order(players:list[dict[str,Any]], team:str|None=None, offseason:int|None=None) -> list[dict[str,Any]]:
    rooms:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for p in players:
        g=group_for_pos(p.get("position"));p["room_group"]=g;rooms[g].append(p)
    for group,room in rooms.items():
        room.sort(key=lambda p:(
            0 if intval(p.get("_depth_tier"),99)<99 else 1,
            intval(p.get("_depth_tier"),99),
            -num(p.get("_starter_rate")),
            -num(p.get("_depth_presence")),
            -num(p.get("_role_score")),
            intval(p.get("_latest_depth_tier"),99),
            status_priority(str(p.get("status") or "")),
            player_name(p).lower(),
        ))
        priority=VERIFIED_ROOM_PRIORITY.get((offseason,team,group),())
        if priority:
            verified_rank={norm_name(name):i for i,name in enumerate(priority)}
            room.sort(key=lambda p:verified_rank.get(norm_name(player_name(p)),len(priority)))
        for i,p in enumerate(room,1):
            p["room_order"]=i
            p["_officialRoomOrder"]=i
            p["_roomGroup"]={
                "QB":"Quarterbacks","RB":"Running backs","FB":"Fullbacks","WR":"Wide receivers","TE":"Tight ends",
                "OT":"Offensive tackles","G":"Guards","C":"Centers","EDGE":"Edge / defensive ends","DT":"Defensive tackles",
                "LB":"Linebackers","CB":"Cornerbacks","S":"Safeties","K":"Kickers","P":"Punters","LS":"Long snappers","OTHER":"Other"
            }[group]
            p["_officialDepthTier"]=intval(p.get("_depth_tier"),99)
    return players


def compact_player(p:dict[str,Any]) -> dict[str,Any]:
    keep = {
        "full_name","display_name","position","status","team","jersey_number","college","college_name","years_exp",
        "gsis_id","pfr_id","espn_id","headshot_url","headshot","room_group","room_order","_officialRoomOrder","_roomGroup",
        "_officialDepthTier","_starter_rate","_depth_presence","_role_score","_stats","games","starts","av","birth_date","height","weight"
    }
    out={k:v for k,v in p.items() if k in keep and v not in (None,"")}
    out["full_name"]=player_name(p)
    out["position"]=canonical_pos(p.get("position"))
    out["room_group"]=p.get("room_group") or group_for_pos(out["position"])
    out["room_order"]=intval(p.get("room_order") or p.get("_officialRoomOrder"),99)
    out["_officialRoomOrder"]=out["room_order"]
    return out


def team_record(games:list[dict[str,str]], season:int, team:str) -> tuple[str|None,str|None]:
    aliases={x.upper() for x in historical_abbr(team,season)}
    w=l=t=0; coach=None; count=0
    for g in games:
        if intval(g.get("season"))!=season:continue
        if "REG" not in str(g.get("game_type") or g.get("season_type") or "REG").upper():continue
        home=str(g.get("home_team") or "").upper();away=str(g.get("away_team") or "").upper()
        if home not in aliases and away not in aliases:continue
        count+=1;is_home=home in aliases
        fp=num(g.get("home_score") if is_home else g.get("away_score"),float('nan'))
        ap=num(g.get("away_score") if is_home else g.get("home_score"),float('nan'))
        if math.isfinite(fp) and math.isfinite(ap):
            if fp>ap:w+=1
            elif fp<ap:l+=1
            else:t+=1
        c=g.get("home_coach") if is_home else g.get("away_coach")
        if c:coach=c
    return ((f"{w}-{l}"+(f"-{t}" if t else "")) if count else None, coach)


def normalize_trade_abbr(x:str)->str:
    x=str(x or "").upper()
    return {"LA":"LAR","SD":"LAC","OAK":"LV","WSH":"WAS"}.get(x,x)


def opening_pick_owners(draft_rows, trade_rows, year:int) -> dict[int,str]:
    rows=[r for r in draft_rows if intval(r.get("season"))==year and intval(r.get("pick"))>0]
    owners={intval(r.get("pick")):normalize_trade_abbr(r.get("team")) for r in rows}
    if year==2010:return owners
    snapshot=f"{year}-03-01"
    relevant=[r for r in trade_rows if intval(r.get("pick_season"))==year and intval(r.get("pick_number"))>0 and str(r.get("trade_date") or "")>snapshot]
    relevant.sort(key=lambda r:str(r.get("trade_date") or ""),reverse=True)
    for r in relevant:
        n=intval(r.get("pick_number"));gave=normalize_trade_abbr(r.get("gave"));received=normalize_trade_abbr(r.get("received"))
        if owners.get(n)==received:owners[n]=gave
    for (verified_year,pick),owner in VERIFIED_PICK_OWNERS.items():
        if verified_year==year and pick in owners:owners[pick]=owner
    return owners


def team_pick_inventory(owners:dict[int,str], team:str, year:int)->list[int]:
    aliases={normalize_trade_abbr(x) for x in draft_abbr(team,year)}|{normalize_trade_abbr(BASE_ABBR[team])}
    return sorted(p for p,o in owners.items() if normalize_trade_abbr(o) in aliases)


def build_draft_class(draft_rows, year:int, master_idx) -> list[dict[str,Any]]:
    out=[]
    for r in draft_rows:
        if intval(r.get("season"))!=year or intval(r.get("pick"))<=0:continue
        e=enrich(r,master_idx)
        name=str(r.get("pfr_name") or r.get("full_name") or player_name(e) or "Unknown player")
        out.append({
            "full_name":name,"display_name":name,"position":canonical_pos(r.get("position") or e.get("position")),
            "college":e.get("college") or e.get("college_name") or r.get("college") or "",
            "pfr_id":r.get("pfr_id") or r.get("playerid") or e.get("pfr_id") or "","gsis_id":r.get("player_id") or e.get("gsis_id") or "",
            "espn_id":e.get("espn_id") or "","headshot_url":e.get("headshot_url") or e.get("headshot") or "",
            "actual_team":r.get("team") or "","actual_pick":intval(r.get("pick")),"round":intval(r.get("round")),
        })
    return sorted(out,key=lambda r:r["actual_pick"])


def free_agent_status_pool(rows:list[dict[str,str]], master_idx) -> list[dict[str,Any]]:
    merged={}
    for r in rows:
        code=normalize_status_code(r.get("status"))
        if code not in FREE_AGENT_STATUSES:continue
        e=enrich(r,master_idx);k=player_key(e)
        prior=canonical_team(str(r.get("team") or "").upper())
        e.update({"fa_type":"CUT" if code in {"CUT","NWT","RSR"} else code,"prior_team_name":prior or "","status":code})
        merged[k]=compact_player(e)|{"fa_type":e["fa_type"],"prior_team_name":e["prior_team_name"]}
    return list(merged.values())


def _espn_id_from_ref(ref:str)->str:
    return str(ref or "").rstrip('/').split('/')[-1].split('?')[0]


def espn_free_agents(year:int, max_workers:int=18) -> list[dict[str,Any]]:
    """Historical ESPN supplement. Failure is non-fatal; the nflverse status pool remains."""
    base=f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{year}/freeagents"
    try:first=read_json_url(f"{base}?limit=250&page=1",f"espn_fa_{year}_1.json")
    except Exception as e:
        print(f"WARN ESPN FA {year}: {e}",file=sys.stderr);return []
    items=list(first.get("items") or []);pages=max(1,intval(first.get("pageCount"),1))
    for page in range(2,pages+1):
        try:items.extend((read_json_url(f"{base}?limit=250&page={page}",f"espn_fa_{year}_{page}.json").get("items") or []))
        except Exception:pass
    def resolve(item):
        try:
            detail=item
            if item.get("$ref"):
                ref=str(item["$ref"]).replace("http:","https:")
                detail=read_json_url(ref,f"espn_fa_detail_{year}_{_espn_id_from_ref(ref)}.json")
            aref=((detail.get("athlete") or detail.get("player") or {}).get("$ref") or "")
            athlete=detail
            if aref:
                aref=str(aref).replace("http:","https:")
                athlete=read_json_url(aref,f"espn_fa_ath_{year}_{_espn_id_from_ref(aref)}.json")
            name=athlete.get("fullName") or athlete.get("displayName") or athlete.get("name")
            if not name:return None
            oldref=((detail.get("oldTeam") or detail.get("team") or {}).get("$ref") or "")
            newid=((detail.get("newTeam") or {}).get("$ref") or "")
            oldteam=ESPN_ID_TEAM.get(_espn_id_from_ref(oldref),"")
            newteam=ESPN_ID_TEAM.get(_espn_id_from_ref(newid),"")
            pos=((athlete.get("position") or {}).get("abbreviation") or "")
            h=((athlete.get("headshot") or {}).get("href") or "")
            ftype=detail.get("type") or {}
            if isinstance(ftype,dict):ftype=ftype.get("abbreviation") or ftype.get("name") or "FA"
            return {"full_name":name,"display_name":name,"position":canonical_pos(pos),"espn_id":str(athlete.get("id") or ""),"headshot_url":h,"prior_team_name":oldteam,"new_team_name":newteam,"fa_type":str(ftype or "FA"),"status":str(ftype or "FA")}
        except Exception:return None
    out=[]
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures=[ex.submit(resolve,i) for i in items]
        for f in as_completed(futures):
            r=f.result()
            if r:out.append(r)
    return out


def merge_free_agents(status_pool:list[dict[str,Any]], espn:list[dict[str,Any]])->list[dict[str,Any]]:
    merged={}
    for r in status_pool+espn:
        k=player_key(r) or norm_name(player_name(r))
        if not k:continue
        old=merged.get(k,{})
        new={**old,**{kk:vv for kk,vv in r.items() if vv not in (None,"")}}
        merged[k]=new
    return sorted(merged.values(),key=lambda r:(group_for_pos(r.get("position")),player_name(r)))


def trade_benchmarks(trade_rows:list[dict[str,str]], year:int) -> list[dict[str,Any]]:
    # Historical transactions are used only to calibrate the model; users may trade any roster player.
    rows=[r for r in trade_rows if intval(r.get("season"))==year]
    out=[]
    for r in rows:
        if not r.get("pfr_name"):continue
        out.append({k:r.get(k) for k in ("trade_id","trade_date","pfr_id","pfr_name","gave","received","pick_season","pick_round","pick_number") if r.get(k) not in (None,"")})
    return out


def build_year(year:int, global_data:dict[str,Any], season_data:dict[int,dict[str,list]], include_espn:bool) -> dict[str,Any]:
    season=year-1
    sd=season_data[season]; prior=season_data.get(season-1,{"stats":[]})
    master_idx=global_data["master_idx"]
    owners=opening_pick_owners(global_data["draft"],global_data["trades"],year)
    draft_class=build_draft_class(global_data["draft"],year,master_idx)
    # Free agency is leaguewide and shared by all 32 clubs for that offseason.
    fa_status=free_agent_status_pool(season_data.get(year,{}).get("roster",[]),master_idx) if year in season_data else []
    fa_espn=espn_free_agents(year) if include_espn else []
    free_agents=merge_free_agents(fa_status,fa_espn)
    teams={}
    for team in TEAMS:
        roster=roster_membership(sd["roster"],sd["weekly"],team,year,master_idx)
        roster=attach_player_evidence(roster,sd["depth"],sd["stats"],sd["snaps"],prior.get("stats",[]),team,season)
        roster=assign_room_order(roster,team,year)
        record,coach=team_record(global_data["games"],season,team)
        teams[team]={
            "rosterSeason":season,
            "roster":[compact_player(p) for p in roster],
            "picks":team_pick_inventory(owners,team,year),
            "priorRecord":record,
            "coach":coach,
            "teamCap":VERIFIED_TEAM_CAP.get(f"{year}|{team}"),
        }
    return {
        "year":year,"rosterSeason":season,"draftClass":draft_class,
        "pickOwners":{str(k):v for k,v in sorted(owners.items())},
        "freeAgents":free_agents,"tradeBenchmarks":trade_benchmarks(global_data["trades"],year),"teams":teams,
    }


def source_manifest() -> dict[str,Any]:
    return {
        "nflverseReleaseBase": RELEASE,
        "nfldataRawBase": RAW,
        "coverage": DATASET_COVERAGE,
        "docs": SOURCE_DOCS,
        "templates": {
            "roster": f"{RELEASE}/rosters/roster_{{season}}.csv",
            "weekly": f"{RELEASE}/weekly_rosters/roster_weekly_{{season}}.csv",
            "depth": f"{RELEASE}/depth_charts/depth_charts_{{season}}.csv",
            "stats": f"{RELEASE}/stats_player/stats_player_reg_{{season}}.csv",
            "snaps": f"{RELEASE}/snap_counts/snap_counts_{{season}}.csv",
            "players": URLS["players"],
            "draft": URLS["draft"],
            "trades": URLS["trades"],
            "games": URLS["games"],
        },
        "depthSchemaNote": "2025+ depth charts use date/team/player_name/pos_abb/pos_slot/pos_rank; 2001-2024 use legacy weekly depth-team fields.",
    }

def parse_years(spec:str)->list[int]:
    if ":" in spec:
        a,b=map(int,spec.split(":",1));return list(range(a,b+1))
    return sorted({int(x) for x in spec.split(",") if x.strip()})


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--years",default="2010:2026")
    ap.add_argument("--espn-free-agents",action="store_true",help="supplement nflverse statuses with ESPN historical free-agent API")
    ap.add_argument("--fixture",action="store_true",help="use repository fixture instead of network")
    args=ap.parse_args(); years=parse_years(args.years)
    if args.fixture:
        fixture=ROOT/"fixtures"/"offline_bundle_fixture.json"
        bundle=json.loads(fixture.read_text())
    else:
        print("Downloading global historical tables...")
        draft=read_csv_url(URLS["draft"],"draft_picks_release.csv")
        trades=read_csv_url(URLS["trades"],"trades.csv")
        games=read_csv_url(URLS["games"],"games.csv")
        try:players=read_csv_url(URLS["players"],"players.csv")
        except Exception as e:
            print(f"WARN players master unavailable: {e}",file=sys.stderr);players=[]
        master_idx=build_master_index(players)
        global_data={"draft":draft,"trades":trades,"games":games,"players":players,"master_idx":master_idx}
        seasons=sorted(set([y-2 for y in years]+[y-1 for y in years]+years))
        season_data={}
        print(f"Downloading {len(seasons)} season data packs...")
        for s in seasons:
            if s<2008:continue
            print(f"  season {s}")
            season_data[s]=download_season_dataset(s)
        bundle={"schemaVersion":2,"generatedAt":time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),"sources":source_manifest(),"years":{}}
        for y in years:
            print(f"Building offseason {y}...")
            bundle["years"][str(y)]=build_year(y,global_data,season_data,args.espn_free_agents)
    json_path=DIST/"offline-data.json";js_path=DIST/"offline-data.js"
    json_text=json.dumps(bundle,separators=(",",":"),ensure_ascii=False)
    json_path.write_text(json_text,encoding="utf-8")
    js_path.write_text("window.FOH_OFFLINE_BUNDLE="+json_text+";\n",encoding="utf-8")
    print(f"Wrote {json_path} ({json_path.stat().st_size/1024/1024:.1f} MB)")

if __name__=="__main__":main()
