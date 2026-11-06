"""Fog-of-war POC for a built code city: python3 inject_fog.py <in.html> <out.html>

Removable by design: everything it adds sits between FOG-POC markers, so re-running on a
fresh build (or simply not running it) is the whole revert. Progress is kept locally in
localStorage (wrapped in try/catch); the city works unchanged when storage is unavailable.
"""
import sys

CSS = """
/* FOG-POC */
#fogHud{position:absolute;left:12px;top:58px;z-index:6;width:250px;background:var(--panel);border:1px solid #ffffff14;border-radius:12px;padding:9px 12px;font-size:12px;backdrop-filter:blur(6px)}
#fogHud[hidden]{display:none}
#fogHud .fh-top{display:flex;justify-content:space-between;align-items:center;gap:8px}
#fogHud .fh-btns{display:flex;gap:4px}#fogHud.min .fh-d,#fogHud.min .fh-meta{display:none}
#fogHud .fh-top b{font-size:13.5px}#fogHud .fh-top b span{color:var(--acc)}
#fogHud button{background:transparent;border:1px solid #ffffff2a;color:var(--mute);font-size:11px;padding:2px 8px;border-radius:999px;cursor:pointer}
#fogHud .fh-d{display:grid;grid-template-columns:1fr 34px;gap:2px 8px;margin-top:7px;align-items:center}
#fogHud .fh-d span{color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:11px}
#fogHud .fh-d em{font-style:normal;color:var(--mute);font-size:10.5px;text-align:right;font-variant-numeric:tabular-nums}
#fogHud .fh-d i{grid-column:1/3;height:4px;border-radius:2px;background:#ffffff14;overflow:hidden;margin-bottom:3px}
#fogHud .fh-d i u{display:block;height:100%;transition:width .6s}
#fogHud .fh-meta{display:flex;justify-content:space-between;margin-top:6px;color:var(--mute);font-size:11px;font-variant-numeric:tabular-nums}
#fogToast{position:absolute;left:50%;top:18px;transform:translate(-50%,-140%);z-index:12;background:#0f1424f0;border:1px solid #5eead466;color:#e8ecf5;padding:8px 16px;border-radius:999px;font-size:13px;font-weight:600;transition:transform .45s cubic-bezier(.2,.9,.3,1.2);pointer-events:none}
#fogToast.on{transform:translate(-50%,0)}
.tag.fogname small{display:block;font-size:10px;font-weight:500;opacity:.6;text-align:center}
#body .fogcode{font-family:ui-monospace,Menlo,monospace;font-size:11.5px}
#body li.fogdim b{color:#6b7489;font-weight:500}
#app.isolated #fogHud{display:none}
#fogHud:not([hidden])~#layers{max-height:calc(100% - 270px)}
@media (prefers-reduced-motion:reduce){#fogToast{transition:none}}
@media (max-width:700px){#fogHud{width:auto;max-width:calc(100% - 140px);padding:6px 10px}#fogHud .fh-d,#fogHud .fh-meta{display:none}}
/* /FOG-POC */
"""

HTML = '<!--FOG-POC--><div id="fogHud" data-dock="top" hidden><div class="fh-top"><b id="fhPct"></b><span class="fh-btns"><button id="fhReset" title="Hide everything again">Reset fog</button><button id="fhMin" aria-expanded="true" title="Collapse">▴</button></span></div><div class="fh-d" id="fhDist"></div><div class="fh-meta"><span id="fhFn"></span><span id="fhFl"></span></div></div><div id="fogToast" role="status" aria-live="polite"></div><!--/FOG-POC-->'

JS = r"""
/* ==== FOG-POC: fog of war (removable, see inject_fog.py) ==== */
{
const FKEY="boarding-city-fog-"+(D.repo||"repo");
const store={get(){try{return JSON.parse(localStorage.getItem(FKEY)||"null")}catch{return null}},
  set(v){try{localStorage.setItem(FKEY,JSON.stringify(v))}catch{}},clear(){try{localStorage.removeItem(FKEY)}catch{}}};
const saved=store.get()||{};
const S={b:saved.b||{},on:saved.fog===true};            // fog is opt-in (Layers)            // b: building path -> 0.5 (glimpsed) | 1 (explored)
const fnSet=new Set(saved.f||[]),flSet=new Set(saved.fl||[]),msSet=new Set(saved.ms||[]);
const save=()=>store.set({b:S.b,fog:S.on,f:[...fnSet],fl:[...flSet],ms:[...msSet]});

// ---- friendly names, from data already in the build (file summaries, flow narration) ----
const narr={};D.flows.forEach(F=>F.steps.forEach(s=>{narr[s.path+"::"+s.function]??=s.narration}));
const human=n=>n.replace(/^_+/,"").replace(/([a-z0-9])([A-Z])/g,"$1 $2").replace(/([A-Z]+)([A-Z][a-z])/g,"$1 $2").replace(/[_-]+/g," ").trim().toLowerCase().replace(/^./,c=>c.toUpperCase());
const clip=(s,n)=>s.length>n?s.slice(0,n-1).replace(/[\s,;:]+\S*$/,"")+"…":s;
const lead=s=>(s||"").split(/(?<=\.)\s|;\s|,\s(?=and |which |then |so )/)[0].replace(/\.$/,"").trim();
const baseTitle=p=>{const parts=p.split("/"),b=parts.pop().replace(/\.\w+$/,"");return b==="index"?`${human(parts.pop()||"root")} module`:human(b)};
const blockTitle=p=>{const seg=p.replace(/\/? \(block\)$/,"").split(/\s·\s|\//).filter(Boolean).pop()||"folder",n=byPath[p].members.length;return `${human(seg)} · ${n} file${n===1?"":"s"}`};
const fileTitle=p=>{const f=byPath[p];return f.cluster?blockTitle(p):clip(lead(f.summary)||baseTitle(p),44)};
const fnTitle=(p,n,max=64)=>{const s=narr[p+"::"+n];return s?clip(lead(s),max):human(n)};
const fogEsc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

// ---- per-building fog state and visuals ----
const GREY=new THREE.Color(0x353b49),PLATE=new THREE.Color(0x191d27);
const realFns=Object.fromEntries(D.files.filter(f=>!f.cluster).map(f=>[f.path,new Set(f.functions.map(x=>x.name))]));
const N_FN=Object.values(realFns).reduce((a,s)=>a+s.size,0),PATHS=Object.keys(buildings);
const puffTex=(()=>{const c=document.createElement("canvas");c.width=c.height=128;const g=c.getContext("2d"),r=g.createRadialGradient(64,64,6,64,64,62);
  r.addColorStop(0,"rgba(196,206,232,.62)");r.addColorStop(.55,"rgba(150,162,196,.26)");r.addColorStop(1,"rgba(130,140,175,0)");g.fillStyle=r;g.fillRect(0,0,128,128);
  const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;return t})();
const FOGG=new THREE.Group();scene.add(FOGG);const EDGES=new THREE.Group();scene.add(EDGES);
const BS={};
PATHS.forEach((p,i)=>{const b=buildings[p],w=byPath[p].cluster?2.6:1.9;
  b.group.children.forEach(m=>m.userData.c0=m.material.color.clone());
  const sp=new THREE.Sprite(new THREE.SpriteMaterial({map:puffTex,transparent:true,depthWrite:false,fog:false}));
  const s=CELL*1.55,y0=Math.min(b.H,7)*0.55+0.9;sp.scale.set(s,s*0.62,1);sp.position.set(b.x,y0,b.z);FOGG.add(sp);
  const eg=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(w*1.06,b.H,w*1.06)),new THREE.LineBasicMaterial({color:COLORS[fileDistrict[p]],transparent:true,opacity:0}));
  eg.position.set(b.x,0.15+b.H/2,b.z);EDGES.add(eg);
  const g=S.b[p]||0;BS[p]={t:g,goal:g,shown:-1,sp,eg,y0,s,seed:i*1.618}});
// a few big slow banks of fog per district, for the drifting ambience
const plates=pickables.filter(m=>m.userData.kind==="district");
plates.forEach(pl=>{(Array.isArray(pl.material)?pl.material:[pl.material]).forEach(m=>m.userData.c0=m.color.clone())});
const banks=D.districts.map((d,i)=>{const arr=[];for(let k=0;k<1;k++){const sp=new THREE.Sprite(new THREE.SpriteMaterial({map:puffTex,transparent:true,depthWrite:false,fog:false,opacity:0}));
  const s=d.size*0.8;sp.scale.set(s,s*0.4,1);sp.position.set(d.center.x,1.6,d.center.z);sp.userData={x0:sp.position.x,z0:sp.position.z,seed:i*3.1+k};FOGG.add(sp);arr.push(sp)}return arr});
const PS=D.districts.map(()=>({t:0,shown:-1}));

// ---- labels: district names hide until something there is seen; friendly building titles once explored ----
const dTags=D.districts.map(d=>tags.find(t=>t.city&&!t.layer&&t.el.textContent===d.name));
const landmarkPaths=new Set(D.files.map(f=>short(f.path)));
tags.filter(t=>t.city&&!t.layer&&!dTags.includes(t)&&landmarkPaths.has(t.el.textContent)).forEach(t=>t.el.style.visibility="hidden");
let fogTags=[];
function relabel(){fogTags.forEach(t=>{t.el.remove();tags.splice(tags.indexOf(t),1)});fogTags=[];
  const pick=PATHS.filter(p=>!byPath[p].cluster&&(!S.on||S.b[p]===1)).sort((a,b)=>byPath[b].lines-byPath[a].lines).slice(0,S.on?14:8);
  pick.forEach(p=>{const b=buildings[p],el=tag("",0xe8ecf5);el.classList.add("fogname");el.innerHTML=`${fogEsc(fileTitle(p))}<small>${fogEsc(short(p))}</small>`;
    const t={el,pos:new THREE.Vector3(b.x,b.H+0.6,b.z),city:true};tags.push(t);fogTags.push(t)});
  D.districts.forEach((d,i)=>{const t=dTags[i];if(!t)return;const seen=!S.on||distFrac(i,true)>0;t.el.textContent=seen?d.name:"Unexplored";t.el.style.opacity=seen?"":".55"})}

// ---- progress ----
const distFiles=D.districts.map(d=>d.files.filter(p=>buildings[p]));
function distFrac(i,any){const fs=distFiles[i];return fs.length?fs.filter(p=>any?S.b[p]:S.b[p]===1).length/fs.length:0}
const pct=()=>Math.round(100*PATHS.filter(p=>S.b[p]===1).length/PATHS.length);
const hud=$("fogHud"),toastEl=$("fogToast");let toastT=0,quiet=true;
function toast(msg){toastEl.textContent=msg;toastEl.classList.add("on");clearTimeout(toastT);toastT=setTimeout(()=>toastEl.classList.remove("on"),2600)}
function renderHud(){hud.hidden=!S.on;if(!S.on)return;const q=pct();
  $("fhPct").innerHTML=`Explored <span>${q}%</span> of ${fogEsc(D.repo||"the repo")}`;
  $("fhDist").innerHTML=D.districts.map((d,i)=>{const f=distFrac(i);return `<span>${fogEsc(d.name)}</span><em>${Math.round(f*100)}%</em><i><u style="width:${f*100}%;background:${"#"+COLORS[i].toString(16).padStart(6,"0")}"></u></i>`}).join("");
  $("fhFn").textContent=`Functions ${fnSet.size}/${N_FN}`;$("fhFl").textContent=`Flows ${flSet.size}/${D.flows.length}`}
function milestones(){const q=pct(),said=[];
  D.districts.forEach((d,i)=>{if(distFrac(i)>=1&&!msSet.has("d"+i)){msSet.add("d"+i);said.push(`${d.name} mapped!`)}});
  for(const m of[25,50,75,100])if(q>=m&&!msSet.has("p"+m)){msSet.add("p"+m);said.push(m===100?`${D.repo} fully mapped!`:`${m}% of ${D.repo} explored`)}
  if(said.length&&!quiet)toast(said[said.length-1])}
let dirty=0;function changed(){if(dirty)return;dirty=requestAnimationFrame(()=>{dirty=0;milestones();renderHud();relabel();save()})}

// ---- reveal ----
function reveal(p,lvl=1){p=home[p]||p;if(!buildings[p])return;if((S.b[p]||0)>=lvl)return;S.b[p]=lvl;BS[p].goal=lvl;changed()}
function revealFn(p,n){p=home[p]||p;reveal(p,1);const k=p+"::"+n;if(realFns[p]?.has(n)&&!fnSet.has(k)){fnSet.add(k);changed()}}
const glimpse=p=>(byPath[home[p]||p]?.imports||[]).forEach(q=>reveal(q,0.5));

// wrap the city's own entry points (function declarations are mutable module bindings)
const _showFile=showFile;showFile=function(p,keep){const r=_showFile(p,keep);reveal(p,1);glimpse(p);dressFile(p);return r};
const _showFn=showFn;showFn=function(p,n,extra){const r=_showFn(p,n,extra);revealFn(p,n);dressFn(p,n);return r};
const _showStep=showStep;showStep=function(k){const r=_showStep(k);if(P.fi!==null){const F=D.flows[P.fi],s=F.steps[P.k];revealFn(s.path,s.function);
  if(P.k===F.steps.length-1&&!flSet.has(P.fi)){flSet.add(P.fi);changed()}}return r};

// friendly names in the side panel (code names stay, smaller)
function dressFile(p){const f=byPath[p],h=panel.querySelector("h2");if(!h)return;h.textContent=fileTitle(p);
  const sub=panel.querySelector(".sub");if(sub)sub.innerHTML=`<span class="fogcode">${fogEsc(short(p))}</span> · ${fogEsc(sub.textContent)}`;
  if(f.cluster)return;panel.querySelectorAll("li[data-n]").forEach(li=>{const n=li.dataset.n,fn=f.functions.find(x=>x.name===n),known=!S.on||fnSet.has(p+"::"+n);
    li.classList.toggle("fogdim",!known);li.querySelector("b").textContent=known?fnTitle(p,n,52):"Unexplored function";
    li.querySelector("span").textContent=known?`${n}() · line ${fn?.line}`:`line ${fn?.line} · click to read it`})}
function dressFn(p,n){const h=panel.querySelector("h2");if(!h||!h.textContent.startsWith(n)||panel.querySelector("#step"))return;/* a walkthrough step already shows the narration: keep the function name as the heading */const sub=h.nextElementSibling;
  h.textContent=fnTitle(p,n,90);if(sub?.classList.contains("sub"))sub.innerHTML=`<span class="fogcode">${fogEsc(n)}()</span> · ${fogEsc(sub.textContent)}`}

// hover tooltips in the 3D city
const fray=new THREE.Raycaster(),fm=new THREE.Vector2();
renderer.domElement.addEventListener("pointermove",e=>{if(mode!=="3d"||open.path&&!S.on)return;const r=renderer.domElement.getBoundingClientRect();
  fm.set(((e.clientX-r.left)/r.width)*2-1,-((e.clientY-r.top)/r.height)*2+1);fray.setFromCamera(fm,camera);const h=fray.intersectObjects(pickables,false)[0];
  if(!h){hoverEl.style.display="none";return}const u=h.object.userData;let html;
  if(u.kind==="district"){const i=u.i,f=distFrac(i);html=S.on&&!distFrac(i,true)?"Unexplored district · walk a flow or open a building":`${fogEsc(D.districts[i].name)}${S.on?` · ${Math.round(f*100)}% explored`:""}`}
  else{const p=u.path,l=S.on?S.b[p]||0:1;
    html=l===0?"Unexplored · click to explore":l<1?`Glimpsed from a neighbour · ${fogEsc(D.districts[fileDistrict[p]].name)} · click to explore`:
      `<b>${fogEsc(fileTitle(p))}</b> · <span class="fogcode">${fogEsc(short(p))}</span>`+(u.fn&&(!S.on||fnSet.has(p+"::"+u.fn.name))?`<br>${fogEsc(fnTitle(p,u.fn.name,70))} · <span class="fogcode">${fogEsc(u.fn.name)}()</span>`:"")}
  hoverEl.innerHTML=html;hoverEl.style.display="block";hoverEl.style.left=(e.clientX-r.left)+"px";hoverEl.style.top=(e.clientY-r.top)+"px"});
renderer.domElement.addEventListener("pointerleave",()=>{if(mode==="3d")hoverEl.style.display="none"});

// ---- per-frame: lift animation, drift, colours ----
const RM=matchMedia("(prefers-reduced-motion: reduce)").matches;let lastF=0;
function fogFrame(now){requestAnimationFrame(fogFrame);const dt=Math.min(.05,(now-(lastF||now))/1000);lastF=now;
  const city=mode==="3d"&&iso.fi===null,show=S.on&&city&&!open.path;FOGG.visible=show;EDGES.visible=show;
  const k=RM?1:1-Math.exp(-dt*2.6);
  for(const p of PATHS){const st=BS[p],goal=S.on?st.goal:1;if(Math.abs(goal-st.t)>0.002)st.t+=(goal-st.t)*k;else st.t=goal;
    const v=st.t>=0.999?1:st.t;
    if(Math.abs(v-st.shown)>0.003){st.shown=v;const c=Math.min(1,v<=0.5?v*1.1:0.55+(v-0.5)*0.9);buildings[p].group.children.forEach(m=>m.material.color.copy(GREY).lerp(m.userData.c0,c))}
    if(show){const lift=Math.max(0,(st.t-0.5)*2);st.sp.material.opacity=0.82*(1-Math.min(1,st.t*1.25));st.sp.visible=st.sp.material.opacity>0.01;
      st.sp.position.set(buildings[p].x+(RM?0:Math.sin(now*0.00035+st.seed)*0.35),st.y0+lift*3.2,buildings[p].z);const sc=st.s*(1+lift*0.9);st.sp.scale.set(sc,sc*0.62,1);
      st.eg.material.opacity=st.goal===0.5?0.85:0}}
  D.districts.forEach((d,i)=>{const ps=PS[i],goal=S.on?Math.min(1,distFrac(i,true)>0?0.55+0.45*distFrac(i):0):1;if(Math.abs(goal-ps.t)>0.002)ps.t+=(goal-ps.t)*k;else ps.t=goal;
    if(Math.abs(ps.t-ps.shown)>0.003){ps.shown=ps.t;const pl=plates[i];(Array.isArray(pl.material)?pl.material:[pl.material]).forEach(m=>m.color.copy(PLATE).lerp(m.userData.c0,0.3+0.7*ps.t))}
    if(show)banks[i].forEach(sp=>{sp.material.opacity=0.42*(1-distFrac(i));sp.position.x=sp.userData.x0+(RM?0:Math.sin(now*0.00012+sp.userData.seed)*d.size*0.12);sp.position.z=sp.userData.z0+(RM?0:Math.cos(now*0.0001+sp.userData.seed)*d.size*0.06)})})}
requestAnimationFrame(fogFrame);

// ---- controls: Layers toggle + reset ----
$("layerList").insertAdjacentHTML("afterbegin",`<label title="Unexplored code stays hidden until you walk a flow or open a building."><input type="checkbox" id="fogToggle" ${S.on?"checked":""}><b>Fog of war</b><em></em><i>Unexplored code stays hidden until you walk a flow or open a building.</i></label>`);
{const m=$("fhMin"),hud=$("fogHud"),set=v=>{hud.classList.toggle("min",v);m.textContent=v?"▾":"▴";m.title=v?"Show the details":"Collapse";m.setAttribute("aria-expanded",String(!v));try{localStorage.setItem("bc-fog-min",v?"1":"0")}catch{}};
  let v=false;try{v=localStorage.getItem("bc-fog-min")==="1"}catch{}set(v);m.onclick=()=>set(!hud.classList.contains("min"))}
$("fogToggle").addEventListener("change",e=>{e.stopPropagation();S.on=e.target.checked;changed()});
$("fhReset").onclick=()=>{S.b={};fnSet.clear();flSet.clear();msSet.clear();PATHS.forEach(p=>BS[p].goal=0);store.clear();quiet=true;changed();requestAnimationFrame(()=>requestAnimationFrame(()=>quiet=false))};
window.cityFog={state:()=>({pct:pct(),fns:fnSet.size,flows:flSet.size,on:S.on,glimpsed:PATHS.filter(p=>S.b[p]===0.5).length}),reveal,reset:()=>$("fhReset").click(),open:p=>showFile(p),toggle:on=>{const t=$("fogToggle");if(t.checked!==on){t.checked=on;t.dispatchEvent(new Event("change",{bubbles:true}))}}};
milestones();renderHud();relabel();requestAnimationFrame(()=>requestAnimationFrame(()=>quiet=false));
}
/* ==== /FOG-POC ==== */
"""


def inject(h):
    if "FOG-POC" in h:
        raise ValueError("already injected: run on a fresh build")
    end = "</script></body></html>"
    for anchor in ("</style></head>", '<div id="hover"></div>', end):
        if h.count(anchor) != 1:
            raise ValueError(f"anchor not found exactly once: {anchor}")
    h = h.replace("</style></head>", CSS + "</style></head>")
    h = h.replace('<div id="hover"></div>', '<div id="hover"></div>' + HTML)
    return h.replace(end, JS + end)


def main(src, dst):
    open(dst, "w", encoding="utf-8").write(inject(open(src, encoding="utf-8").read()))
    print(f"fog injected: {dst}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
