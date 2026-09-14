// ===== FRONT OFFICE HISTORY: EXACT PUBLISHED DEPTH CHART =====
const FOH_BASE_ROSTER_RENDER = roster;

function publishedEsc(value){
  return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
function publishedTeamPack(){
  try{return typeof bundledTeamData==='function'?bundledTeamData():null}catch{return null}
}
function publishedPlayerMap(){
  const map=new Map();
  for(const p of currentRoster()){
    const names=[playerName(p),p.display_name,p.full_name,p.player_name].filter(Boolean);
    for(const n of names)map.set(normalizeName(n),p);
  }
  return map;
}
function publishedPlayerCell(slot,item,playerMap){
  const name=String(item?.name||'').trim(), key=normalizeName(name), p=playerMap.get(key);
  const jersey=String(item?.jersey||p?.jersey_number||'').trim();
  const depth=Number(item?.depth)||0;
  const status=p?.status||'';
  const action=p?`<button class="btn link published-trade" data-add-player="${encodeURIComponent(playerKey(p))}">Trade</button>`:'';
  return `<td class="published-depth-cell" data-published-player="${publishedEsc(key)}" data-depth="${depth}" data-slot="${publishedEsc(slot.slot)}">
    <div class="published-player-card">
      <span class="published-number">${publishedEsc(jersey||'—')}</span>
      <div class="published-player-copy"><strong>${publishedEsc(name)}</strong><small>${publishedEsc(slot.slot)} ${depth}${status?` · ${publishedEsc(status)}`:''}</small></div>
      ${action}
    </div>
  </td>`;
}
function publishedEmptyCell(){return '<td class="published-depth-cell empty"></td>'}
function publishedSection(section,slots,playerMap,q){
  const visible=slots.filter(slot=>{
    if(!q)return true;
    if(normalizeName(slot.slot).includes(q))return true;
    return (slot.players||[]).some(item=>normalizeName(item.name).includes(q));
  });
  if(!visible.length)return '';
  return `<section class="panel published-depth-panel">
    <div class="panel-head"><div><h3>${publishedEsc(section)}</h3><p>Exact source slots and published Player 1–5 order</p></div></div>
    <div class="table-wrap"><table class="published-depth-table">
      <thead><tr><th>Pos</th><th>Player 1</th><th>Player 2</th><th>Player 3</th><th>Player 4</th><th>Player 5</th></tr></thead>
      <tbody>${visible.map(slot=>{
        const cells=(slot.players||[]).slice(0,5).map(item=>publishedPlayerCell(slot,item,playerMap));
        while(cells.length<5)cells.push(publishedEmptyCell());
        return `<tr><td class="published-slot"><strong>${publishedEsc(slot.slot)}</strong></td>${cells.join('')}</tr>`;
      }).join('')}</tbody>
    </table></div>
  </section>`;
}
function publishedDepthRoster(){
  const td=publishedTeamPack();
  const slots=td?.publishedDepthSlots||[];
  if(!slots.length)return FOH_BASE_ROSTER_RENDER();
  const q=normalizeName(state.rosterSearch);
  const playerMap=publishedPlayerMap();
  const sections=[];
  for(const section of ['Offense','Defense','Special Teams','Other']){
    const html=publishedSection(section,slots.filter(s=>(s.section||'Other')===section),playerMap,q);
    if(html)sections.push(html);
  }
  const snapshot=td.publishedDepthSnapshot||'Published snapshot';
  const provider=td.publishedDepthProvider||'Published depth-chart source';
  const source=td.publishedDepthSource||'';
  const sourceLink=source?`<a href="${publishedEsc(source)}" target="_blank" rel="noopener">Source data</a>`:'';
  return pageHead('Personnel','Roster',`Published depth chart · ${snapshot}`)+
    `<div class="toolbar"><input class="search" id="rosterSearch" placeholder="Search depth chart" value="${publishedEsc(state.rosterSearch)}"><div class="segments"><button data-roster-view="depth" class="active">Depth chart</button><button data-roster-view="contract">Under contract</button><button data-roster-view="fa">Pending free agents</button></div></div>`+
    `<div class="published-depth-source"><div><strong>${publishedEsc(provider)}</strong><span>${publishedEsc(snapshot)} · No model re-ranking</span></div>${sourceLink}</div>`+
    sections.join('');
}
roster=function(){
  if(state.rosterView==='depth'){
    const td=publishedTeamPack();
    if(td?.publishedDepthSlots?.length)return publishedDepthRoster();
  }
  return FOH_BASE_ROSTER_RENDER();
};
// ===== END EXACT PUBLISHED DEPTH CHART =====
