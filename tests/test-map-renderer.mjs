// Camera checks run without a browser or optional rendering dependencies.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const context={window:{},ResizeObserver:class{observe(){}},devicePixelRatio:1};
vm.createContext(context);vm.runInContext(fs.readFileSync('client/renderer.js','utf8'),context);
const canvas={getContext:()=>({setTransform(){}}),getBoundingClientRect:()=>({width:800,height:600}),addEventListener(){}};
const layout=JSON.parse(fs.readFileSync('scenarios/neighborhood.json','utf8'));
const renderer=new context.window.SmallworldRenderer(canvas,canvas,layout,{},()=>{},()=>{});
renderer.resize();renderer.fit();
assert(renderer.zoom>0 && renderer.zoom<1);
for(const id of ['market','garden','plaza','waterfront']){
  renderer.focusPlace(id);
  const p=renderer.screen(renderer.iso(...layout.places[id]));
  assert(Math.abs(p.x-400)<.001);
  assert(Math.abs(p.y-342)<.001);
  assert.equal(renderer.room(),'');
  assert(renderer.zoom>.8);
}
console.log('District camera targets remain centered and readable.');
