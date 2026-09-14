#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,importlib.util,math
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("builder",ROOT/"scripts/build_data.py")
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
TEAMS=b.TEAMS
ROOMS=set(b.GROUP_ORDER)

def norm(x):return b.norm_name(x)
def iv(x,d=0):
    try:return int(float(x))
    except:return d
def aliases(team,season):return {x.upper() for x in b.historical_abbr(team,season)}

def pick_snapshot(rows,team,season):
    a=aliases(team,season);modern=season>=2025
    if modern:r=[x for x in rows if str(x.get("team") or "").upper() in a and x.get("dt")]
    else:
        r=[x for x in rows if str(x.get("club_code") or x.get("team") or "").upper() in a]
        reg=[x for x in r if str(x.get("game_type") or "").upper() in {"","REG"}]
        if reg:r=reg
    groups=defaultdict(list)
    for x in r:
        k=str(x.get("dt") or "") if modern else f"{iv(x.get('week'),-1):03d}"
        if k and k!="-01":groups[k].append(x)
    if not groups:raise RuntimeError("no published depth rows")
    snaps=sorted(groups.items(),reverse=True);mx=max(len(v) for _,v in snaps);cut=max(18,math.floor(mx*.72))
    return next(((k,v) for k,v in snaps if len(v)>=cut),snaps[0])

def row_parts(x,modern):
    if modern:
        slot=str(x.get("pos_abb") or x.get("pos_name") or x.get("pos_grp") or "OTHER").upper();slotno=iv(x.get("pos_slot"),1) or 1;rank=iv(x.get("pos_rank"),99) or 99
        name=str(x.get("player_name") or x.get("full_name") or "").strip();pos=str(x.get("pos_abb") or x.get("pos_name") or slot).upper()
        return slot,slotno,rank,name,pos,str(x.get("gsis_id") or ""),str(x.get("espn_id") or ""),str(x.get("jersey_number") or "")
    slot=str(x.get("depth_position") or x.get("position") or "OTHER").upper()
    return slot,1,iv(x.get("depth_team"),99) or 99,str(x.get("full_name") or x.get("football_name") or "").strip(),str(x.get("position") or slot).upper(),str(x.get("gsis_id") or ""),"",str(x.get("jersey_number") or "")

def section(room):
    if room in {"QB","RB","FB","WR","TE","OT","G","C"}:return "Offense"
    if room in {"EDGE","DT","LB","CB","S"}:return "Defense"
    if room in {"K","P","LS"}:return "Special Teams"
    return "Other"

def build_slots(rows,modern):
    grouped=defaultdict(list);meta={};seen=0
    for x in rows:
        slot,slotno,rank,name,pos,gsis,espn,jersey=row_parts(x,modern)
        if not name:continue
        key=(slot,slotno if modern else 1)
        if key not in meta:
            seen+=1;meta[key]=(iv(x.get("pos_grp_id"),999),iv(x.get("pos_id"),999),slotno,seen) if modern else (0,0,0,seen)
        room=b.group_for_pos(slot if b.group_for_pos(slot)!="OTHER" else pos)
        grouped[key].append({"name":name,"jersey":jersey,"depth":rank,"gsis_id":gsis,"espn_id":espn,"source_position":pos,"room":room})
    counts=defaultdict(set)
    for s,n in grouped:counts[s].add(n)
    keys=sorted(grouped,key=lambda k:meta[k]);order={k:i+1 for i,k in enumerate(keys)};out=[]
    for key in keys:
        slot,n=key;players=sorted(grouped[key],key=lambda p:(p["depth"],norm(p["name"])))
        unique=[];ids=set()
        for p in players:
            ident=p["gsis_id"] or p["espn_id"] or norm(p["name"])
            if ident in ids:continue
            ids.add(ident);unique.append(p)
        label=f"{slot} {n}" if len(counts[slot])>1 else slot;room=next((p["room"] for p in unique if p["room"]!="OTHER"),"OTHER")
        out.append({"section":section(room),"slot":label,"source_slot":slot,"source_slot_number":n,"slot_order":order[key],"players":unique[:5]})
    return out

def indexes(roster):
    gsis={};espn={};names={}
    for p in roster:
        if p.get("gsis_id"):gsis[str(p["gsis_id"])]=p
        if p.get("espn_id"):espn[str(p["espn_id"])]=p
        for n in (p.get("full_name"),p.get("display_name"),p.get("player_name")):
            if norm(n):names.setdefault(norm(n),p)
    return gsis,espn,names

def overlay(td,season,team,key,slots):
    # Critical separation: the exact published chart is an immutable source snapshot.
    # It must never add/remove players from the transaction-aware roster. When a
    # source-listed player still exists in this team's clean roster, attach metadata;
    # otherwise keep the source row only in publishedDepthSlots.
    roster=list(td.get("roster") or []);gsis,espn,names=indexes(roster);unique=set();matched=source_only=0
    for p in roster:
        for k in ("published_depth_entries","published_slot","published_depth","published_slot_order","published_snapshot","published_source","published_provider"):p.pop(k,None)
    for s in slots:
        for i in s["players"]:
            ident=i["gsis_id"] or i["espn_id"] or norm(i["name"]);unique.add(ident)
            p=gsis.get(i["gsis_id"]) if i["gsis_id"] else None
            if p is None and i["espn_id"]:p=espn.get(i["espn_id"])
            if p is None:p=names.get(norm(i["name"]))
            if p is None:
                source_only+=1;continue
            matched+=1
            e={"section":s["section"],"slot":s["slot"],"source_slot":s["source_slot"],"source_slot_number":s["source_slot_number"],"depth":i["depth"],"slot_order":s["slot_order"],"room":i["room"]}
            if e not in p.setdefault("published_depth_entries",[]):p["published_depth_entries"].append(e)
    provider="ESPN via nflverse" if season>=2025 else "NFL Data Exchange via nflverse";source=f"{b.RELEASE}/depth_charts/depth_charts_{season}.csv";snap=key if season>=2025 else f"Week {iv(key)} REG"
    for p in roster:
        es=p.get("published_depth_entries") or []
        if not es:continue
        es.sort(key=lambda e:(e["slot_order"],e["depth"]));primary=min(es,key=lambda e:(e["depth"],e["slot_order"]))
        p.update(published_slot=primary["slot"],published_depth=primary["depth"],published_slot_order=primary["slot_order"],published_snapshot=snap,published_source=source,published_provider=provider)
    td.update(roster=roster,rosterSeason=season,publishedDepthSnapshot=snap,publishedDepthProvider=provider,publishedDepthSource=source,publishedDepthSlots=slots,publishedDepthCoverage={"uniquePlayers":len(unique),"matchedCleanRoster":matched,"sourceOnlyPlayers":source_only})
    return len(unique),matched,source_only

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--file",required=True);ap.add_argument("--years",default="2010:2026");a=ap.parse_args()
    years=(lambda lo,hi:list(range(lo,hi+1)))(*[int(x) for x in a.years.split(":",1)]) if ":" in a.years else [int(x) for x in a.years.split(",") if x.strip()]
    path=Path(a.file);bundle=json.loads(path.read_text());errs=[];total=slots_n=unique_n=matched_n=source_only_n=0
    for season in years:
        rows=b.download_season_dataset(season)["depth"];yd=(bundle.get("years") or {}).get(str(season));teams=(yd or {}).get("teams") or {}
        for team in TEAMS:
            try:
                td=teams[team];key,snap=pick_snapshot(rows,team,season);slots=build_slots(snap,season>=2025)
                unique={p["gsis_id"] or p["espn_id"] or norm(p["name"]) for s in slots for p in s["players"]}
                if len(slots)<10 or len(unique)<20:raise RuntimeError(f"small snapshot {len(slots)} slots/{len(unique)} players")
                u,m,so=overlay(td,season,team,key,slots);total+=1;slots_n+=len(slots);unique_n+=u;matched_n+=m;source_only_n+=so
            except Exception as e:errs.append(f"{season} {team}: {e}")
        if yd:yd["rosterSeason"]=season;yd["rosterLabel"]=f"{season} exact published depth snapshot"
    expected=len(years)*len(TEAMS)
    if errs or total!=expected:
        for e in errs:print("ERROR",e)
        raise SystemExit(f"exact depth coverage {total}/{expected}")
    bundle["publishedDepthCharts"]={"version":3,"source":"nflverse depth_charts","providers":{"2010-2024":"NFL Data Exchange via nflverse","2025+":"ESPN via nflverse"},"rule":"Exact published team snapshot shown verbatim; transaction roster remains separate","years":years,"teamPacksApplied":total}
    text=json.dumps(bundle,separators=(",",":"),ensure_ascii=False);path.write_text(text);path.with_suffix(".js").write_text("window.FOH_OFFLINE_BUNDLE="+text+";\n")
    print(f"EXACT DEPTH SNAPSHOTS: {total} packs; {slots_n} slots; {unique_n} players; {matched_n} linked to clean rosters; {source_only_n} source-only")
if __name__=="__main__":main()
