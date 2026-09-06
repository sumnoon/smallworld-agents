// Offline composition using the actual application renderer, not browser automation.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
const require=createRequire(import.meta.url);
const {createCanvas,loadImage}=require(process.env.VIDEO_CANVAS_MODULE||'@napi-rs/canvas');
const root=path.resolve(import.meta.dirname,'../..');
const build=path.join(root,'.video-build');
const media=path.join(root,'docs/media');
const demo=JSON.parse(fs.readFileSync(path.join(build,'demo.json'),'utf8'));
const scenes=JSON.parse(fs.readFileSync(path.join(build,'timeline.json'),'utf8'));
const layout=JSON.parse(fs.readFileSync(path.join(root,'scenarios/neighborhood.json'),'utf8'));
const manifest=JSON.parse(fs.readFileSync(path.join(root,'assets/manifest.json'),'utf8'));
const context={window:{},ResizeObserver:class{observe(){}},devicePixelRatio:1,requestAnimationFrame(){}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root,'client/renderer.js'),'utf8'),context);
const map=createCanvas(800,570),portrait=createCanvas(130,150);
map.getBoundingClientRect=()=>({width:800,height:570});map.addEventListener=()=>{};
const renderer=new context.window.SmallworldRenderer(map,portrait,layout,manifest,()=>{},()=>{});
for(const [id,sheet]of Object.entries(manifest.sheets))renderer.images[id]=await loadImage(path.join(root,'assets',sheet.file));
renderer.ready=true;renderer.resize();renderer.fit();renderer.originY=55;
const canvas=createCanvas(1280,720),c=canvas.getContext('2d');
const C={paper:'#f5f3e9',ink:'#284b3e',muted:'#72816c',accent:'#be865c',line:'#dce1d0'};
function rect(x,y,w,h,r,fill){c.fillStyle=fill;c.beginPath();c.roundRect(x,y,w,h,r);c.fill();}
function text(value,x,y,size=20,color=C.ink,font='Segoe UI',weight='400'){c.fillStyle=color;c.font=`${weight} ${size}px "${font}"`;c.textAlign='left';c.fillText(value,x,y);}
function wrap(value,width,size=22,font='Segoe UI'){c.font=`400 ${size}px "${font}"`;let lines=[],line='';for(const word of value.split(/\s+/)){const next=line?line+' '+word:word;if(c.measureText(next).width>width&&line){lines.push(line);line=word;}else line=next;}if(line)lines.push(line);return lines;}
const ease=x=>x*x*(3-2*x);
function stateFor(scene,u){const [lo,hi]=demo.sections[scene.id];const index=lo+(hi-lo)*Math.min(1,u*(scene.id==='delivery'?1.3:scene.id==='conversation'?1.2:1));const i=Math.floor(index),v=index-i,a=demo.frames[i],b=demo.frames[Math.min(hi,i+1)];return {...a,agents:a.agents.map((agent,k)=>({...agent,x:agent.x+(b.agents[k].x-agent.x)*v,y:agent.y+(b.agents[k].y-agent.y)*v}))};}
function cardTitle(label,x,y){text(label,x,y,12,C.muted,'Segoe UI','600');}
function draw(time){
 const scene=scenes.find(s=>time<s.end)||scenes.at(-1),index=scenes.indexOf(scene),local=time-scene.start,u=Math.max(0,Math.min(1,local/scene.duration));
 c.fillStyle=C.paper;c.fillRect(0,0,1280,720);
 const bg=c.createRadialGradient(895,330,20,890,340,530);bg.addColorStop(0,'#dfe8cf');bg.addColorStop(1,C.paper);c.fillStyle=bg;c.fillRect(400,70,880,570);
 rect(50,30,32,36,10,C.ink);text('S',58,57,26,'#fff6df','Georgia');text('SMALLWORLD AGENTS',98,54,13,C.ink,'Segoe UI','600');
 text('A GUIDED INTRODUCTION',1040,54,11,C.muted,'Segoe UI','600');
 const state=stateFor(scene,u);renderer.selected=scene.id==='delivery'?'samir':scene.id==='memory'?'elena':'maya';
 renderer.setState(state);renderer.display=Object.fromEntries(state.agents.map(a=>[a.id,{x:a.x,y:a.y}]));renderer.clock=time;
 renderer.bubbles=scene.id==='conversation'||scene.id==='delivery';renderer.draw();
 c.save();c.beginPath();c.rect(425,85,855,500);c.clip();c.globalAlpha=['memory','ollama'].includes(scene.id)?.48:1;c.drawImage(map,440,80);c.restore();
 const reveal=ease(Math.min(1,Math.max(0,local/.5)));c.save();c.globalAlpha=reveal;c.translate(-12*(1-reveal),0);
 text(scene.eyebrow,54,132,11,C.accent,'Segoe UI','600');
 const titleSize=scene.id==='residents'?43:scene.id==='welcome'?56:51;
 scene.title.forEach((line,i)=>text(line,52,203+i*61,titleSize,C.ink,'Georgia'));
 const bodyY=218+scene.title.length*61;
 scene.body.split('\n').forEach((line,i)=>{const lines=wrap(line,380,17);lines.forEach((l,j)=>text(l,54,bodyY+i*29+j*24,17,C.muted));});
 if(scene.id==='start'){rect(54,bodyY+80,253,46,10,C.ink);text('OPEN THE PROJECT  ↗',76,bodyY+109,13,'#fff7e5','Segoe UI','600');}
 if(scene.id==='residents'){
  const names=['Maya','Noah','Elena','Samir','Jun'];names.forEach((name,i)=>{const x=54+(i%3)*111,y=bodyY+83+Math.floor(i/3)*40;rect(x,y-23,99,31,15,'#e4ebd8');text(name,x+14,y-2,14,C.ink);});
 }
 if(scene.id==='conversation'){
  rect(668,410,475,125,15,'#fffdf4f2');cardTitle('SAY HELLO',693,438);
  text('Alex: Hello Maya, how is your morning?',693,466,17);
  const utterance=[...state.events].find(e=>e.kind==='dialogue'&&e.actor==='maya'&&(e.payload.recipients||[]).includes('visitor'));
  if(utterance)wrap(utterance.text,420,16).slice(0,2).forEach((line,i)=>text(line,693,493+i*22,16,C.muted));
 }
 if(scene.id==='delivery'){
  const task=state.tasks.find(t=>t.agent==='samir');const step=task?.step||0;
  rect(710,424,500,119,15,'#fffdf4f2');cardTitle('SAMIR’S REQUEST',735,452);text('Bring a coffee to Elena',735,481,22,C.ink,'Georgia');
  const labels=['Collect','Find Elena','Hand over'];labels.forEach((label,i)=>{rect(735+i*150,496,137,4,2,step>i?'#6e9359':'#dfe5d4');text(label,735+i*150,522,12,step>i?C.ink:C.muted);});
  if(task?.status==='completed'){rect(1080,443,106,26,13,'#dfeccd');text('DELIVERED',1094,461,11,C.ink,'Segoe UI','600');}
 }
 if(scene.id==='memory'){
  rect(677,157,531,345,19,'#fffdf4');cardTitle('ELENA / PERSONAL MEMORY',704,190);text('A coffee. A remembered moment.',704,226,25,C.ink,'Georgia');
  const memory=demo.detail.memories.find(m=>m.text.includes('brought me coffee'));
  rect(704,251,477,105,12,'#edf2e1');text('OBSERVATION',724,276,11,C.muted,'Segoe UI','600');
  wrap(memory?.text||'Samir brought me coffee.',430,21).forEach((line,i)=>text(line,724,306+i*27,21));
  text('Linked to an actual handoff event',724,341,13,C.muted);
  text('Observations  ·  Conversations  ·  Reflections',704,396,16,C.muted);text('Personal context for the next interaction.',704,443,18);
 }
 if(scene.id==='ollama'){
  rect(677,157,531,345,19,'#284b3e');text('CONNECT YOUR LOCAL MODEL',707,194,12,'#b9c8aa','Segoe UI','600');
  text('Ollama',706,248,40,'#fff6df','Georgia');text('gemma4:31b',706,285,25,'#dbe8ce','Consolas');
  text('AGENT_PROVIDER=ollama',706,338,19,'#f1d2a7','Consolas');text('python run.py',706,372,19,'#f1d2a7','Consolas');
  text('No cloud API key required',706,427,18,'#e2e8d8');text('Offline demo also available',706,464,15,'#b9c8aa');
 }
 c.restore();
 // Open captions match the narration. The footage label distinguishes this
 // scripted offline capture from separately tested live Ollama functionality.
 rect(48,587,1184,81,12,'#284b3e');const caption=wrap(scene.voice,1120,22);caption.slice(0,2).forEach((line,i)=>text(line,76,caption.length===1?636:620+i*29,22,'#fff9ed'));
 text('GUIDED OFFLINE DEMO · SIMULATION TIME CONDENSED',52,697,10,C.muted,'Segoe UI','600');
 const pw=272;rect(950,689,pw,3,2,'#dce1d1');rect(950,689,pw*time/scenes.at(-1).end,3,2,C.accent);
 text(`${String(index+1).padStart(2,'0')} / 07`,880,697,10,C.muted);
 const edge=Math.min(1,time/.45,(scenes.at(-1).end-time)/.65);if(edge<1){c.fillStyle=`rgba(245,243,233,${1-Math.max(0,edge)})`;c.fillRect(0,0,1280,720);}
}
const fps=24,duration=scenes.at(-1).end,total=Math.ceil(duration*fps);
const ffmpeg=process.env.VIDEO_FFMPEG;
if(!ffmpeg)throw Error('Set VIDEO_FFMPEG to the ffmpeg executable.');
const output=path.join(media,'smallworld-agents-intro.mp4');
const encoder=spawn(ffmpeg,['-y','-loglevel','error','-f','rawvideo','-pixel_format','rgba','-video_size','1280x720','-framerate',String(fps),'-i','pipe:0','-i',path.join(build,'mix.wav'),'-c:v','libx264','-preset','fast','-crf','25','-pix_fmt','yuv420p','-c:a','aac','-b:a','112k','-movflags','+faststart','-shortest',output],{stdio:['pipe','inherit','inherit']});
const completed=new Promise((resolve,reject)=>{encoder.on('error',reject);encoder.on('close',code=>code===0?resolve():reject(Error('FFmpeg failed '+code)));});
const stills=new Map(scenes.map((s,i)=>[Math.round((s.start+Math.min(s.duration*.75,s.duration-1))*fps),i]));
for(let frame=0;frame<total;frame++){
 draw(frame/fps);
 if(frame===Math.round((scenes[3].end-.5)*fps))fs.writeFileSync(path.join(build,'delivery-complete.png'),canvas.toBuffer('image/png'));
 if(stills.has(frame))fs.writeFileSync(path.join(build,`scene-${stills.get(frame)}.png`),canvas.toBuffer('image/png'));
 if(frame===Math.round(2.8*fps))fs.writeFileSync(path.join(media,'intro-poster.png'),canvas.toBuffer('image/png'));
 const rgba=c.getImageData(0,0,1280,720).data;
 if(!encoder.stdin.write(rgba))await once(encoder.stdin,'drain');
 if(frame%(fps*10)===0)process.stdout.write(`Rendered ${Math.round(frame/fps)} / ${duration.toFixed(1)} seconds\n`);
}
encoder.stdin.end();await completed;
fs.writeFileSync(path.join(media,'intro-transcript.md'),'# Smallworld Agents — Introduction transcript\n\nThis guided offline demo uses original project assets and a recorded simulation run. Narration is locally synthesized; the quiet procedural score was composed for this video.\n\n'+scenes.map(s=>`**${s.start.toFixed(1)}s — ${s.eyebrow}**\n\n${s.voice}\n`).join('\n'));
process.stdout.write(`Created ${output} (${(fs.statSync(output).size/1048576).toFixed(2)} MiB)\n`);
