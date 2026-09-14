#!/usr/bin/env python3
import argparse,json
from pathlib import Path

def norm(x):return ''.join(c for c in str(x or '').lower() if c.isalnum())
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--file',required=True);ap.add_argument('--years',default='2010:2026');a=ap.parse_args()
    lo,hi=(map(int,a.years.split(':',1)) if ':' in a.years else (None,None));years=list(range(lo,hi+1)) if lo is not None else [int(x) for x in a.years.split(',') if x.strip()]
    b=json.loads(Path(a.file).read_text());errs=[];checks=0;packs=0
    for y in years:
        yd=(b.get('years') or {}).get(str(y)) or {}; teams=yd.get('teams') or {}
        for team,td in teams.items():
            slots=td.get('publishedDepthSlots') or []; provider=td.get('publishedDepthProvider');snap=td.get('publishedDepthSnapshot');source=td.get('publishedDepthSource');checks+=4
            if not slots:errs.append(f'{y} {team}: no published depth slots');continue
            if not provider or not snap or not source:errs.append(f'{y} {team}: missing published source metadata')
            expected='ESPN via nflverse' if y>=2025 else 'NFL Data Exchange via nflverse'
            if provider!=expected:errs.append(f'{y} {team}: provider {provider!r} != {expected!r}')
            roster=td.get('roster') or []; names={norm(p.get('full_name') or p.get('display_name')) for p in roster}; gsis={str(p.get('gsis_id')) for p in roster if p.get('gsis_id')}; espn={str(p.get('espn_id')) for p in roster if p.get('espn_id')}
            orders=[];entries=0
            for s in slots:
                orders.append(int(s.get('slot_order') or 0)); depths=[]
                for p in s.get('players') or []:
                    entries+=1;d=int(p.get('depth') or 0);depths.append(d);checks+=2
                    found=(p.get('gsis_id') and str(p['gsis_id']) in gsis) or (p.get('espn_id') and str(p['espn_id']) in espn) or norm(p.get('name')) in names
                    if not found:errs.append(f"{y} {team} {s.get('slot')}: {p.get('name')} missing from roster")
                if depths and sorted(depths)!=list(range(1,len(depths)+1)):errs.append(f"{y} {team} {s.get('slot')}: depth ranks {depths}")
            if sorted(orders)!=list(range(1,len(orders)+1)):errs.append(f'{y} {team}: slot_order not sequential')
            if len(slots)<10 or entries<20:errs.append(f'{y} {team}: snapshot too small ({len(slots)} slots/{entries} entries)')
            packs+=1
    expected=len(years)*32
    if packs!=expected:errs.append(f'coverage {packs}/{expected} team-year packs')
    print(f'EXACT DEPTH AUDIT: {checks:,} checks; {packs}/{expected} packs; {len(errs)} errors')
    for e in errs:print('ERROR',e)
    if errs:raise SystemExit(1)
if __name__=='__main__':main()
