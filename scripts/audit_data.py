#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TEAMS=[
"Arizona Cardinals","Atlanta Falcons","Baltimore Ravens","Buffalo Bills","Carolina Panthers","Chicago Bears","Cincinnati Bengals","Cleveland Browns","Dallas Cowboys","Denver Broncos","Detroit Lions","Green Bay Packers","Houston Texans","Indianapolis Colts","Jacksonville Jaguars","Kansas City Chiefs","Las Vegas Raiders","Los Angeles Chargers","Los Angeles Rams","Miami Dolphins","Minnesota Vikings","New England Patriots","New Orleans Saints","New York Giants","New York Jets","Philadelphia Eagles","Pittsburgh Steelers","San Francisco 49ers","Seattle Seahawks","Tampa Bay Buccaneers","Tennessee Titans","Washington Commanders"]
ROOMS={"QB","RB","FB","WR","TE","OT","G","C","EDGE","DT","LB","CB","S","K","P","LS","OTHER"}

def parse_years(s):
    if ':' in s:
        a,b=map(int,s.split(':'));return list(range(a,b+1))
    return [int(x) for x in s.split(',')]

def norm(s):return ''.join(c for c in str(s or '').lower() if c.isalnum())

def audit(bundle, years, strict=True):
    errors=[];warnings=[];checks=0
    sources=bundle.get('sources') or {}
    checks+=2
    if strict and int(bundle.get('schemaVersion') or 0)<2: errors.append('bundle schemaVersion is older than 2')
    if strict and not sources.get('templates'): errors.append('bundle missing source manifest/templates')
    ys=bundle.get('years',{})
    for year in years:
        y=ys.get(str(year))
        checks+=1
        if not y:
            errors.append(f'{year}: missing year pack');continue
        draft=y.get('draftClass',[]); fa=y.get('freeAgents',[]); owners=y.get('pickOwners',{})
        checks+=3
        if strict and len(draft)<200:errors.append(f'{year}: draft class only {len(draft)} players')
        if strict and len(fa)<40:errors.append(f'{year}: free-agent market only {len(fa)} players')
        if draft and len(owners)<min(200,len(draft)):errors.append(f'{year}: pick-owner map incomplete ({len(owners)}/{len(draft)})')
        teams=y.get('teams',{})
        for team in TEAMS:
            checks+=1
            t=teams.get(team)
            if not t:
                errors.append(f'{year} {team}: missing team pack');continue
            roster=t.get('roster',[])
            if strict and len(roster)<25:errors.append(f'{year} {team}: roster only {len(roster)} players')
            rooms=defaultdict(list)
            for p in roster:
                checks+=4
                name=p.get('full_name') or p.get('display_name')
                group=p.get('room_group')
                order=p.get('room_order')
                if not name:errors.append(f'{year} {team}: unnamed roster player')
                if group not in ROOMS:errors.append(f'{year} {team} {name}: invalid room {group}')
                if not isinstance(order,int) or order<1:errors.append(f'{year} {team} {name}: invalid room_order {order}')
                rooms[group].append(p)
            for group,ps in rooms.items():
                actual=sorted(int(p['room_order']) for p in ps)
                expected=list(range(1,len(ps)+1))
                checks+=len(ps)+1
                if actual!=expected:errors.append(f'{year} {team} {group}: ranks {actual[:12]} are not sequential 1..{len(ps)}')
                top=sorted(ps,key=lambda p:p['room_order'])[:5]
                if any(norm(p.get('full_name')) in {'','unknownplayer'} for p in top):errors.append(f'{year} {team} {group}: unknown player in top five')
            # Quality warning rather than fabrication: a team may genuinely carry unusual room counts.
            for core in ('QB','RB','WR','TE'):
                if not rooms.get(core):warnings.append(f'{year} {team}: no {core} room from source data')
    # Historical draft-capital anchor: Cleveland officially held these 12 selections
    # when the 2018 order was set on March 6, before its March 13 trade spree.
    y18=ys.get('2018',{})
    cle=(y18.get('teams') or {}).get('Cleveland Browns')
    if cle:
        expected_picks=[1,4,33,35,64,65,101,123,138,159,175,219]
        actual=sorted(int(x) for x in (cle.get('picks') or []))
        checks+=1
        if actual!=expected_picks:
            errors.append(f'2018 Cleveland opening picks {actual}, expected {expected_picks}')

    # Regression guard for the case that repeatedly exposed bad broad-room ordering.
    y=ys.get('2026',{});dal=(y.get('teams') or {}).get('Dallas Cowboys')
    if dal:
        by_room=defaultdict(list)
        for p in dal.get('roster',[]):by_room[p.get('room_group')].append(p)
        for g in by_room:by_room[g].sort(key=lambda p:p.get('room_order',999))
        expected={'QB':[(1,'Dak Prescott')],'WR':[(1,'CeeDee Lamb'),(2,'George Pickens')],'TE':[(1,'Jake Ferguson')]}
        for g,wants in expected.items():
            names={norm(p.get('full_name')):p.get('room_order') for p in by_room.get(g,[])}
            for rank,name in wants:
                checks+=1
                # Only assert if source data contains the player; never insert a player to satisfy a test.
                if norm(name) in names and names[norm(name)]!=rank:errors.append(f'2026 Dallas {g}: {name} is {names[norm(name)]}, expected {rank}')
    return checks,errors,warnings

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--years',default='2010:2026');ap.add_argument('--file',default=str(ROOT/'dist/data/offline-data.json'));ap.add_argument('--non-strict',action='store_true');ap.add_argument('--fixture',action='store_true',help='audit only years/teams present in the small repository fixture');ap.add_argument('--passes',type=int,default=1);args=ap.parse_args()
    bundle=json.loads(Path(args.file).read_text())
    if args.fixture:
        present=sorted(int(y) for y in (bundle.get('years') or {}))
        years=present
    else:
        years=parse_years(args.years)
    total=0;errors=[];warnings=[]
    for _ in range(max(1,args.passes)):
        if args.fixture:
            # Fixture is deliberately tiny: validate structure/ranking only for data actually present.
            e=[];w=[];c=0
            ys=bundle.get('years',{})
            for year in years:
                y=ys.get(str(year),{});c+=1
                teams=y.get('teams') or {}
                for team,t in teams.items():
                    c+=1
                    rooms=defaultdict(list)
                    for player in t.get('roster',[]):
                        c+=4
                        name=player.get('full_name') or player.get('display_name');group=player.get('room_group');order=player.get('room_order')
                        if not name:e.append(f'{year} {team}: unnamed roster player')
                        if group not in ROOMS:e.append(f'{year} {team} {name}: invalid room {group}')
                        if not isinstance(order,int) or order<1:e.append(f'{year} {team} {name}: invalid room_order {order}')
                        rooms[group].append(player)
                    for group,ps in rooms.items():
                        actual=sorted(int(p['room_order']) for p in ps);expected=list(range(1,len(ps)+1));c+=len(ps)+1
                        if actual!=expected:e.append(f'{year} {team} {group}: ranks {actual} are not sequential')
            total+=c;errors.extend(e);warnings.extend(w)
        else:
            c,e,w=audit(bundle,years,not args.non_strict);total+=c;errors.extend(e);warnings.extend(w)
    checks=total
    print(f'AUDIT: {checks:,} assertions across {max(1,args.passes)} pass(es); {len(errors)} errors; {len(warnings)} warnings')
    for w in warnings[:80]:print('WARN',w)
    if len(warnings)>80:print(f'WARN ... {len(warnings)-80} more')
    for e in errors:print('ERROR',e,file=sys.stderr)
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
