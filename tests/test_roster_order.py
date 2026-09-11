#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('builder',ROOT/'scripts/build_data.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

def player(name,pos):return {'full_name':name,'display_name':name,'position':pos,'status':'ACTIVE','team':'DAL'}

def test_new_schema():
    players=[player('Dak Prescott','QB'),player('Joe Milton III','QB'),player('CeeDee Lamb','WR'),player('George Pickens','WR'),player('Ryan Flournoy','WR'),player('Jake Ferguson','TE'),player('Luke Schoonmaker','TE')]
    # Multiple formation WR slots are all pos_rank=1. Role evidence must flatten them into one room.
    depth=[]
    for day in ('2025-09-01','2025-10-01','2025-11-01'):
        depth += [
          {'team':'DAL','dt':day,'player_name':'Dak Prescott','pos_abb':'QB','pos_rank':'1','pos_slot':'1'},
          {'team':'DAL','dt':day,'player_name':'Joe Milton III','pos_abb':'QB','pos_rank':'2','pos_slot':'1'},
          {'team':'DAL','dt':day,'player_name':'CeeDee Lamb','pos_abb':'WR','pos_rank':'1','pos_slot':'1'},
          {'team':'DAL','dt':day,'player_name':'George Pickens','pos_abb':'WR','pos_rank':'1','pos_slot':'2'},
          {'team':'DAL','dt':day,'player_name':'Ryan Flournoy','pos_abb':'WR','pos_rank':'1','pos_slot':'3'},
          {'team':'DAL','dt':day,'player_name':'Jake Ferguson','pos_abb':'TE','pos_rank':'1','pos_slot':'1'},
          {'team':'DAL','dt':day,'player_name':'Luke Schoonmaker','pos_abb':'TE','pos_rank':'2','pos_slot':'1'},
        ]
    stats=[
      {'player_name':'Dak Prescott','recent_team':'DAL','games':'12','starts':'12','passing_attempts':'430','passing_yards':'3500'},
      {'player_name':'Joe Milton III','recent_team':'DAL','games':'5','starts':'0','passing_attempts':'20','passing_yards':'140'},
      {'player_name':'CeeDee Lamb','recent_team':'DAL','games':'12','starts':'12','targets':'150','receptions':'100','receiving_yards':'1300'},
      {'player_name':'George Pickens','recent_team':'DAL','games':'17','starts':'17','targets':'120','receptions':'75','receiving_yards':'1050'},
      {'player_name':'Ryan Flournoy','recent_team':'DAL','games':'17','starts':'5','targets':'40','receiving_yards':'350'},
      {'player_name':'Jake Ferguson','recent_team':'DAL','games':'16','starts':'16','targets':'95','receiving_yards':'760'},
      {'player_name':'Luke Schoonmaker','recent_team':'DAL','games':'17','starts':'2','targets':'28','receiving_yards':'210'},
    ]
    # Stats matching also indexes normalized player name via player_key fallback.
    players=b.attach_player_evidence(players,depth,stats,[],[], 'Dallas Cowboys',2025)
    b.assign_room_order(players,'Dallas Cowboys',2026)
    rooms={}
    for p in players:rooms.setdefault(p['room_group'],[]).append(p)
    for v in rooms.values():v.sort(key=lambda p:p['room_order'])
    assert [p['full_name'] for p in rooms['QB']][:2]==['Dak Prescott','Joe Milton III']
    assert [p['full_name'] for p in rooms['WR']][:3]==['CeeDee Lamb','George Pickens','Ryan Flournoy']
    assert [p['full_name'] for p in rooms['TE']][:2]==['Jake Ferguson','Luke Schoonmaker']

def test_legacy_schema_all_rooms():
    groups=[('QB','Quarterback'),('RB','Running back'),('WR','Wide receiver'),('TE','Tight end'),('OT','Tackle'),('G','Guard'),('C','Center'),('EDGE','Edge'),('DT','DT'),('LB','LB'),('CB','CB'),('S','Safety'),('K','K'),('P','P'),('LS','LS')]
    players=[];depth=[]
    for pos,label in groups:
        for rank in (1,2,3):
            name=f'{label} {rank}';players.append(player(name,pos));depth.append({'club_code':'DAL','week':'17','game_type':'REG','full_name':name,'depth_position':pos,'depth_team':str(rank)})
    players=b.attach_player_evidence(players,depth,[],[],[],'Dallas Cowboys',2020);b.assign_room_order(players)
    rooms={}
    for p in players:rooms.setdefault(p['room_group'],[]).append(p)
    for group,ps in rooms.items():
        ps.sort(key=lambda p:p['room_order']);assert [p['room_order'] for p in ps]==list(range(1,len(ps)+1)),group

def test_postseason_membership_is_latest():
    rows=[
      {'gsis_id':'00-TEST','team':'DAL','game_type':'REG','week':'18','full_name':'Test Player','position':'WR'},
      {'gsis_id':'00-TEST','team':'PHI','game_type':'POST','week':'1','full_name':'Test Player','position':'WR'},
    ]
    latest=b.latest_weekly_membership(rows)
    assert latest['00-TEST']['team']=='PHI', latest['00-TEST']


def main():
    for _ in range(5):
        test_new_schema();test_legacy_schema_all_rooms();test_postseason_membership_is_latest()
    print('ROSTER TESTS: 5 passes, all position rooms, legacy + 2025+ schemas: PASS')
if __name__=='__main__':main()
