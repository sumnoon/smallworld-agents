// Read-only PNG inspection. Writes metadata; never changes source artwork.
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
const root = path.resolve(import.meta.dirname, '..');
function png(file) {
  const buf=fs.readFileSync(file), parts=[]; let w,h,channels,type,depth,interlace;
  if(buf.subarray(1,4).toString()!=='PNG') throw Error('Not PNG: '+file);
  for(let p=8;p<buf.length;) {
    const n=buf.readUInt32BE(p), tag=buf.toString('ascii',p+4,p+8), d=buf.subarray(p+8,p+8+n);
    if(tag==='IHDR') {w=d.readUInt32BE(0);h=d.readUInt32BE(4);depth=d[8];type=d[9];interlace=d[12];}
    if(tag==='IDAT') parts.push(d); p+=n+12;
  }
  channels=({2:3,6:4})[type];
  if(depth!==8 || interlace!==0 || !channels) throw Error('Unsupported PNG encoding: '+file);
  const raw=zlib.inflateSync(Buffer.concat(parts)), stride=w*channels, pixels=Buffer.alloc(h*stride);
  const paeth=(a,b,c)=>{const p=a+b-c,pa=Math.abs(p-a),pb=Math.abs(p-b),pc=Math.abs(p-c);return pa<=pb&&pa<=pc?a:pb<=pc?b:c;};
  for(let y=0;y<h;y++) {
    const filter=raw[y*(stride+1)];
    for(let x=0;x<stride;x++) {
      const i=y*stride+x,a=x>=channels?pixels[i-channels]:0,b=y?pixels[i-stride]:0,c=y&&x>=channels?pixels[i-stride-channels]:0;
      pixels[i]=(raw[y*(stride+1)+1+x]+([0,a,b,Math.floor((a+b)/2),paeth(a,b,c)][filter]))&255;
    }
  }
  const alpha=new Uint8Array(w*h);let transparent=0;
  for(let i=0;i<alpha.length;i++){alpha[i]=channels===4?pixels[i*4+3]:255;if(alpha[i]===0)transparent++;}
  return {w,h,alpha,transparent};
}
function frames(img,cols,rows) {
  const {w,h,alpha}=img,seen=new Uint8Array(w*h),queue=new Int32Array(w*h),groups=Array.from({length:cols*rows},()=>[]);
  for(let i=0;i<alpha.length;i++) {
    if(seen[i]||alpha[i]<128)continue;
    let head=0,tail=1,count=0,x0=w,y0=h,x1=0,y1=0;queue[0]=i;seen[i]=1;
    while(head<tail){const p=queue[head++],x=p%w,y=Math.floor(p/w);count++;x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y);
      for(const q of [x?p-1:-1,x<w-1?p+1:-1,y?p-w:-1,y<h-1?p+w:-1])if(q>=0&&!seen[q]&&alpha[q]>=128){seen[q]=1;queue[tail++]=q;}
    }
    if(count<220)continue;
    const col=Math.min(cols-1,Math.floor(((x0+x1)/2)/w*cols)),row=Math.min(rows-1,Math.floor(((y0+y1)/2)/h*rows));
    groups[row*cols+col].push({x0,y0,x1,y1,count});
  }
  return groups.map((g,index)=>{
    if(!g.length)throw Error('Empty sprite cell '+index);
    // Main connected object; include nearby disconnected details, discard distant dust.
    g.sort((a,b)=>b.count-a.count);const b={...g[0]};
    for(const c of g.slice(1))if(c.x0<=b.x1+12&&c.x1>=b.x0-12&&c.y0<=b.y1+12&&c.y1>=b.y0-12){b.x0=Math.min(b.x0,c.x0);b.x1=Math.max(b.x1,c.x1);b.y0=Math.min(b.y0,c.y0);b.y1=Math.max(b.y1,c.y1);}
    const x=Math.max(0,b.x0-2),y=Math.max(0,b.y0-2),width=Math.min(w-1,b.x1+2)-x+1,height=Math.min(h-1,b.y1+2)-y+1;
    let sx=0,n=0;for(let yy=b.y0;yy<b.y0+(b.y1-b.y0)*.3;yy++)for(let xx=b.x0;xx<=b.x1;xx++)if(alpha[yy*w+xx]>200){sx+=xx;n++;}
    return {index,x,y,width,height,anchorX:n?(sx/n-x)/width:.5,anchorY:(b.y1-y)/height};
  });
}
const terrain=['grass','flowers','sidewalk','gravel','asphalt','road-se','road-sw','cobblestone','wood-floor','cafe-floor','terracotta-floor','bathroom-floor','water','soil','sand','autumn-grass'];
const buildings=['cafe','shop','home-green','home-blue'];
const props=['tree','small-tree','shrub','planter','bench','table','chair','lamp','coffee-counter','bookshelf','armchair','bed','coffee','parcel','bin','noticeboard'];
const chars=['maya','noah','elena','samir','jun','visitor'];
const sheets=[['terrain','isometric/terrain.png',4,4,terrain],['buildings','isometric/buildings.png',2,2,buildings],['props','isometric/props.png',4,4,props],...chars.map(id=>[id,`characters/${id}${id==='maya'?'':'-alpha'}.png`,4,8,null])];
const manifest={version:1,projection:{type:'game-isometric',tileWidth:128,tileHeight:64},directions:['S','SW','W','NW','N','NE','E','SE'],walkSequence:[0,1,2,3],fps:6,sheets:{}};
for(const [id,file,cols,rows,names] of sheets){
  const p=path.join(root,'assets',file);if(!fs.existsSync(p))continue;
  const img=png(p);if(img.transparent/img.alpha.length<.1)throw Error('Background is not transparent: '+file);
  const list=frames(img,cols,rows);if(names)list.forEach((f,i)=>{f.name=names[i];f.anchorX=.5;});
  const facing=manifest.directions.map((direction,row)=>({direction,row,flipX:false}));
  // Visual review: these generated rows face left instead of right. Reuse the
  // correct west artwork with the renderer's native flip, preserving source PNGs.
  if(['elena','samir','visitor'].includes(id))facing[6]={direction:'E',row:2,flipX:true};
  if(id==='elena')facing[5]={direction:'NE',row:3,flipX:true};
  manifest.sheets[id]={file,width:img.w,height:img.h,transparentPercent:Math.round(img.transparent/img.alpha.length*1000)/10,cols,rows,referenceHeight:Math.max(...list.map(f=>f.height)),frames:list,...(!names?{facing}: {})};
  console.log(`${id}: ${img.w}x${img.h}, ${list.length} frames, ${manifest.sheets[id].transparentPercent}% transparent`);
}
fs.writeFileSync(path.join(root,'assets/manifest.json'),JSON.stringify(manifest,null,2)+'\n');
fs.writeFileSync(path.join(root,'assets/manifest.js'),'window.ASSET_MANIFEST = '+JSON.stringify(manifest)+';\n');
