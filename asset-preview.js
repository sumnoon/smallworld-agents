'use strict';
const manifest=window.ASSET_MANIFEST, images={}, canvas=document.querySelector('#world'),ctx=canvas.getContext('2d'),portrait=document.querySelector('#portrait'),pc=portrait.getContext('2d');
const profiles=[['maya','Maya','Cafe owner · A warm welcome and a fresh cup.'],['noah','Noah','Teacher · Always curious about his neighbors.'],['elena','Elena','Gardener · Keeping the neighborhood green.'],['samir','Samir','Shopkeeper · A familiar face on every errand.'],['jun','Jun','Artist · Finding inspiration in everyday life.'],['visitor','Alex','Your visitor · A new story in the neighborhood.']];
let selected='maya',direction=0,paused=false,clock=0,last=0,zoom=1,pan={x:0,y:0},cw=1000,ch=590,drag=null,ready=false;
const TW=64,TH=32,N=16;
const iso=(x,y)=>({x:(x-y)*TW/2,y:(x+y)*TH/2});
const screen=p=>({x:cw/2+pan.x+p.x*zoom,y:65+pan.y+p.y*zoom});
const buildings=[{id:'cafe',x:3,y:4,index:0},{id:'shop',x:11,y:4,index:1},{id:'home-green',x:4,y:11,index:2},{id:'home-blue',x:12,y:11,index:3}];
const blocked=new Set();for(const b of buildings)for(let x=b.x-2;x<=b.x+1;x++)for(let y=b.y-2;y<=b.y+1;y++)blocked.add(`${x},${y}`);
const staticProps=[{i:0,x:1,y:7,w:95},{i:1,x:14,y:7,w:72},{i:0,x:8,y:14,w:92},{i:2,x:6,y:1,w:39},{i:3,x:2,y:6,w:32},{i:4,x:8,y:7,w:75},{i:4,x:8,y:10,w:75},{i:5,x:3,y:6,w:41},{i:6,x:3,y:7,w:26},{i:7,x:6,y:5,w:25},{i:7,x:10,y:7,w:25},{i:8,x:5,y:6,w:66},{i:15,x:9,y:5,w:42},{i:14,x:13,y:6,w:24}];
const routes=[[[6,6],[7,7],[8,8],[6,8]],[[9,8],[10,8],[10,7],[8,7]],[[7,12],[7,14],[9,14],[9,13]],[[12,6],[14,6],[14,8],[11,7]],[[1,8],[2,8],[3,8],[1,7]],[[8,11],[8,12]]];
const agents=profiles.map(([id],i)=>({id,x:routes[i][0][0],y:routes[i][0][1],route:routes[i],leg:0,path:[],face:0,moving:false,wait:i*.7}));
function pathfind(start,end){
  const sx=Math.round(start.x),sy=Math.round(start.y),ex=Math.round(end.x),ey=Math.round(end.y),key=(x,y)=>`${x},${y}`,valid=(x,y)=>x>=0&&x<N&&y>=0&&y<N&&!blocked.has(key(x,y));
  if(!valid(ex,ey))return [];
  const open=[{x:sx,y:sy,g:0,f:0,parent:null}],best=new Map([[key(sx,sy),0]]);
  while(open.length){open.sort((a,b)=>a.f-b.f);const node=open.shift();if(node.x===ex&&node.y===ey){const path=[];for(let p=node;p.parent;p=p.parent)path.unshift({x:p.x,y:p.y});return path;}
    for(let dx=-1;dx<=1;dx++)for(let dy=-1;dy<=1;dy++){if(!dx&&!dy)continue;const x=node.x+dx,y=node.y+dy;if(!valid(x,y)||(dx&&dy&&(!valid(node.x+dx,node.y)||!valid(node.x,node.y+dy))))continue;const g=node.g+Math.hypot(dx,dy),k=key(x,y);if(g>=(best.get(k)??Infinity))continue;best.set(k,g);open.push({x,y,g,f:g+Math.hypot(ex-x,ey-y),parent:node});}
  }return [];
}
function select(id){selected=id;document.querySelectorAll('#residents button').forEach(b=>b.classList.toggle('active',b.dataset.id===id));const p=profiles.find(p=>p[0]===id);document.querySelector('#name').textContent=p[1];document.querySelector('#role').textContent=p[2];}
for(const [id,name] of profiles){const b=document.createElement('button');b.textContent=name;b.dataset.id=id;b.onclick=()=>select(id);document.querySelector('#residents').append(b);}
const dirNames=['SOUTH','SOUTHWEST','WEST','NORTHWEST','NORTH','NORTHEAST','EAST','SOUTHEAST'];
function setDirection(i){direction=i;document.querySelector('#direction-label').textContent=dirNames[i];document.querySelectorAll('#directions button').forEach((b,j)=>b.classList.toggle('active',i===j));}
manifest.directions.forEach((d,i)=>{const b=document.createElement('button');b.textContent=d;b.onclick=()=>setDirection(i);document.querySelector('#directions').append(b);});
select(selected);setDirection(0);
function sprite(c,id,index,x,y,width,anchorX=.5,anchorY=1,flip=false){const s=manifest.sheets[id],f=s.frames[index],height=width*f.height/f.width;c.save();c.translate(x,y);if(flip)c.scale(-1,1);c.drawImage(images[id],f.x,f.y,f.width,f.height,-width*anchorX,-height*anchorY,width,height);c.restore();}
function character(c,id,face,x,y,height,animate){const s=manifest.sheets[id],map=s.facing[face],col=animate?manifest.walkSequence[Math.floor(clock*manifest.fps)%4]:0,f=s.frames[map.row*4+col],scale=height/s.referenceHeight;sprite(c,id,f.index,x,y,f.width*scale,f.anchorX,f.anchorY,map.flipX);}
function tile(x,y,index){const p=iso(x,y),s=manifest.sheets.terrain,f=s.frames[index];ctx.save();ctx.translate(p.x,p.y);ctx.beginPath();ctx.moveTo(0,-TH/2);ctx.lineTo(TW/2,0);ctx.lineTo(0,TH/2);ctx.lineTo(-TW/2,0);ctx.closePath();ctx.clip();ctx.fillStyle=index===2?'#d7ceaf':'#819858';ctx.fill();ctx.drawImage(images.terrain,f.x,f.y,f.width,f.height,-TW/2-1,-TH/2-1,TW+2,TH+2);ctx.restore();}
function label(text,x,y){ctx.font='10px Segoe UI';const w=ctx.measureText(text).width+14;ctx.fillStyle='#fbfaeee8';ctx.beginPath();ctx.roundRect(x-w/2,y-13,w,19,5);ctx.fill();ctx.fillStyle='#466043';ctx.textAlign='center';ctx.fillText(text,x,y);}
function drawWorld(){
  ctx.clearRect(0,0,cw,ch);ctx.save();ctx.translate(cw/2+pan.x,65+pan.y);ctx.scale(zoom,zoom);
  // Decorative foundation supplies the visual height of the neighborhood block.
  const a=iso(-.5,-.5),b=iso(N-.5,-.5),c=iso(N-.5,N-.5),d=iso(-.5,N-.5);
  ctx.fillStyle='#758d5a';ctx.beginPath();ctx.moveTo(d.x,d.y);ctx.lineTo(c.x,c.y);ctx.lineTo(c.x,c.y+12);ctx.lineTo(d.x,d.y+12);ctx.closePath();ctx.fill();ctx.fillStyle='#657e4f';ctx.beginPath();ctx.moveTo(c.x,c.y);ctx.lineTo(b.x,b.y);ctx.lineTo(b.x,b.y+12);ctx.lineTo(c.x,c.y+12);ctx.closePath();ctx.fill();
  for(let y=0;y<N;y++)for(let x=0;x<N;x++){let t=(x+y*3)%13===0?1:0;if(x===7||x===8||y===6||y===7||y===8)t=2;if((x===0||x===15)&&(y%3===0))t=15;tile(x,y,t);}
  const objects=[];
  for(const b of buildings){const p=iso(b.x,b.y);objects.push({depth:p.y+29,draw:()=>sprite(ctx,'buildings',b.index,p.x,p.y+54,226,.5,1)});}
  for(const o of staticProps){const p=iso(o.x,o.y);objects.push({depth:p.y,draw:()=>sprite(ctx,'props',o.i,p.x,p.y+6,o.w)});}
  for(const a of agents){const p=iso(a.x,a.y);objects.push({depth:p.y+1,draw:()=>{ctx.fillStyle='#233c3526';ctx.beginPath();ctx.ellipse(p.x,p.y,11,5,0,0,Math.PI*2);ctx.fill();if(a.id===selected){ctx.strokeStyle='#f5d382';ctx.lineWidth=2;ctx.beginPath();ctx.ellipse(p.x,p.y,17,8,0,0,Math.PI*2);ctx.stroke();}character(ctx,a.id,a.face,p.x,p.y,57,a.moving);}});}
  objects.sort((a,b)=>a.depth-b.depth).forEach(o=>o.draw());
  for(const a of agents){const p=iso(a.x,a.y);if(a.id===selected)label(profiles.find(p=>p[0]===a.id)[1],p.x,p.y-65);}
  const phase=Math.floor(clock/5)%4;if(phase===0){const a=agents[0],p=iso(a.x,a.y);label('Good morning!',p.x,p.y-86);}else if(phase===1){const a=agents[1],p=iso(a.x,a.y);label('See you at the cafe.',p.x,p.y-80);}
  ctx.restore();
}
function update(dt){for(const a of agents){a.moving=false;if(a.wait>0){a.wait-=dt;continue;}if(!a.path.length){if(a.id==='visitor')continue;a.leg=(a.leg+1)%a.route.length;const [x,y]=a.route[a.leg];a.path=pathfind(a,{x,y});a.wait=.9+profiles.findIndex(p=>p[0]===a.id)*.2;continue;}const p=a.path[0],dx=p.x-a.x,dy=p.y-a.y,d=Math.hypot(dx,dy),step=dt*.9;if(d<=step){a.x=p.x;a.y=p.y;a.path.shift();}else{a.x+=dx/d*step;a.y+=dy/d*step;}const v=iso(dx,dy),angle=Math.atan2(v.y,v.x),oct=(Math.round(angle/(Math.PI/4))+8)%8;a.face=[6,7,0,1,2,3,4,5][oct];a.moving=true;}}
function drawPortrait(){pc.clearRect(0,0,320,240);pc.fillStyle='#8f9c7330';pc.beginPath();pc.ellipse(160,218,42,10,0,0,Math.PI*2);pc.fill();character(pc,selected,direction,160,218,184,true);}
function resize(){const r=canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);cw=r.width;ch=r.height;canvas.width=Math.round(cw*dpr);canvas.height=Math.round(ch*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);}
new ResizeObserver(resize).observe(canvas);
canvas.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,px:pan.x,py:pan.y,moved:false};canvas.setPointerCapture(e.pointerId);});
canvas.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.hypot(dx,dy)>5)drag.moved=true;if(drag.moved){pan.x=drag.px+dx;pan.y=drag.py+dy;}});
canvas.addEventListener('pointerup',e=>{if(!drag)return;const moved=drag.moved;drag=null;if(moved||!ready)return;const r=canvas.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;let found=null,best=35;for(const a of agents){const p=screen(iso(a.x,a.y));const d=Math.hypot(p.x-mx,p.y-24*zoom-my);if(d<best){best=d;found=a;}}if(found){select(found.id);return;}const u=(mx-cw/2-pan.x)/zoom,v=(my-65-pan.y)/zoom,x=Math.round((u/(TW/2)+v/(TH/2))/2),y=Math.round((v/(TH/2)-u/(TW/2))/2),a=agents[5];a.path=pathfind(a,{x,y});select('visitor');});
canvas.addEventListener('pointercancel',()=>drag=null);
document.querySelector('#pause').onclick=()=>{paused=!paused;document.querySelector('#pause').textContent=paused?'Resume':'Pause';};
function fitWorld(){pan={x:0,y:0};zoom=Math.min(1,(cw-30)/(N*TW),(ch-80)/(N*TH+12));document.querySelector('#zoom').value=zoom;}
document.querySelector('#reset').onclick=fitWorld;
document.querySelector('#zoom').oninput=e=>zoom=Number(e.target.value);
function gallery(category){const host=document.querySelector('#gallery');host.className='gallery '+category;host.replaceChildren();document.querySelectorAll('[data-category]').forEach(b=>b.classList.toggle('active',b.dataset.category===category));const names=category==='ui'?['chat','task','destination','selection','pause','play','memory','clock']:manifest.sheets[category].frames.map(f=>f.name);names.forEach((name,i)=>{const card=document.createElement('div');card.className='asset-card';if(category==='ui'){const img=document.createElement('img');img.src=`assets/ui/${name}.svg`;img.alt=name;card.append(img);}else{const c=document.createElement('canvas');c.width=360;c.height=category==='buildings'?280:190;const cx=c.getContext('2d'),f=manifest.sheets[category].frames[i],scale=Math.min((c.width-25)/f.width,(c.height-18)/f.height);sprite(cx,category,i,c.width/2,c.height/2,f.width*scale,.5,.5);card.append(c);}const label=document.createElement('span');label.textContent=name.replaceAll('-',' ');card.append(label);host.append(card);});}
document.querySelectorAll('[data-category]').forEach(b=>b.onclick=()=>gallery(b.dataset.category));
Promise.all(Object.entries(manifest.sheets).map(([id,s])=>new Promise((resolve,reject)=>{const img=new Image;img.onload=()=>{images[id]=img;resolve();};img.onerror=()=>reject(Error('Could not load '+s.file));img.src='assets/'+s.file;}))).then(()=>{ready=true;document.querySelector('#load-status').hidden=true;gallery('terrain');resize();fitWorld();requestAnimationFrame(function tick(ms){const dt=Math.min((ms-last)/1000,.05);last=ms;if(!paused){clock+=dt;update(dt);}drawWorld();drawPortrait();requestAnimationFrame(tick);});}).catch(e=>{document.querySelector('#load-status').textContent=e.message;console.error(e);});
