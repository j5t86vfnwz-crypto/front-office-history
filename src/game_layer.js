// ===== FRONT OFFICE HISTORY: GAME LAYER =====
const FOH_GAME={baselineKey:'',baseline:null,lastEventCount:0};
const FOH_CORE_ROOMS=[
  ['Quarterbacks','QB',1650,1],['Running backs','RB',650,2],['Wide receivers','WR',900,3],['Tight ends','TE',600,2],
  ['Offensive tackles','OT',850,2],['Guards','G',620,2],['Centers','C',620,1],['Edge / defensive ends','EDGE',920,2],
  ['Defensive tackles','DT',720,2],['Linebackers','LB',620,3],['Cornerbacks','CB',760,3],['Safeties','S',650,2]
];
const FOH_VERIFIED_ROOMS={
  '2025|Dallas Cowboys|Wide receivers':['CeeDee Lamb'],
  '2026|Dallas Cowboys|Wide receivers':['CeeDee Lamb','George Pickens']
};
function gameClamp(n,a=0,b=100){return Math.max(a,Math.min(b,Number(n)||0))}
function gameEsc(v){return String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}
function gameScenarioKey(){return `${state.year}|${state.team}`}
function gameGrade(score){score=Number(score)||0;return score>=96?'A+':score>=92?'A':score>=89?'A-':score>=86?'B+':score>=82?'B':score>=79?'B-':score>=75?'C+':score>=70?'C':score>=66?'C-':score>=61?'D+':score>=55?'D':'F'}
function gamePlayerImpact(p){
  const role=Number(p?._role_score)||0,starter=(Number(p?._starter_rate)||0)*180,presence=(Number(p?._depth_presence)||0)*45;
  let extra=0;try{extra=positionRoomEvidence(p)||0}catch{}
  return role+starter+presence+extra*.12;
}
function refineVisibleRoomOrder(players,team=state.team,year=state.year){
  const rooms=new Map();
  for(const p of players||[]){const g=p._roomGroup||groupForPos(playerPosition(p));p._roomGroup=g;if(!rooms.has(g))rooms.set(g,[]);rooms.get(g).push(p)}
  for(const [group,list] of rooms){
    const priority=FOH_VERIFIED_ROOMS[`${year}|${team}|${group}`]||[];
    const priorityMap=new Map(priority.map((name,i)=>[normalizeName(name),i]));
    list.sort((a,b)=>{
      const an=normalizeName(playerName(a)),bn=normalizeName(playerName(b)),aa=priorityMap.has(an),ba=priorityMap.has(bn);
      const at=Number(a._officialDepthTier||99),bt=Number(b._officialDepthTier||99),ah=at<99,bh=bt<99;
      if(ah!==bh)return ah?-1:1;if(at!==bt)return at-bt;
      if(aa!==ba)return aa?-1:1;if(aa&&ba&&priorityMap.get(an)!==priorityMap.get(bn))return priorityMap.get(an)-priorityMap.get(bn);
      const ai=gamePlayerImpact(a),bi=gamePlayerImpact(b);if(Math.abs(ai-bi)>.01)return bi-ai;
      const as=statusPriority(a.status),bs=statusPriority(b.status);if(as!==bs)return as-bs;
      const ao=Number(a.room_order||a._officialRoomOrder||999),bo=Number(b.room_order||b._officialRoomOrder||999);if(ao!==bo)return ao-bo;
      return playerName(a).localeCompare(playerName(b));
    });
    list.forEach((p,i)=>{p._officialRoomOrder=i+1;p.room_order=i+1;p._officialRoomLabel=`${group} ${i+1}`})
  }
  return players
}
function gameRoomMetrics(){
  const roster=currentRoster(),by=new Map();for(const p of roster){const g=groupForPos(playerPosition(p));if(!by.has(g))by.set(g,[]);by.get(g).push(p)}
  return FOH_CORE_ROOMS.map(([group,short,target,count])=>{
    const ps=(by.get(group)||[]).slice().sort((a,b)=>rosterStrength(b)-rosterStrength(a));
    const chosen=ps.slice(0,count),values=chosen.map(p=>modelValue(p));
    const avg=values.length?values.reduce((a,b)=>a+b,0)/Math.max(1,count):0;
    const score=gameClamp(20+(avg/target)*68,12,100);
    return {group,short,target,count,score,players:chosen,best:chosen[0]||null}
  })
}
function gameMetrics(){
  const rooms=gameRoomMetrics();
  const weights={QB:1.45,WR:1.3,OT:1.2,EDGE:1.2,CB:1.15,RB:.85,TE:.85,G:.85,C:.75,DT:.9,LB:.85,S:.85};
  let weight=0,total=0;for(const r of rooms){const w=weights[r.short]||1;weight+=w;total+=r.score*w}
  const rosterScore=weight?total/weight:50;
  const pickValue=(state.picks||[]).reduce((sum,p)=>sum+Math.max(0,pv(Number(p))||0),0)+(state.acquiredFuturePicks||[]).reduce((sum,p)=>sum+(Number(p.value)||0),0);
  const draftScore=gameClamp(42+Math.log10(1+pickValue)*14,35,98);
  const cap=availableCapRoom(),league=LEAGUE_CAP[state.year];
  const capScore=cap==null||!league?68:gameClamp(56+(cap/league)*170,45,98);
  const score=Math.round(rosterScore*.64+draftScore*.22+capScore*.14);
  const moves=(state.events||[]).length,signings=(state.signed||[]).length,drafted=(state.drafted||[]).length;
  const departures=(state.departed?.size||0),futureMoved=(state.futurePicksTraded?.size||0),coachChanged=state.baseCoach&&state.coach!==state.baseCoach?1:0;
  const butterfly=Math.min(100,moves*9+signings*5+drafted*6+departures*4+futureMoved*7+coachChanged*14);
  const level=Math.max(1,1+Math.floor((moves*90+drafted*70+signings*55)/300));
  return {score,grade:gameGrade(score),rosterScore:Math.round(rosterScore),draftScore:Math.round(draftScore),capScore:Math.round(capScore),rooms,pickValue,butterfly,level,moves,signings,drafted}
}
function ensureGameBaseline(){
  if(state.loading||state.error)return;const key=gameScenarioKey();if(FOH_GAME.baselineKey!==key){FOH_GAME.baselineKey=key;FOH_GAME.baseline=gameMetrics();FOH_GAME.lastEventCount=state.events.length}
}
function gameDNA(m){
  const trades=(state.events||[]).filter(e=>/trade/i.test(`${e.title} ${e.detail}`)).length;
  const firsts=(state.picks||[]).filter(p=>Number(p)<=32).length;
  if(m.drafted>=3||firsts>=2)return ['Draft Architect','You are leaning into young assets and draft leverage.'];
  if(m.signings>=3)return ['Market Hunter','You are attacking the veteran market aggressively.'];
  if(trades>=2)return ['Deal Maker','Your alternate timeline is being shaped through trades.'];
  if(availableCapRoom()!=null&&LEAGUE_CAP[state.year]&&availableCapRoom()/LEAGUE_CAP[state.year]>.22)return ['Cap Strategist','You are preserving unusually strong financial flexibility.'];
  return ['Balanced Builder','You are keeping multiple roster-building paths open.']
}
function gameDirectives(m){
  const weakest=[...m.rooms].sort((a,b)=>a.score-b.score)[0];
  const rosterProgress=gameClamp(m.rosterScore);
  const capitalProgress=gameClamp(45+Math.log10(1+m.pickValue)*14);
  const weakestProgress=weakest?gameClamp(weakest.score):70;
  return [
    {title:'Build a playoff-caliber core',detail:`Roster power ${m.rosterScore}/100`,value:rosterProgress},
    {title:'Protect premium draft capital',detail:`Draft leverage ${m.draftScore}/100`,value:capitalProgress},
    {title:`Fix the ${weakest?.short||'weakest'} room`,detail:weakest?`${weakest.group} is your biggest need`:'Keep the roster balanced',value:weakestProgress}
  ]
}
function gameNeedAction(room){
  const hasFA=(state.freeAgents||[]).some(p=>groupForPos(playerPosition(p))===room.group);
  if(hasFA)return ['freeagency','Scan market'];
  return ['draft','Open board']
}
function gameSnapshot(){
  return {
    version:1,year:state.year,team:state.team,signed:state.signed,rosterAdds:state.rosterAdds,departed:[...state.departed],futurePicksTraded:[...state.futurePicksTraded],acquiredFuturePicks:state.acquiredFuturePicks,leagueDeparted:[...state.leagueDeparted],events:state.events,drafted:state.drafted,cpuDrafted:state.cpuDrafted,draftCursor:state.draftCursor,picks:state.picks,pickOwners:[...state.pickOwners.entries()],coach:state.coach,teamCap:state.teamCap
  }
}
function saveGameRun(){try{localStorage.setItem(`foh-run:${gameScenarioKey()}`,JSON.stringify(gameSnapshot()));toast('Franchise checkpoint saved')}catch{toast('Could not save this checkpoint',true)}}
function restoreGameRun(){
  try{
    const raw=localStorage.getItem(`foh-run:${gameScenarioKey()}`);if(!raw){toast('No saved checkpoint for this team and year',true);return}
    const s=JSON.parse(raw);if(Number(s.year)!==state.year||s.team!==state.team)throw new Error('wrong scenario');
    state.signed=s.signed||[];state.rosterAdds=s.rosterAdds||[];state.departed=new Set(s.departed||[]);state.futurePicksTraded=new Set(s.futurePicksTraded||[]);state.acquiredFuturePicks=s.acquiredFuturePicks||[];state.leagueDeparted=new Set(s.leagueDeparted||[]);state.events=s.events||[];state.drafted=s.drafted||[];state.cpuDrafted=s.cpuDrafted||[];state.draftCursor=Number(s.draftCursor)||1;state.picks=(s.picks||[]).map(Number);state.pickOwners=new Map(s.pickOwners||[]);state.coach=s.coach??state.coach;state.teamCap=s.teamCap??state.teamCap;state.outgoing=[];state.incoming=[];
    render();toast('Checkpoint restored');openWarRoom()
  }catch{toast('Saved checkpoint could not be restored',true)}
}
function warRoomHtml(){
  ensureGameBaseline();const m=gameMetrics(),base=FOH_GAME.baseline||m,delta=m.score-base.score,dna=gameDNA(m),needs=[...m.rooms].sort((a,b)=>a.score-b.score).slice(0,5),directives=gameDirectives(m);
  const deltaClass=delta>0?'good':delta<0?'bad':'';const deltaText=delta===0?'Baseline':`${delta>0?'+':''}${delta} vs start`;
  const recent=(state.events||[]).slice(0,6);
  return `<div class="foh-war-backdrop" id="fohWarBackdrop"><aside class="foh-war-room" role="dialog" aria-modal="true" aria-label="GM War Room"><div class="foh-war-top"><div class="foh-war-title"><img src="${logoUrl(state.team)}" alt=""><div><div class="kicker">${state.year} ${gameEsc(historicalName(state.team,state.year))}</div><h2>GM War Room</h2></div></div><div class="foh-war-actions"><button class="btn small" data-game-save>Save checkpoint</button><button class="btn small" data-game-restore>Restore</button><button class="btn small primary foh-close-war" data-game-close>Close</button></div></div><div class="foh-war-body">
  <div class="foh-game-hero"><section class="foh-score-card"><small>Front Office Grade</small><div class="foh-score-big">${m.grade}</div><div class="foh-score-row"><span>GM score <b>${m.score}/100</b></span><span class="foh-score-delta ${deltaClass}">${deltaText}</span></div><div class="foh-score-row" style="margin-top:9px"><span>Level ${m.level}</span><span>${m.moves} decisions</span></div></section><section class="foh-directives"><div class="foh-directives-head"><strong>Owner directives</strong><span>Live objectives</span></div>${directives.map(d=>`<div class="foh-directive"><div class="foh-directive-line"><b>${gameEsc(d.title)}</b><span>${gameEsc(d.detail)}</span></div><div class="foh-progress"><i style="width:${Math.round(gameClamp(d.value))}%"></i></div></div>`).join('')}</section></div>
  <div class="foh-game-grid"><section class="foh-game-panel"><div class="foh-game-panel-head"><strong>Needs Scanner</strong><small>Instant roster diagnosis</small></div><div class="foh-game-panel-body"><div class="foh-needs">${needs.map((r,i)=>{const [route,label]=gameNeedAction(r);const names=r.players.length?r.players.map(playerName).slice(0,2).join(' / '):'No established option';return `<div class="foh-need"><div class="foh-need-rank">${i+1}</div><div><strong>${r.short} · ${gameEsc(r.group)}</strong><small>${gameEsc(names)}</small></div><button class="btn small" data-game-route="${route}">${label}</button></div>`}).join('')}</div></div></section>
  <section class="foh-game-panel"><div class="foh-game-panel-head"><strong>Front Office DNA</strong><small>Your strategy is changing live</small></div><div class="foh-game-panel-body"><div class="foh-dna"><div class="foh-dna-card"><small>Identity</small><b>${gameEsc(dna[0])}</b><p>${gameEsc(dna[1])}</p></div><div class="foh-dna-card"><small>Roster power</small><b>${m.rosterScore}/100</b><p>Based on room strength and premium-position weighting.</p></div><div class="foh-dna-card"><small>Draft leverage</small><b>${m.draftScore}/100</b><p>Values current and acquired future draft assets.</p></div><div class="foh-dna-card"><small>Cap flexibility</small><b>${m.capScore}/100</b><p>${availableCapRoom()==null?'Cap room is not verified for this snapshot.':`${mm(availableCapRoom())} currently available.`}</p></div></div><div class="foh-butterfly"><div class="foh-butterfly-num">${m.butterfly}</div><div><strong>Butterfly Index</strong><p>${m.butterfly<20?'Your timeline is still close to history.':m.butterfly<55?'Your choices are creating a meaningfully different NFL timeline.':'You have pushed this franchise deep into an alternate universe.'}</p></div></div></div></section></div>
  <div class="foh-game-grid"><section class="foh-game-panel"><div class="foh-game-panel-head"><strong>Decision feed</strong><small>Every move changes the model</small></div><div class="foh-game-panel-body"><div class="foh-move-feed">${recent.length?recent.map(e=>`<div class="foh-move"><span class="foh-move-dot"></span><div><strong>${gameEsc(e.title)}</strong><small>${gameEsc(e.detail)}</small></div></div>`).join(''):'<div class="foh-empty-game">Make a trade, signing, pick, or coaching move and it will show up here.</div>'}</div></div></section><section class="foh-game-panel"><div class="foh-game-panel-head"><strong>Quick launch</strong><small>One click to the decision</small></div><div class="foh-game-panel-body"><div class="foh-quick-actions"><button class="foh-quick" data-game-route="roster"><b>Depth Lab</b><small>See corrected room order and roster holes.</small></button><button class="foh-quick" data-game-route="trade"><b>Trade Desk</b><small>Build a realistic package instantly.</small></button><button class="foh-quick" data-game-route="freeagency"><b>Free Agency</b><small>Attack the market by need.</small></button><button class="foh-quick" data-game-route="draft"><b>Draft Room</b><small>Use or trade every selection.</small></button></div></div></section></div>
  </div></aside></div>`
}
function openWarRoom(){if(state.loading||state.error)return;closeCommandPalette();document.querySelector('#fohWarBackdrop')?.remove();document.body.insertAdjacentHTML('beforeend',warRoomHtml())}
function closeWarRoom(){document.querySelector('#fohWarBackdrop')?.remove()}
function gameCommandItems(query=''){
  const q=normalizeName(query),pages=[['overview','Overview','Franchise dashboard'],['roster','Roster','Depth chart and player rooms'],['cap','Cap','Salary-cap room'],['trade','Trade Desk','Build realistic trades'],['freeagency','Free Agency','Leaguewide market'],['draft','Draft Room','Draft and trade picks'],['coaches','Coaches','Hire or fire the head coach'],['timeline','Timeline','Your alternate history'],['sources','Sources','Historical data sources']];
  const items=pages.map(([route,label,detail])=>({type:'route',route,label,detail}));items.unshift({type:'war',label:'GM War Room',detail:'Grade, needs, objectives, Butterfly Index'});
  return q?items.filter(x=>normalizeName(`${x.label} ${x.detail}`).includes(q)):items
}
function renderCommandResults(query=''){
  const box=document.querySelector('#fohCommandResults');if(!box)return;const items=gameCommandItems(query);box.innerHTML=items.map((x,i)=>`<button class="foh-command-item ${i===0?'active':''}" data-command-index="${i}" data-command-type="${x.type}" ${x.route?`data-command-route="${x.route}"`:''}><span><b>${gameEsc(x.label)}</b><small>${gameEsc(x.detail)}</small></span><small>↵</small></button>`).join('')||'<div class="foh-empty-game">No command found.</div>'
}
function openCommandPalette(){if(document.querySelector('#fohCommandBackdrop'))return;document.body.insertAdjacentHTML('beforeend',`<div class="foh-command-backdrop" id="fohCommandBackdrop"><div class="foh-command"><input id="fohCommandInput" placeholder="Jump to roster, draft, trade…" autocomplete="off"><div class="foh-command-results" id="fohCommandResults"></div><div class="foh-command-hint">Enter to open · Esc to close · ⌘K / Ctrl K anywhere</div></div></div>`);renderCommandResults('');setTimeout(()=>document.querySelector('#fohCommandInput')?.focus(),0)}
function closeCommandPalette(){document.querySelector('#fohCommandBackdrop')?.remove()}
function installGameChrome(){
  if(state.loading||state.error)return;ensureGameBaseline();const top=document.querySelector('.top-actions');if(!top)return;const m=gameMetrics();
  let hud=document.querySelector('#fohGameHud');if(!hud){hud=document.createElement('div');hud.id='fohGameHud';hud.className='foh-game-hud';top.prepend(hud)}hud.innerHTML=`<div class="gm-grade">${m.grade}</div><div class="gm-hud-copy"><b>GM Level ${m.level}</b><small>${m.score}/100 · ${m.moves} moves</small></div>`;
  let btn=document.querySelector('#fohWarButton');if(!btn){btn=document.createElement('button');btn.id='fohWarButton';btn.className='btn foh-game-button';btn.innerHTML='<span>War Room</span>';top.append(btn)}
  btn.onclick=openWarRoom;
}
const FOH_BASE_RENDER=render;
render=function(){const result=FOH_BASE_RENDER();requestAnimationFrame(installGameChrome);return result};
document.addEventListener('click',e=>{
  const close=e.target.closest('[data-game-close]');if(close){closeWarRoom();return}
  if(e.target.id==='fohWarBackdrop'){closeWarRoom();return}
  const save=e.target.closest('[data-game-save]');if(save){saveGameRun();return}
  const restore=e.target.closest('[data-game-restore]');if(restore){restoreGameRun();return}
  const route=e.target.closest('[data-game-route]');if(route){state.page=route.dataset.gameRoute;closeWarRoom();render();return}
  if(e.target.id==='fohCommandBackdrop'){closeCommandPalette();return}
  const command=e.target.closest('[data-command-type]');if(command){const type=command.dataset.commandType,routeName=command.dataset.commandRoute;closeCommandPalette();if(type==='war')openWarRoom();else if(routeName){state.page=routeName;render()}return}
});
document.addEventListener('input',e=>{if(e.target.id==='fohCommandInput')renderCommandResults(e.target.value)});
document.addEventListener('keydown',e=>{
  if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();document.querySelector('#fohCommandBackdrop')?closeCommandPalette():openCommandPalette();return}
  if(e.key==='Escape'){closeCommandPalette();closeWarRoom();return}
  if(e.key==='Enter'&&document.activeElement?.id==='fohCommandInput'){const first=document.querySelector('#fohCommandResults .foh-command-item');first?.click()}
});
// ===== END GAME LAYER =====
