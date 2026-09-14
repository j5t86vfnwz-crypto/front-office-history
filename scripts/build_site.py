#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src/index.template.html'
GAME_CSS=ROOT/'src/game_layer.css'
GAME_JS=ROOT/'src/game_layer.js'
POLISH_CSS=ROOT/'src/polish_layer.css'
POLISH_JS=ROOT/'src/polish_layer.js'
PUBLISHED_CSS=ROOT/'src/published_depth_layer.css'
PUBLISHED_JS=ROOT/'src/published_depth_layer.js'
DIST=ROOT/'dist'
DIST.mkdir(parents=True,exist_ok=True)
html=SRC.read_text(encoding='utf-8')

# Keep the approved visual language in the frozen template while layering the
# decision-game UI, usability polish, and exact-source depth chart renderer in
# small, independently testable files.
for source, marker in [
    (GAME_CSS,'/* Front Office History — game layer */'),
    (POLISH_CSS,'/* Front Office History — usability polish layer */'),
    (PUBLISHED_CSS,'/* Front Office History — exact published depth chart */'),
]:
    if source.exists() and marker not in html:
        html=html.replace('</style>',source.read_text(encoding='utf-8')+'\n</style>',1)

# Bundle is loaded before the frozen application script. This works from file:// and HTTPS.
if '<script src="data/offline-data.js"></script>' not in html:
    html=html.replace('<script>','<script src="data/offline-data.js"></script>\n<script>',1)

helper=r'''
// ===== OFFLINE DATA LAYER (generated project integration) =====
function bundledYearData(year=state.year){return window.FOH_OFFLINE_BUNDLE?.years?.[String(year)]||null}
function bundledTeamData(team=state.team,year=state.year){return bundledYearData(year)?.teams?.[team]||null}
function hydrateBundledPlayer(raw){
  const p={...raw};
  p._officialRoomOrder=Number(raw._officialRoomOrder||raw.room_order||99);
  p._officialDepthTier=Number(raw._officialDepthTier||99);
  p._roomGroup=raw._roomGroup||({QB:'Quarterbacks',RB:'Running backs',FB:'Fullbacks',WR:'Wide receivers',TE:'Tight ends',OT:'Offensive tackles',G:'Guards',C:'Centers',EDGE:'Edge / defensive ends',DT:'Defensive tackles',LB:'Linebackers',CB:'Cornerbacks',S:'Safeties',K:'Kickers',P:'Punters',LS:'Long snappers',OTHER:'Other'}[raw.room_group]||groupForPos(raw.position));
  return p
}
function loadBundledScenario(){
  const yd=bundledYearData(),td=bundledTeamData();
  if(!yd||!td)return false;
  state.rosterSeason=Number(td.rosterSeason||state.year);
  const hydrated=(td.roster||[]).map(hydrateBundledPlayer);
  state.teamRoster=hydrated.sort(sortRoster);state.allRoster=state.teamRoster;
  state.draftClass=(yd.draftClass||[]).map(p=>({...p,actual_pick:Number(p.actual_pick),round:Number(p.round)})).sort((a,b)=>a.actual_pick-b.actual_pick);
  state.pickOwners=new Map(Object.entries(yd.pickOwners||{}).map(([k,v])=>[Number(k),v]));state.basePickOwners=new Map(state.pickOwners);
  state.picks=[...(td.picks||[])].map(Number).sort((a,b)=>a-b);state.basePicks=[...state.picks];
  state.freeAgents=(yd.freeAgents||[]).map(hydrateBundledPlayer);
  state.tradeMarket=yd.tradeBenchmarks||[];
  state.teamCap=td.teamCap??null;state.priorRecord=td.priorRecord||'—';state.coach=td.coach||'—';state.baseCoach=state.coach;
  state.depthMap=new Map();state.dataFlags={roster:!!state.teamRoster.length,depth:!!td.publishedDepthSlots?.length,draft:!!state.draftClass.length,trades:true,freeagency:!!state.freeAgents.length,players:true};
  state.masterPlayerIndex=buildMasterPlayerIndex([]);state.playerIndex=buildPlayerIndex([...state.teamRoster,...state.draftClass,...state.freeAgents]);
  state.loading=false;state.error='';state.offlineMode=true;updateChrome();render();return true
}
function loadBundledTradeTarget(team){
  const td=bundledTeamData(team,state.year);if(!td)return false;
  const expected=team;state.tradeTargetLoading=false;state.tradeTargetError='';
  const hydrated=(td.roster||[]).map(hydrateBundledPlayer);
  state.tradeTargetRoster=hydrated.filter(p=>!state.leagueDeparted.has(`${expected}|${playerKey(p)}`)).sort(sortRoster);
  render();return true
}
// ===== END OFFLINE DATA LAYER =====
'''
needle='async function loadScenario(){'
if helper.strip() not in html:
    html=html.replace(needle,helper+'\n'+needle,1)

if GAME_JS.exists():
    game_js=GAME_JS.read_text(encoding='utf-8')
    old_order="if(ah!==bh)return ah?-1:1;if(at!==bt)return at-bt;\n      if(aa!==ba)return aa?-1:1;if(aa&&ba&&priorityMap.get(an)!==priorityMap.get(bn))return priorityMap.get(an)-priorityMap.get(bn);"
    new_order="if(aa!==ba)return aa?-1:1;if(aa&&ba&&priorityMap.get(an)!==priorityMap.get(bn))return priorityMap.get(an)-priorityMap.get(bn);\n      if(ah!==bh)return ah?-1:1;if(at!==bt)return at-bt;"
    if old_order not in game_js:raise SystemExit('Expected roster-order comparator not found in game layer')
    game_js=game_js.replace(old_order,new_order,1)
    marker='// ===== FRONT OFFICE HISTORY: GAME LAYER ====='
    if marker not in html:html=html.replace(needle,game_js+'\n'+needle,1)

if POLISH_JS.exists():
    polish_js=POLISH_JS.read_text(encoding='utf-8');marker='// ===== FRONT OFFICE HISTORY: USABILITY POLISH ====='
    if marker not in html:html=html.replace(needle,polish_js+'\n'+needle,1)

if PUBLISHED_JS.exists():
    published_js=PUBLISHED_JS.read_text(encoding='utf-8');marker='// ===== FRONT OFFICE HISTORY: EXACT PUBLISHED DEPTH CHART ====='
    if marker not in html:html=html.replace(needle,published_js+'\n'+needle,1)

scenario_line="const season=state.year-1;state.rosterSeason=season;"
replacement=scenario_line+"\n  if(window.FOH_OFFLINE_BUNDLE){if(loadBundledScenario())return;state.loading=false;state.error=`Offline data pack missing for ${state.year} ${historicalName(state.team,state.year)}.`;updateChrome();render();return;}"
if replacement not in html:html=html.replace(scenario_line,replacement,1)
trade_guard="if(!team||team===state.team){state.tradeTargetRoster=[];state.tradeTargetError='Choose another team.';state.tradeTargetLoading=false;render();return}"
trade_replace=trade_guard+"\n  if(window.FOH_OFFLINE_BUNDLE&&loadBundledTradeTarget(team))return;"
if trade_replace not in html:html=html.replace(trade_guard,trade_replace,1)
html=html.replace('Historical data layer','Bundled historical data',1)
(DIST/'index.html').write_text(html,encoding='utf-8')
print('Wrote',DIST/'index.html')
