#!/usr/bin/env python3
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("builder",ROOT/"scripts/build_data.py")
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

def main():
    assert b.DATASET_COVERAGE=={"roster":1920,"weekly":2002,"depth":2001,"stats":1999,"snaps":2012}
    u=b.season_urls(2025)
    assert u["roster"].endswith("/rosters/roster_2025.csv")
    assert u["weekly"].endswith("/weekly_rosters/roster_weekly_2025.csv")
    assert u["depth"].endswith("/depth_charts/depth_charts_2025.csv")
    assert u["stats"].endswith("/stats_player/stats_player_reg_2025.csv")
    assert u["snaps"].endswith("/snap_counts/snap_counts_2025.csv")
    assert b.URLS["players"].endswith("/players/players.csv")

    master=b.build_master_index([{'pfr_id':'MayfBa00','display_name':'Baker Mayfield','gsis_id':'00-0034855'}])
    e=b.enrich({'season':'2018','playerid':'MayfBa00','full_name':'Baker Mayfield','position':'QB'},master)
    assert e['pfr_id']=='MayfBa00' and e['gsis_id']=='00-0034855'

    assert b.normalize_status_code('Active')=='ACT'
    assert b.normalize_status_code('Unrestricted Free Agent')=='UFA'
    assert b.normalize_status_code('Restricted Free Agent')=='RFA'
    assert b.normalize_status_code('Exclusive Rights Free Agent')=='ERFA'
    assert b.normalize_status_code('Practice Squad')=='DEV'
    template=(ROOT/'src/index.template.html').read_text(encoding='utf-8')
    assert 'mergeHistoricalRoster(seasonRoster,weeklyRows,state.team,state.year)' in template
    assert 'mergeHistoricalRoster(seasonRows,weeklyRows,team,state.year)' in template
    assert "ESPN season athletes remain the last-resort roster fallback" not in template
    assert '/athletes?limit=200`,`roster-index-' not in template
    assert 'NFLverse weekly historical roster fallback' in template
    print("SOURCE CONTRACT: official nflverse URL templates + coverage: PASS")
if __name__=="__main__": main()
