// Render actual garden/picnic snapshots produced by evaluate-community.py.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url),{createCanvas,loadImage}=require(process.env.VIDEO_CANVAS_MODULE||'@napi-rs/canvas');
const root=path.resolve(import.meta.dirname,'..'),state=JSON.parse(fs.readFileSync(path.join(root,'.video-build/community-'+(process.argv[2]||'garden')+'-state.json'),'utf8'));
const manifest=JSON.parse(fs.readFileSync(path.join(root,'assets/manifest.json'),'utf8'));
const sandbox={window:{},OffscreenCanvas:class{constructor(w,h){return createCanvas(w,h);}},ResizeObserver:class{observe(){}},devicePixelRatio:1,requestAnimationFrame(){}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(root,'client/renderer.js'),'utf8'),sandbox);
const canvas=createCanvas(1400,1000),portrait=createCanvas(130,150);
canvas.getBoundingClientRect=()=>({width:1400,height:1000});canvas.addEventListener=()=>{};
const renderer=new sandbox.window.SmallworldRenderer(canvas,portrait,state.layout,manifest,()=>{},()=>{});
for(const [id,s]of Object.entries(manifest.sheets))renderer.images[id]=await loadImage(path.join(root,'assets',s.file));
renderer.resize();renderer.setState(state);renderer.view='';renderer.bubbles=false;renderer.draw();
function save(name){const out=createCanvas(1400,1000),c=out.getContext('2d');c.fillStyle='#edf1df';c.fillRect(0,0,1400,1000);c.drawImage(canvas,0,0);fs.writeFileSync(path.join(root,'.video-build/'+name+'.png'),out.toBuffer('image/png'));}
renderer.focusPlace(process.argv[2]==='picnic'?'plaza':'garden');renderer.selected='maya';renderer.clock=1;renderer.draw();save('community-'+(process.argv[2]||'garden'));
console.log('Rendered community snapshot.');
