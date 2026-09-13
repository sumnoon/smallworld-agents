'use strict';
class SmallworldRenderer {
  constructor(canvas,portrait,layout,manifest,onSelect,onMove){
    this.canvas=canvas;this.ctx=canvas.getContext('2d');this.portrait=portrait;this.pc=portrait.getContext('2d');this.layout=layout;this.manifest=manifest;this.onSelect=onSelect;this.onMove=onMove;this.images={};this.selected='maya';this.view='auto';this.state=null;this.display={};this.zoom=1;this.pan={x:0,y:0};this.clock=0;this.last=0;this.bubbles=true;this.drag=null;this.ready=false;this.placeLabels=true;
    new ResizeObserver(()=>this.resize()).observe(canvas);
    canvas.addEventListener('pointerdown',e=>{this.drag={x:e.clientX,y:e.clientY,px:this.pan.x,py:this.pan.y,moved:false};canvas.setPointerCapture(e.pointerId);});
    canvas.addEventListener('pointermove',e=>{if(!this.drag)return;const dx=e.clientX-this.drag.x,dy=e.clientY-this.drag.y;if(Math.hypot(dx,dy)>5)this.drag.moved=true;if(this.drag.moved){this.pan.x=this.drag.px+dx;this.pan.y=this.drag.py+dy;}});
    canvas.addEventListener('pointerup',e=>{if(!this.drag)return;const moved=this.drag.moved;this.drag=null;if(moved||!this.state)return;const r=canvas.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;let found=null,best=26;for(const a of this.state.agents.filter(a=>(a.room||'')===this.room())){const p=this.screen(this.iso(this.display[a.id].x,this.display[a.id].y)),d=Math.hypot(p.x-mx,p.y-25*this.zoom-my);if(d<best){best=d;found=a;}}if(found&&found.id!=='visitor'){this.onSelect(found.id);return;}const u=(mx-this.cw/2-this.pan.x)/this.zoom,v=(my-this.origin()-this.pan.y)/this.zoom;this.onMove(Math.round((u/32+v/16)/2),Math.round((v/16-u/32)/2));});
    canvas.addEventListener('pointercancel',()=>this.drag=null);
    canvas.addEventListener('wheel',e=>{e.preventDefault();this.zoom=Math.max(.22,Math.min(1.8,this.zoom*Math.exp(-e.deltaY*.001)));},{passive:false});
    canvas.addEventListener('keydown',e=>{if(e.key==='Home'){this.fit();e.preventDefault();}});
  }
  async load(){await Promise.all(Object.entries(this.manifest.sheets).map(([id,s])=>new Promise((resolve,reject)=>{const img=new Image;img.onload=()=>{this.images[id]=img;resolve();};img.onerror=()=>reject(Error('Missing artwork: '+s.file));img.src='/assets/'+s.file;})));this.ready=true;this.resize();this.fit();requestAnimationFrame(ms=>this.frame(ms));}
  room(){return this.view==='auto'?(this.state?.agents.find(a=>a.id===this.selected)?.room||''):this.view;}
  origin(){return this.room()?Math.max(170,this.ch*.28):this.originY;}
  iso(x,y){return{x:(x-y)*32,y:(x+y)*16};}
  screen(p){return{x:this.cw/2+this.pan.x+p.x*this.zoom,y:this.origin()+this.pan.y+p.y*this.zoom};}
  resize(){const r=this.canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);this.cw=r.width;this.ch=r.height;this.originY=70;this.canvas.width=Math.round(r.width*dpr);this.canvas.height=Math.round(r.height*dpr);this.ctx.setTransform(dpr,0,0,dpr,0,0);}
  fit(){this.pan={x:0,y:0};this.zoom=Math.min(1,(this.cw-20)/(this.layout.size*64),(this.ch-90)/(this.layout.size*32+12));}
  focusPlace(id){const point=this.layout.places[id];if(!point)return;this.focusPoint(point[0],point[1]);}
  focusPoint(x,y){this.view='';this.lastViewRoom='';this.zoom=Math.min(1.05,(this.cw-30)/570);const p=this.iso(x,y);this.pan={x:-p.x*this.zoom,y:this.ch*.57-this.origin()-p.y*this.zoom};}
  setState(state){this.state=state;for(const a of state.agents)if(!this.display[a.id])this.display[a.id]={x:a.x,y:a.y};}
  sprite(c,id,index,x,y,width,anchorX=.5,anchorY=1,flip=false){const s=this.manifest.sheets[id],f=s.frames[index],h=width*f.height/f.width;c.save();c.translate(x,y);if(flip)c.scale(-1,1);c.drawImage(this.images[id],f.x,f.y,f.width,f.height,-width*anchorX,-h*anchorY,width,h);c.restore();}
  character(c,a,x,y,height){const skin=a.skin||a.id,s=this.manifest.sheets[skin],map=s.facing[a.face],col=a.moving&&!this.state.paused?this.manifest.walkSequence[Math.floor(this.clock*6)%4]:0,f=s.frames[map.row*4+col];this.sprite(c,skin,f.index,x,y,f.width*height/s.referenceHeight,f.anchorX,f.anchorY,map.flipX);}
  ground(x,y,index){const c=this.ctx,p=this.iso(x,y),f=this.manifest.sheets.terrain.frames[index];c.save();c.translate(p.x,p.y);c.beginPath();c.moveTo(0,-16);c.lineTo(32,0);c.lineTo(0,16);c.lineTo(-32,0);c.closePath();c.clip();c.fillStyle=index===2?'#d7ceaf':'#819858';c.fill();c.drawImage(this.images.terrain,f.x,f.y,f.width,f.height,-33,-17,66,34);c.restore();}
  drawTerrain(n){
    const paint=()=>{for(let y=0;y<n;y++)for(let x=0;x<n;x++){let tile=this.layout.terrain?.[y]?.[x];if(tile===undefined){tile=(x+y*3)%13===0?1:0;if(x===7||x===8||y===6||y===7||y===8)tile=2;}this.ground(x,y,tile);}};
    if(typeof OffscreenCanvas==='undefined'){paint();return;}
    if(this.terrainCache?.layout!==this.layout){
      const surface=new OffscreenCanvas(n*64,n*32+32),previous=this.ctx;
      this.ctx=surface.getContext('2d');this.ctx.translate(n*32,16);
      try{paint();}finally{this.ctx=previous;}
      this.terrainCache={layout:this.layout,surface};
    }
    this.ctx.drawImage(this.terrainCache.surface,-n*32,-16);
  }
  label(text,x,y,fill='#fbfaeef0',color='#466043'){const c=this.ctx;c.font='10px Segoe UI';const w=Math.min(215,c.measureText(text).width+16);c.fillStyle=fill;c.beginPath();c.roundRect(x-w/2,y-13,w,20,6);c.fill();c.fillStyle=color;c.textAlign='center';c.fillText(text,x,y,200);}
  speech(text,x,y){const c=this.ctx,words=text.split(/\s+/),lines=[];let line='';c.font='11px Segoe UI';for(const word of words){if(c.measureText(line+' '+word).width>175){lines.push(line);line=word;if(lines.length===2)break;}else line+=(line?' ':'')+word;}if(lines.length<3&&line)lines.push(line);if(lines.join(' ').length<text.length)lines[lines.length-1]+='…';const w=Math.max(...lines.map(t=>c.measureText(t).width))+20,h=lines.length*15+15;c.fillStyle='#fffdf2';c.strokeStyle='#d2dec3';c.lineWidth=1;c.beginPath();c.roundRect(x-w/2,y-h,w,h,8);c.fill();c.stroke();c.beginPath();c.moveTo(x-5,y);c.lineTo(x,y+5);c.lineTo(x+5,y);c.fill();c.fillStyle='#52674b';c.textAlign='center';lines.forEach((t,i)=>c.fillText(t,x,y-h+16+i*15));}
  draw(){if(this.lastViewRoom!==this.room()){this.lastViewRoom=this.room();this.fit();if(this.room())this.zoom=Math.min(1.6,(this.cw-30)/400);}if(this.room()){this.drawInterior();return;}const c=this.ctx;c.clearRect(0,0,this.cw,this.ch);c.save();c.translate(this.cw/2+this.pan.x,this.origin()+this.pan.y);c.scale(this.zoom,this.zoom);const n=this.layout.size,pb=this.iso(n-.5,-.5),pc=this.iso(n-.5,n-.5),pd=this.iso(-.5,n-.5);c.fillStyle='#788f5d';c.beginPath();c.moveTo(pd.x,pd.y);c.lineTo(pc.x,pc.y);c.lineTo(pc.x,pc.y+12);c.lineTo(pd.x,pd.y+12);c.closePath();c.fill();c.fillStyle='#687f50';c.beginPath();c.moveTo(pc.x,pc.y);c.lineTo(pb.x,pb.y);c.lineTo(pb.x,pb.y+12);c.lineTo(pc.x,pc.y+12);c.closePath();c.fill();
    this.drawTerrain(n);
    this.drawGarden();
    this.drawPicnic();
    const objects=[];for(const b of this.layout.buildings){const p=this.iso(b.x,b.y);objects.push({depth:p.y+29,draw:()=>{const a=this.display[this.selected],ap=a?this.iso(a.x,a.y):null,occludes=ap&&ap.y<p.y+48&&ap.y>p.y-155&&Math.abs(ap.x-p.x)<95;c.save();if(occludes)c.globalAlpha=.48;this.sprite(c,'buildings',b.index,p.x,p.y+54,226);c.restore();}});}
    for(const o of this.layout.landmarks||[]){const p=this.iso(o.x,o.y),offset=o.base_offset||0;objects.push({depth:p.y+offset*.55,draw:()=>{const a=this.state.agents.find(a=>a.id===this.selected),d=a&&!a.room?this.display[a.id]:null,ap=d?this.iso(d.x,d.y):null;c.save();if(ap&&ap.y<p.y+offset&&ap.y>p.y-o.w*.75&&Math.abs(ap.x-p.x)<o.w*.44)c.globalAlpha=.48;this.sprite(c,o.asset,0,p.x,p.y+offset,o.w);c.restore();}});}
    for(const o of this.layout.props){const p=this.iso(o.x,o.y);objects.push({depth:p.y,draw:()=>this.sprite(c,'props',o.i,p.x,p.y+6,o.w)});}
    for(const a of this.state.agents.filter(a=>(a.room||'')===this.room())){const d=this.display[a.id],p=this.iso(d.x,d.y);objects.push({depth:p.y+1,draw:()=>{c.fillStyle='#223c3525';c.beginPath();c.ellipse(p.x,p.y,11,5,0,0,Math.PI*2);c.fill();if(a.id===this.selected||a.id==='visitor'){c.strokeStyle=a.id==='visitor'?'#d69669':'#f2d58a';c.lineWidth=2;c.beginPath();c.ellipse(p.x,p.y,16,7,0,0,Math.PI*2);c.stroke();}this.character(c,a,p.x,p.y+(a.working?Math.sin(this.clock*5)*1.5:0),60);this.drawWork(c,a,p);if(a.inventory.length)this.sprite(c,'props',a.inventory[0].kind==='coffee'?12:13,p.x+15,p.y-25,12);}});}
    objects.sort((a,b)=>a.depth-b.depth).forEach(o=>o.draw());c.restore();
    for(const a of this.state.agents.filter(a=>(a.room||'')===this.room())){const d=this.display[a.id],p=this.screen(this.iso(d.x,d.y));if(a.id===this.selected)this.label(a.name+(a.thinking?' · thinking':''),p.x,p.y-64*this.zoom);if(this.bubbles&&a.bubble&&a.bubble_until>this.state.time)this.speech(a.bubble,p.x,p.y-85*this.zoom);}
    if(this.placeLabels&&this.zoom>.43)for(const district of this.layout.districts||[]){const point=this.layout.places[district.place],p=this.screen(this.iso(point[0],point[1]));this.label(district.name,p.x,p.y+25*this.zoom,'#fffdf3eb',district.color);}
    this.drawWeather();
    const a=this.state.agents.find(a=>a.id===this.selected);this.pc.clearRect(0,0,130,150);if(a){this.pc.fillStyle='#7e97662a';this.pc.beginPath();this.pc.ellipse(65,143,24,6,0,0,Math.PI*2);this.pc.fill();this.character(this.pc,{...a,face:0},65,141,124);}
  }
  drawPicnic(){const t=this.state.tasks.find(t=>t.picnic&&['invite','completed'].includes(t.picnic.phase)&&(!t.completed||this.state.time-t.completed<1800)),host=t&&this.state.agents.find(a=>a.id===t.agent),point=this.layout.places.plaza;if(!host||host.room||!point||Math.hypot(host.x-point[0],host.y-point[1])>2)return;const c=this.ctx,p=this.iso(point[0]+.6,point[1]+.6);c.save();c.translate(p.x,p.y);c.fillStyle='#db8666';c.strokeStyle='#fff2d4';c.lineWidth=2;c.beginPath();c.moveTo(0,-19);c.lineTo(37,0);c.lineTo(0,19);c.lineTo(-37,0);c.closePath();c.fill();c.stroke();for(const [x,y] of [[-15,0],[0,-8],[15,0],[0,8]]){c.fillStyle='#fff4d4';c.beginPath();c.ellipse(x,y,6,3,0,0,Math.PI*2);c.fill();c.fillStyle='#73944b';c.fillRect(x-2,y-1,4,2);}c.restore();}
  drawGarden(){const c=this.ctx;for(const bed of Object.values(this.state.community?.beds||{})){const p=this.iso(bed.x,bed.y),ripe=bed.ready_at&&this.state.time>=bed.ready_at;c.fillStyle='#785744';c.beginPath();c.ellipse(p.x,p.y,21,10,0,0,Math.PI*2);c.fill();for(let i=0;i<3;i++){const x=p.x+(i-1)*11,y=p.y+(i%2)*3;c.strokeStyle='#518146';c.lineWidth=2;c.beginPath();c.moveTo(x,y);c.lineTo(x,y-(ripe?14:7));c.stroke();c.fillStyle=ripe?'#e98d56':bed.ready_at?'#86bf5b':'#b8d473';c.beginPath();c.ellipse(x-3,y-7,5,3,-.5,0,Math.PI*2);c.fill();c.beginPath();c.ellipse(x+3,y-10,5,3,.5,0,Math.PI*2);c.fill();}}}
  drawWork(c,a,p){if(!a.working)return;const phase=this.state.paused?0:this.clock;c.save();c.translate(p.x+15,p.y-20);if(a.working.kind==='water'){c.fillStyle='#71b7d5';c.fillRect(-5,-8,12,9);for(let i=0;i<3;i++){c.beginPath();c.ellipse(10+i*3,((phase*18+i*4)%18)-5,1.3,2.5,.4,0,Math.PI*2);c.fill();}}else{c.strokeStyle='#e9c078';c.lineWidth=2;c.beginPath();c.arc(0,0,8,phase*2,phase*2+4.4);c.stroke();c.fillStyle='#fff9dd';c.font='8px sans-serif';c.textAlign='center';c.fillText(a.working.kind==='buy'?'$':'+',0,3);}c.restore();}
  drawWeather(){const c=this.ctx,hour=(this.state.time/3600)%24,dark=hour<6||hour>=20?.25:hour<8||hour>=18?.1:0;if(dark){c.fillStyle=`rgba(29,40,73,${dark})`;c.fillRect(0,0,this.cw,this.ch);}if(this.state.community?.weather==='rain'){c.fillStyle='#536c7b18';c.fillRect(0,0,this.cw,this.ch);c.strokeStyle='#b6d8e6aa';c.lineWidth=1;c.beginPath();for(let i=0;i<90;i++){const x=(i*137)%this.cw,y=(i*71+this.clock*160)%this.ch;c.moveTo(x,y);c.lineTo(x-4,y+11);}c.stroke();}}
  drawInterior(){
    const c=this.ctx,room=this.room(),r=this.layout.interiors?.[room];if(!r)return;
    c.clearRect(0,0,this.cw,this.ch);c.save();c.translate(this.cw/2+this.pan.x,this.origin()+this.pan.y);c.scale(this.zoom,this.zoom);
    const polygon=(points,fill)=>{c.fillStyle=fill;c.beginPath();points.forEach((p,i)=>i?c.lineTo(p.x,p.y):c.moveTo(p.x,p.y));c.closePath();c.fill();};
    for(let y=0;y<r.size;y++)for(let x=0;x<r.size;x++){const p=this.iso(x,y);polygon([{x:p.x,y:p.y-16},{x:p.x+32,y:p.y},{x:p.x,y:p.y+16},{x:p.x-32,y:p.y}],(x+y)%2?'#d9c49a':'#e9d6ad');}
    const a=this.iso(-.5,-.5),b=this.iso(r.size-.5,-.5),d=this.iso(-.5,r.size-.5);
    polygon([a,b,{x:b.x,y:b.y-80},{x:a.x,y:a.y-80}],'#b3c3a5');polygon([a,d,{x:d.x,y:d.y-80},{x:a.x,y:a.y-80}],'#c9d4b9');
    const door=this.iso(...r.door);c.fillStyle='#7a9b72';c.beginPath();c.ellipse(door.x,door.y,22,10,0,0,Math.PI*2);c.fill();
    const objects=r.objects.map(o=>{const p=this.iso(o.x,o.y);return{depth:p.y,draw:()=>this.sprite(c,'props',o.i,p.x,p.y+4,o.w)};});
    const people=this.state.agents.filter(a=>(a.room||'')===room);
    for(const a of people){const p=this.iso(this.display[a.id].x,this.display[a.id].y);objects.push({depth:p.y+1,draw:()=>{c.fillStyle='#30453330';c.beginPath();c.ellipse(p.x,p.y,12,5,0,0,Math.PI*2);c.fill();this.character(c,a,p.x,p.y,60);}});}
    objects.sort((a,b)=>a.depth-b.depth).forEach(o=>o.draw());c.restore();
    this.label(room.toUpperCase()+' · interior',this.cw/2,28);
    for(const a of people){const p=this.screen(this.iso(this.display[a.id].x,this.display[a.id].y));if(a.id===this.selected)this.label(a.name,p.x,p.y-64*this.zoom);if(this.bubbles&&a.bubble&&a.bubble_until>this.state.time)this.speech(a.bubble,p.x,p.y-85*this.zoom);}
    const selected=this.state.agents.find(a=>a.id===this.selected);this.pc.clearRect(0,0,130,150);if(selected)this.character(this.pc,{...selected,face:0},65,141,124);
  }
  frame(ms){const dt=Math.min((ms-this.last)/1000,.05);this.last=ms;if(this.state){if(!this.state.paused)this.clock+=dt;for(const a of this.state.agents.filter(a=>(a.room||'')===this.room())){const d=this.display[a.id],alpha=1-Math.exp(-dt*15);if(Math.hypot(d.x-a.x,d.y-a.y)>3){d.x=a.x;d.y=a.y;}else{d.x+=(a.x-d.x)*alpha;d.y+=(a.y-d.y)*alpha;}}this.draw();}requestAnimationFrame(t=>this.frame(t));}
}
window.SmallworldRenderer=SmallworldRenderer;
