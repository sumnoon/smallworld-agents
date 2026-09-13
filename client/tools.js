/* Optional controls share the authoritative state and command transport. */
'use strict';
let activeDistrict="park",districtStamp="",liveLayout=null;
let replayFrames=[], replayTimer=null, replayIndex=0, replayRequest=0, lastSpoken=0;
window.townReplay=false;
const downloadJSON=(value,name)=>{const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
$('#room-view').onchange=e=>{if(renderer){renderer.view=e.target.value;renderer.fit();if(renderer.room())renderer.zoom=Math.min(1.6,(renderer.cw-30)/400);}};
$('#enter-room').onclick=()=>{const room=renderer?.room()||'';action({kind:'enter',room});};
async function showReplay(i){if(!replayFrames.length)return;replayIndex=Math.max(0,Math.min(replayFrames.length-1,i));const ticket=++replayRequest;const r=await fetch('/api/replay/'+replayFrames[replayIndex].id);if(!r.ok)throw Error('This recording is no longer available');const frame=await r.json();if(ticket!==replayRequest||!window.townReplay)return;state=frame;renderer.layout=frame.layout;renderer.setState(state);render();$('#replay-slider').value=String(replayIndex);$('#replay-time').textContent='REPLAY · '+formatTime(frame.time);$('#memories').textContent='Memory inspection is available in the live town. Playback shows recorded movement, tasks and events.';$('#plans').textContent='Recorded playback';window.updateTownTools();}
$('#replay-start').onclick=async()=>{try{await command({kind:'pause',paused:true});const response=await fetch('/api/replay');replayFrames=await response.json();if(!replayFrames.length){toast('No recording yet');return;}liveLayout=renderer.layout;window.townReplay=true;window.speechSynthesis?.cancel();$('#replay-slider').max=String(replayFrames.length-1);for(const id of ['replay-slider','replay-play','replay-exit'])$('#'+id).hidden=false;$('#replay-start').hidden=true;await showReplay(0);}catch(e){toast(e.message);}};
$('#replay-slider').oninput=e=>showReplay(Number(e.target.value)).catch(e=>toast(e.message));
$('#replay-play').onclick=()=>{if(replayTimer){clearInterval(replayTimer);replayTimer=null;$('#replay-play').textContent='Play';return;}$('#replay-play').textContent='Pause playback';replayTimer=setInterval(()=>{if(replayIndex>=replayFrames.length-1){$('#replay-play').click();return;}showReplay(replayIndex+1).catch(e=>toast(e.message));},500);};
$('#replay-exit').onclick=()=>{clearInterval(replayTimer);replayTimer=null;replayRequest++;window.townReplay=false;for(const id of ['replay-slider','replay-play','replay-exit'])$('#'+id).hidden=true;$('#replay-start').hidden=false;$('#replay-play').textContent='Play';$('#replay-time').textContent='';state=window.liveTownState||state;if(liveLayout)renderer.layout=liveLayout;renderer.setState(state);renderer.fit();detailStamp=0;render();};
$('#scenario-load').onclick=async()=>{$('#scenario-editor').value=JSON.stringify(await (await fetch('/api/layout')).json(),null,2);};
async function validateScenario(residents){const layout=JSON.parse($('#scenario-editor').value);const response=await fetch('/api/scenario/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({layout,residents})});const result=await response.json();if(!response.ok)throw Error(result.error);$('#scenario-editor').value=JSON.stringify(result.layout,null,2);$('#scenario-status').textContent='Valid scenario: '+(result.layout.residents.length-1)+' residents plus Alex.';return result.layout;}
$('#scenario-expand').onclick=async()=>{try{if(!$('#scenario-editor').value)await $('#scenario-load').onclick();await validateScenario(25);}catch(e){$('#scenario-status').textContent=e.message;}};
$('#scenario-download').onclick=async()=>{try{downloadJSON(await validateScenario(),'my-town.json');}catch(e){$('#scenario-status').textContent=e.message;}};
$('#scenario-import').onchange=async e=>{const f=e.target.files[0];if(!f)return;if(f.size>131072){toast('Scenario must be smaller than 128 KB');return;}$('#scenario-editor').value=await f.text();try{await validateScenario();}catch(error){$('#scenario-status').textContent=error.message;}};
$('#voice').onchange=e=>{lastSpoken=Math.max(0,...(state?.events||[]).map(e=>e.id));if(!e.target.checked)window.speechSynthesis?.cancel();};
const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
if(!Recognition){$('#dictate').disabled=true;$('#dictate').title='Speech recognition is unavailable in this browser';}else{$('#dictate').onclick=()=>{const recognition=new Recognition();recognition.lang='en-US';recognition.onresult=e=>{$('#message').value=e.results[0][0].transcript;$('#message').focus();};recognition.onerror=e=>toast('Dictation: '+e.error);recognition.start();};}
window.updateTownTools=()=>{if(!state)return;
const community=state.community||{},resident=state.agents.find(a=>a.id===selected),beds=Object.values(community.beds||{}),ripe=beds.filter(b=>b.ready_at&&state.time>=b.ready_at).length;
$('#community-status').textContent=`${community.seeds??0} seeds available · ${beds.length} planted beds (${ripe} ripe) · ${community.supplies??0} market supplies · ${resident?.name||'Resident'}: ${resident?.credits??25} credits`;
$('#weather').value=community.weather||'clear';
$('#picnic-progress').innerHTML=state.tasks.filter(t=>t.picnic).slice(-2).map(t=>`<p><strong>${esc(state.agents.find(a=>a.id===t.agent)?.name)}'s picnic · ${esc(t.status)}</strong><br>${esc(t.blocker||t.steps[t.step]||'Meal served')} · helper: ${esc(state.agents.find(a=>a.id===t.picnic.helper)?.name||'looking for a volunteer')} · ${t.picnic.served.length} people served</p>`).join('');
for(const id of ['picnic-start','garden-start','market-start','weather'])$('#'+id).disabled=window.townReplay;

const districts=renderer.layout.districts||[{name:'Village',place:'park',color:'#6d9064'}],stamp=JSON.stringify(districts);
if(stamp!==districtStamp){districtStamp=stamp;$('#district-links').innerHTML=districts.map(d=>`<button data-district="${esc(d.place)}" style="--district-color:${esc(d.color)}">${esc(d.name)}</button>`).join('');}
if(!renderer.layout.places[activeDistrict])activeDistrict='park';
const current=districts.find(d=>d.place===activeDistrict);$('#walk-district').textContent='Walk to '+(current?.name||activeDistrict);document.querySelectorAll('[data-district]').forEach(b=>b.classList.toggle('active',b.dataset.district===activeDistrict));
$('#proposals').innerHTML=(state.proposals||[]).filter(p=>p.status==='proposed').map(p=>`<p>${esc(p.request)} <button data-accept-proposal="${esc(p.id)}">Accept task</button> <button data-decline-proposal="${esc(p.id)}">Decline</button></p>`).join('')||'No suggestions waiting.';
$('#appointments').innerHTML=(state.appointments||[]).map(a=>`<p>${esc(a.place)} · ${formatTime(a.at)} · ${esc(a.status)}<br>${a.invited.length}/${a.guests.length} invited · ${a.accepted.length-1} guests accepted · ${a.attended.filter(id=>id!==a.host).length} guests attended</p>`).join('')||'No meetings scheduled.';
$('#metrics').textContent=JSON.stringify({memory:state.memory,queued:state.queue,operations:state.metrics,modelTiming:state.model.last_timing},null,2);
const room=renderer?.room(),objects=renderer?.layout.interiors?.[room]?.objects||[];$('#object-tools').innerHTML=objects.map(o=>`<button data-object="${esc(o.id)}">Ask ${esc(state.agents.find(a=>a.id===selected)?.name||'resident')} to use ${esc(o.name)}</button>`).join('')||'Choose an interior view to see its objects.';
if($('#voice').checked&&!window.townReplay&&window.speechSynthesis){const fresh=state.events.filter(e=>e.id>lastSpoken&&e.kind==='dialogue'&&e.actor===selected).sort((a,b)=>a.id-b.id);lastSpoken=Math.max(lastSpoken,...state.events.map(e=>e.id));if(!speechSynthesis.speaking&&fresh.length){const line=fresh.at(-1);speechSynthesis.speak(new SpeechSynthesisUtterance(line.text));}}
};
$('#object-tools').onclick=e=>{const b=e.target.closest('[data-object]');if(b)action({kind:'object',agent:selected,object:b.dataset.object,room:renderer.room()});};

$('#proposals').onclick=e=>{const a=e.target.closest('[data-accept-proposal]'),d=e.target.closest('[data-decline-proposal]');if(a)action({kind:'accept_proposal',proposal:a.dataset.acceptProposal});if(d)action({kind:'decline_proposal',proposal:d.dataset.declineProposal});};

$('#district-links').onclick=e=>{const b=e.target.closest('[data-district]');if(!b||!renderer)return;activeDistrict=b.dataset.district;renderer.focusPlace(activeDistrict);$('#room-view').value='';window.updateTownTools();};
$('#walk-district').onclick=()=>action({kind:'travel',place:activeDistrict});
$('#place-labels').onchange=e=>{if(renderer)renderer.placeLabels=e.target.checked;};
$('#find-resident').onclick=()=>{const a=state?.agents.find(a=>a.id===selected);if(!a||!renderer)return;if(a.room){renderer.view=a.room;renderer.fit();$('#room-view').value=a.room;}else{renderer.focusPoint(a.x,a.y);$('#room-view').value='';}};

$('#picnic-start').onclick=()=>action({kind:'task',agent:selected,text:'Organize a picnic'});
$('#garden-start').onclick=()=>action({kind:'task',agent:selected,text:'Plant vegetables then water vegetables then harvest vegetables'});
$('#market-start').onclick=()=>action({kind:'task',agent:selected,text:'Buy picnic supplies'});
$('#weather').onchange=e=>action({kind:'weather',weather:e.target.value});
