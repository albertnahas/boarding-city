"""Add the learning layer to a built code-city page: GitHub links, a collapsible side panel,
a "what runs next?" quiz on every flow, and onboarding badges with a completion percentage.

usage: python3 inject_learn.py <built demo.html> <out.html>

Post-build step, run after inject_search. It appends to the city's own module script and wraps
the city's entry points (showFile, showFn, showStep, gotoStep, play, stopFlow, isolate) the way the
fog of war does, so it needs no template changes. Progress lives in localStorage, per repository.
"""
import sys

MARK, END = "/* learn */", "/* /learn */"
CSS_MARK, CSS_END = "/* learn-css */", "/* /learn-css */"

CSS = """
a.gh{color:var(--acc);text-decoration:none;white-space:nowrap}a.gh:hover{text-decoration:underline}
#panel .list li a.gh{font-size:11.5px;margin-left:6px}
#pnlMin{position:absolute;top:8px;right:8px;width:26px;height:26px;padding:0;border-radius:7px;background:#1c2335;color:var(--mute);border:1px solid #ffffff1f;font-size:13px;line-height:1;cursor:pointer}
#pnlMin:hover{color:var(--ink)}#panel #crumbs{padding-right:30px}
#panel.min{width:auto;max-width:340px;padding:8px 12px}#panel.min #body{display:none}#panel.min #crumbs{margin:0}
@media (max-width:700px){#panel.min{left:auto;max-height:none}}
#learnBtn{background:#1c2335;color:var(--ink);border:1px solid #ffffff1f;font-weight:600}
#learnBtn b{color:var(--acc);font-variant-numeric:tabular-nums}
#learnToast{position:absolute;left:50%;top:60px;transform:translate(-50%,-30px);opacity:0;z-index:14;background:#0f1424f5;border:1px solid #fbbf2488;color:#fde68a;padding:9px 16px;border-radius:999px;font:600 13.5px system-ui,sans-serif;transition:.4s;pointer-events:none}
#learnToast.on{transform:translate(-50%,0);opacity:1}
.ob-top{display:grid;grid-template-columns:64px 1fr;gap:12px;align-items:center;margin:4px 0 12px}
.ob-ring{width:64px;height:64px;border-radius:50%;display:grid;place-items:center;font:700 16px system-ui,sans-serif}
.ob-ring span{width:50px;height:50px;border-radius:50%;background:#121726;display:grid;place-items:center}
.ob-badge{border:1px solid #ffffff14;border-radius:10px;padding:9px 10px;margin:0 0 8px;background:#ffffff05}
.ob-badge.won{border-color:#fbbf2466;background:#fbbf240d}
.ob-badge summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:30px 1fr auto;gap:2px 8px;align-items:center}
.ob-badge summary::-webkit-details-marker{display:none}
.ob-badge .ic{font-size:20px;grid-row:span 2;filter:grayscale(1);opacity:.45}.ob-badge.won .ic{filter:none;opacity:1}
.ob-badge .t{font-weight:700;font-size:13px}.ob-badge .core{font:600 10px system-ui,sans-serif;color:var(--acc);border:1px solid #5eead466;border-radius:999px;padding:0 6px;vertical-align:1px}.ob-badge .n{font-size:12px;color:var(--mute);font-variant-numeric:tabular-nums}
.ob-badge .why{grid-column:2/-1;color:var(--mute);font-size:12px}
.ob-bar{height:4px;border-radius:2px;background:#ffffff14;margin-top:7px;overflow:hidden}.ob-bar u{display:block;height:100%;background:var(--acc)}
.ob-badge.won .ob-bar u{background:#fbbf24}
.ob-items{margin:8px 0 0;padding:0;list-style:none}
.ob-items li{display:grid;grid-template-columns:18px 1fr;gap:0 6px;padding:5px 6px;border-radius:6px;font-size:12.5px;cursor:pointer}
.ob-items li:hover{background:#ffffff0d}.ob-items li i{font-style:normal;color:var(--mute)}.ob-items li.ok i{color:#34d399}
.ob-items li small{grid-column:2;color:var(--mute);font-size:11.5px}
.ob-reset{background:none;border:0;color:var(--mute);font-size:12px;text-decoration:underline;cursor:pointer;padding:0;margin-top:4px}
.flowitem .qzGo{margin:6px 6px 0 0}
#plQuiz{background:#fbbf24;color:#1a1300;border:0;font-weight:700}
#player.quiz #plPlay,#player.quiz #plNext,#player.quiz #plLast,#player.quiz #plLoop,#player.quiz #plSpeed,#player.quiz #plSteps,#player.quiz #plQuiz{display:none}
#player.quiz~#plList{display:none}
#player.quiz #plTrack b.ahead{pointer-events:none;opacity:.25}
#qz{width:min(560px,100%);position:relative;display:grid;gap:6px}#qz[hidden]{display:none}
#qz .q{font-size:13px;text-align:center}#qz .q code{font:600 12.5px ui-monospace,Menlo,monospace;color:var(--flow)}#qz .q em{color:var(--mute);font-style:normal;font-size:12px}
#qz .row{display:flex;gap:6px;flex-wrap:wrap;justify-content:center}#qz .row[hidden]{display:none}
#qzIn{flex:1 1 200px;min-width:0;height:32px;box-sizing:border-box;padding:0 10px;border-radius:8px;border:1px solid #ffffff2e;background:#0f1320;color:var(--ink);font:13px ui-monospace,Menlo,monospace}
#qzIn:focus{outline:2px solid var(--flow);outline-offset:1px}
#qz .row button{padding:5px 10px;font-size:13px}
#qzSubmit{background:var(--flow);color:#1a1300;border:0;font-weight:700}
#qzList{position:absolute;bottom:calc(100% + 4px);left:0;right:0;margin:0;padding:4px;list-style:none;max-height:240px;overflow:auto;background:#121726fa;border:1px solid #ffffff26;border-radius:10px;box-shadow:0 -10px 30px #0008;z-index:2}
#qzList[hidden]{display:none}
#qzList li{display:flex;justify-content:space-between;gap:10px;padding:6px 8px;border-radius:6px;cursor:pointer;font:12.5px ui-monospace,Menlo,monospace}
#qzList li[aria-selected=true]{background:#ffffff14}#qzList li span{color:var(--mute);font:11.5px system-ui,sans-serif;white-space:nowrap}
#qzFb{font-size:13px;text-align:center;border-radius:8px;padding:6px 10px}#qzFb[hidden]{display:none}
#qzFb.ok{background:#05966933;color:#6ee7b7;border:1px solid #34d39966}
#qzFb.half{background:#d9770633;color:#fcd34d;border:1px solid #fbbf2466}
#qzFb.no{background:#e11d4833;color:#fda4af;border:1px solid #f43f5e66;animation:qzShake .35s}
#qzFb code{font:600 12.5px ui-monospace,Menlo,monospace}
#qzFb button{margin-left:8px;padding:3px 10px;font-size:12.5px}
#qz .score{font-size:12px;color:var(--mute);text-align:center;font-variant-numeric:tabular-nums}
#player.qok{box-shadow:0 0 0 2px #34d399,0 0 24px #34d39955}#player.qno{box-shadow:0 0 0 2px #f43f5e,0 0 24px #f43f5e55}
@keyframes qzShake{20%,60%{transform:translateX(-6px)}40%,80%{transform:translateX(6px)}}
@media (prefers-reduced-motion:reduce){#qzFb.no{animation:none}#learnToast{transition:none}}
"""

JS = r"""
/* learn */
{
const LKEY="boarding-city-learn-"+(D.meta?.key||D.repo);
const load=()=>{try{return JSON.parse(localStorage.getItem(LKEY)||"null")||{}}catch{return {}}};
const L=Object.assign({files:[],fns:[],flows:[],quiz:{},gh:0,ghost:[],diagram:false,won:[]},load());
const files=new Set(L.files),fns=new Set(L.fns),flowsSeen=new Set(L.flows),ghosts=new Set(L.ghost),won=new Set(L.won);
function save(){L.files=[...files];L.fns=[...fns];L.flows=[...flowsSeen];L.ghost=[...ghosts];L.won=[...won];try{localStorage.setItem(LKEY,JSON.stringify(L))}catch{}}
const H=p=>home[p]||p,hexOf=i=>"#"+COLORS[i%COLORS.length].toString(16).padStart(6,"0");

// ---- GitHub links: every file and function opens at the exact commit the city was built from ----
const ghURL=(p,line)=>D.meta?.repo&&`https://github.com/${D.meta.repo}/blob/${D.meta.sha}/${p.split("/").map(encodeURIComponent).join("/")}${line?"#L"+line:""}`;
const ghA=(p,line,label="GitHub ↗")=>{const u=ghURL(p,line);return u?`<a class="gh" href="${u}" target="_blank" rel="noopener" title="Open ${esc(p)}${line?" at line "+line:""} on GitHub">${label}</a>`:""};
panel.addEventListener("click",e=>{const a=e.target.closest("a.gh");if(!a)return;e.stopPropagation();L.gh++;save();check()});
function linkFile(p){const f=byPath[p],sub=panel.querySelector("h2+.sub");
  if(!f.cluster){if(sub)sub.insertAdjacentHTML("beforeend"," · "+ghA(p));return}
  panel.querySelectorAll(".list li").forEach((li,k)=>{const m=f.members[k];if(m)li.querySelector("b")?.insertAdjacentHTML("afterend",ghA(m.path,0,"↗"))})}
function linkFn(p,n){const sub=panel.querySelector("h2+.sub"),fn=byPath[p]?.functions.find(x=>x.name===n),s=flow.on?D.flows[P.fi].steps[P.k]:null;
  const line=fn?.line??(s&&s.path===p&&s.function===n?s.line:0);if(sub)sub.insertAdjacentHTML("beforeend"," · "+ghA(p,line))}

// ---- collapsible side panel: tucks away after the overview; opening something new brings it back ----
const pnl=document.getElementById("panel"),minB=document.createElement("button");minB.id="pnlMin";minB.type="button";pnl.prepend(minB);
let mini=false;try{mini=localStorage.getItem("bc-panel-min")==="1"}catch{}
function setMin(v){mini=v;pnl.classList.toggle("min",v);minB.textContent=v?"⟨":"⟩";minB.title=v?"Show the side panel":"Hide the side panel";minB.setAttribute("aria-label",minB.title);
  minB.setAttribute("aria-expanded",String(!v));try{localStorage.setItem("bc-panel-min",v?"1":"0")}catch{}}
minB.onclick=()=>setMin(!mini);setMin(mini);
const expand=()=>{if(mini&&!flow.on)setMin(false)};

// ---- what the city teaches: the facts each badge is built from ----
const real=p=>buildings[H(p)]&&!byPath[H(p)]?.cluster;
const ENTRY=(D.layers?.entries||[]).filter(([p])=>buildings[H(p)]).slice(0,5).map(([p,n])=>({p,sub:`${n} user action${n===1?"":"s"} start here`}));
const fanIn={};D.files.forEach(f=>(f.imports||[]).forEach(q=>{q=H(q);if(q!==f.path)fanIn[q]=(fanIn[q]||0)+1}));
const MAIN=Object.entries(fanIn).filter(([p])=>real(p)).sort((a,b)=>b[1]-a[1]).slice(0,5).map(([p,n])=>({p,sub:`${n} files depend on it`}));
const HOT=(D.layers?.cranes?.files||[]).filter(([p])=>buildings[H(p)]).slice(0,5).map(([p,n])=>({p,sub:`${n} commits in the last 90 days`}));
const PLANT=(D.layers?.power?.plants||[]).map(pl=>{const r=(D.layers.power.lines||[]).filter(l=>l[1]===pl&&buildings[H(l[0])]).sort((a,b)=>(b[3]||0)-(a[3]||0))[0];return r&&{p:r[0],sub:`biggest user of ${pl}`}}).filter(Boolean);
const flowIdx=D.flows.map((F,i)=>i);
const qBest=fi=>L.quiz[fi]?.best??-1,qMax=fi=>2*(D.flows[fi].steps.length-1);
const fileItems=list=>list.map(x=>({label:short(x.p),sub:x.sub,ok:files.has(H(x.p)),go:()=>showFile(H(x.p))}));
const BADGES=[
  {id:"map",ic:"🗺️",t:"City map",why:"The main areas of the code and what each one owns.",
   items:()=>D.districts.map((d,i)=>({label:d.name,sub:d.summary,ok:[...files].some(p=>fileDistrict[p]===i),go:()=>showDistrict(i)}))},
  ENTRY.length&&{id:"doors",ic:"🚪",t:"Front doors",why:"Where user actions enter the code: start reading a feature here.",items:()=>fileItems(ENTRY)},
  MAIN.length&&{id:"main",ic:"🛣️",t:"Main streets",why:"The files most of the code depends on: change them with care.",items:()=>fileItems(MAIN)},
  HOT.length&&{id:"hot",ic:"🏗️",t:"Busy sites",why:"The files that change most: your first change will likely land near one.",items:()=>fileItems(HOT)},
  PLANT.length&&{id:"power",ic:"⚡",t:"Power grid",why:"Where shared state lives and who uses it most.",items:()=>fileItems(PLANT)},
  {id:"ride",ic:"🚇",t:"Commuter",why:"Watch every traced flow from the user's click to the last function.",
   items:()=>flowIdx.map(fi=>({label:D.flows[fi].title,sub:`${D.flows[fi].steps.length} steps`,ok:flowsSeen.has(fi),go:()=>startFlow(fi)}))},
  {id:"quiz",ic:"🎯",t:"Next-stop predictor",why:"Finish the “what runs next?” quiz on every flow.",
   items:()=>flowIdx.map(fi=>({label:D.flows[fi].title,sub:qBest(fi)<0?"not taken yet":`best ${qBest(fi)}/${qMax(fi)}`,ok:qBest(fi)>=0,go:()=>startQuiz(fi)}))},
  {id:"sharp",ic:"🧠",t:"Sharp mind",why:"Score 80% or more on a flow quiz: you can predict how the code runs.",
   need:Math.min(3,D.flows.length),items:()=>flowIdx.map(fi=>({label:D.flows[fi].title,sub:qBest(fi)<0?"not taken yet":`best ${Math.round(100*qBest(fi)/qMax(fi))}%`,ok:qBest(fi)>=0.8*qMax(fi),go:()=>startQuiz(fi)}))},
  {id:"ghost",ic:"👻",t:"Ghost hunter",why:"Inspect functions no user action reaches: unused code, or code that only runs dynamically.",
   need:3,items:()=>[...ghosts].map(k=>{const [p,n]=k.split("::");return {label:n+"()",sub:short(p),ok:true,go:()=>showFn(p,n)}})},
  {id:"src",ic:"🔎",t:"Source diver",why:"Open the real source on GitHub from the city.",need:3,count:()=>L.gh},
  {id:"diagram",ic:"⧉",t:"Diagram maker",why:"Extract a flow as a 2D diagram you can save as an image or paste into docs.",need:1,count:()=>+L.diagram},
].filter(Boolean);
const CORE=["map","doors","main","ride","quiz"];
function prog(b){if(b.count){const n=Math.min(b.need,b.count());return {n,of:b.need}}
  const it=b.items(),of=b.need||it.length;return {n:Math.min(of,it.filter(x=>x.ok).length),of,it}}
const frac=b=>{const r=prog(b);return r.of?r.n/r.of:1};
const overall=()=>Math.round(100*BADGES.reduce((a,b)=>a+frac(b),0)/BADGES.length);
const ready=()=>CORE.every(id=>{const b=BADGES.find(x=>x.id===id);return !b||frac(b)>=1});

// ---- the onboarding view, in the side panel ----
const btn=document.createElement("button");btn.id="learnBtn";btn.type="button";btn.title="Your onboarding badges and progress";
document.getElementById("bar").insertBefore(btn,document.getElementById("paperBtn"));
const toastEl=document.createElement("div");toastEl.id="learnToast";toastEl.setAttribute("role","status");app.appendChild(toastEl);
let tt=0;function toast(t){toastEl.textContent=t;toastEl.classList.add("on");clearTimeout(tt);tt=setTimeout(()=>toastEl.classList.remove("on"),3200)}
let viewing=false;
function showOnboarding(){stopFlow();closeBuilding();highlight(null);clearArcs();setMin(false);viewing=true;
  const q=overall(),open=new Set([...panel.querySelectorAll(".ob-badge[open]")].map(d=>d.dataset.id));
  crumb([["City",showCity],["My onboarding"]]);
  panel.innerHTML=`<h2>My onboarding</h2><div class="ob-top"><div class="ob-ring" style="background:conic-gradient(var(--acc) ${q*3.6}deg,#ffffff14 0)"><span>${q}%</span></div>
    <div class="sub">${won.size} of ${BADGES.length} badges in ${esc(D.repo)}. ${ready()?"🎓 <b>Ready for your first change.</b> You know where features start, what everything depends on and how the main flows run.":"Earn the 5 core badges to be ready for your first change."}</div></div>`+
    BADGES.map(b=>{const r=prog(b),w=won.has(b.id);
      return `<details class="ob-badge${w?" won":""}" data-id="${b.id}"${open.has(b.id)?" open":""}><summary><span class="ic" aria-hidden="true">${b.ic}</span><span class="t">${esc(b.t)}${CORE.includes(b.id)?' <span class="core">core</span>':""}</span><span class="n">${r.n}/${r.of}${w?" ✓":""}</span><span class="why">${esc(b.why)}</span></summary>
        <div class="ob-bar"><u style="width:${100*r.n/r.of}%"></u></div>${r.it&&r.it.length?`<ul class="ob-items">${r.it.map((x,k)=>`<li class="${x.ok?"ok":""}" data-k="${k}"><i>${x.ok?"✓":"○"}</i><span>${esc(x.label)}</span><small>${esc(x.sub||"")}</small></li>`).join("")}</ul>`:""}</details>`}).join("")+
    `<button class="ob-reset" type="button">Reset my onboarding progress</button>`;
  panel.querySelectorAll(".ob-badge").forEach(d=>{const b=BADGES.find(x=>x.id===d.dataset.id);d.querySelectorAll(".ob-items li").forEach(li=>li.onclick=()=>{viewing=false;prog(b).it[+li.dataset.k].go()})});
  panel.querySelector(".ob-reset").onclick=()=>{if(!confirmReset())return;files.clear();fns.clear();flowsSeen.clear();ghosts.clear();won.clear();Object.assign(L,{quiz:{},gh:0,diagram:false});save();renderBtn();showOnboarding()}}
let armed=0;function confirmReset(){const b=panel.querySelector(".ob-reset");if(Date.now()-armed<4000)return true;armed=Date.now();b.textContent="Click again to erase all progress";return false}
function renderBtn(){btn.innerHTML=`🎓 Onboarding <b>${overall()}%</b>`}
btn.onclick=showOnboarding;
function check(){let fresh=null;for(const b of BADGES)if(!won.has(b.id)&&frac(b)>=1){won.add(b.id);fresh=b}
  if(ready()&&!won.has("ready")){won.add("ready");toast("🎓 Ready for your first change!")}else if(fresh)toast(`${fresh.ic} Badge earned: ${fresh.t}`);
  save();renderBtn();if(viewing&&panel.querySelector(".ob-top"))showOnboarding()}
renderBtn();

// ---- track what was opened (wrapping the city's entry points, after the fog's own wrappers) ----
const _showFile=showFile;showFile=function(p,keep){viewing=false;if(!keep)expand();const r=_showFile(p,keep);files.add(H(p));linkFile(p);check();return r};
const _showFn=showFn;showFn=function(p,n,extra){viewing=false;if(!flow.on)expand();const r=_showFn(p,n,extra);files.add(H(p));fns.add(p+"::"+n);if(deadFn(p,n))ghosts.add(p+"::"+n);linkFn(p,n);check();return r};
const _showDistrict=showDistrict;showDistrict=function(i){viewing=false;expand();return _showDistrict(i)};
const _isolate=isolate;isolate=function(fi,instant){if(Q.on)return;L.diagram=true;check();return _isolate(fi,instant)};
const _showStep=showStep;showStep=function(k){const r=_showStep(k);if(P.fi!==null&&P.k===D.flows[P.fi].steps.length-1&&!Q.on&&!flowsSeen.has(P.fi)){flowsSeen.add(P.fi);check()}return r};

// ---- the quiz: at every step, predict the function that runs next ----
const Q={on:false,fi:null,answered:new Set(),pts:0,right:0,tries:0,hint:false};
const ALL=[...new Map(D.files.flatMap(f=>f.cluster?[]:f.functions.map(fn=>[f.path+"::"+fn.name,{n:fn.name,p:f.path}]))
  .concat(D.flows.flatMap(F=>F.steps.map(s=>[s.path+"::"+s.function,{n:s.function,p:s.path}])))).values()];
ALL.forEach(x=>x.l=x.n.toLowerCase());
const pl=document.getElementById("player"),row=document.getElementById("plRow");
const qBtn=document.createElement("button");qBtn.id="plQuiz";qBtn.type="button";qBtn.textContent="🎯 Quiz me";qBtn.title="Restart this flow as a quiz: predict each next function";
row.insertBefore(qBtn,document.getElementById("plClose"));qBtn.onclick=()=>startQuiz(P.fi);
const box=document.createElement("div");box.id="qz";box.hidden=true;
box.innerHTML=`<div class="q" id="qzQ"></div><div class="row"><input id="qzIn" type="text" autocomplete="off" spellcheck="false" placeholder="Type a function name…" role="combobox" aria-expanded="false" aria-controls="qzList" aria-autocomplete="list" aria-labelledby="qzQ">
  <button id="qzSubmit" type="button">Submit</button><button id="qzHint" type="button" title="Show which file it lives in (the answer then scores 1 point)">Hint</button><button id="qzSkip" type="button" title="Reveal the answer (0 points)">Reveal</button><button id="qzExit" type="button">Exit quiz</button></div>
  <ul id="qzList" role="listbox" hidden></ul><div id="qzFb" role="status" hidden></div><div class="score" id="qzScore"></div>`;
pl.insertBefore(box,document.getElementById("plTrack"));
const $q=id=>document.getElementById(id),qin=$q("qzIn"),qlist=$q("qzList"),qfb=$q("qzFb");
const target=()=>D.flows[Q.fi].steps[P.k+1];
function renderScore(){const N=D.flows[Q.fi].steps.length;
  [...$("plTrack").children].forEach((b,k)=>{b.classList.toggle("ahead",k>P.k&&!Q.answered.has(k));b.removeAttribute("title")});
  $q("qzScore").textContent=`Score ${Q.pts}/${2*Q.tries} · ${Q.right} of ${Q.tries} right · ${N-1-Q.answered.size} to go`}
function renderQ(){const F=D.flows[Q.fi],N=F.steps.length,s=F.steps[P.k],t=target(),rowEl=box.querySelector(".row");renderScore();
  if(!t||Q.answered.has(P.k+1)){rowEl.hidden=true;$q("qzQ").innerHTML=t?`You answered step ${P.k+2} already: press <b>N</b> or click its number on the track to go on.`:"";return finishIfDone()}
  rowEl.hidden=false;qin.disabled=false;
  const ind=t.link.startsWith("indirect");
  $q("qzQ").innerHTML=`Step ${P.k+2}/${N}: after <code>${esc(s.function)}()</code>, what runs next? <em>${ind?"(reached via an event, callback or state change)":"(a direct call)"}</em>${Q.hint?`<br><em>Hint: it lives in <b>${esc(short(t.path))}</b>, ${esc(D.districts[fileDistrict[H(t.path)]]?.name||"")}</em>`:""}`}
function finishIfDone(){const F=D.flows[Q.fi];if(Q.answered.size<F.steps.length-1)return;
  const max=qMax(Q.fi),best=Math.max(qBest(Q.fi),Q.pts);L.quiz[Q.fi]={best,last:Q.pts};flowsSeen.add(Q.fi);check();
  fb(Q.pts>=0.8*max?"ok":Q.pts>=0.5*max?"half":"no",`Quiz done: <b>${Q.pts}/${max}</b> (${Q.right} of ${F.steps.length-1} right first time). Best ${best}/${max}.`,
    `<button type="button" data-a="retry">Retry</button><button type="button" data-a="gallery">Other flows</button>`)}
function fb(cls,html,act=""){qfb.className=cls;qfb.innerHTML=html+act;qfb.hidden=false;pl.classList.remove("qok","qno");if(cls!=="half")void pl.offsetWidth,pl.classList.add(cls==="ok"?"qok":"qno");setTimeout(()=>pl.classList.remove("qok","qno"),900)}
qfb.addEventListener("click",e=>{const a=e.target.closest("button")?.dataset.a;if(a==="next")advance();else if(a==="retry")startQuiz(Q.fi);else if(a==="gallery"){stopFlow();showGallery()}});
let advancing=false;
function advance(){qfb.hidden=true;Q.hint=false;advancing=true;const N=D.flows[Q.fi].steps.length;let j=1;while(j<N&&Q.answered.has(j))j++;const r=_gotoStep(j-1);advancing=false;Promise.resolve(r).then(()=>{renderQ();if(!box.querySelector(".row").hidden)qin.focus()})}
function grade(text){const t=target();if(!t||Q.answered.has(P.k+1))return;const v=text.trim().replace(/\(\)$/,"").toLowerCase();if(!v)return qin.focus();
  const name=v.split(/\s+·\s+|\s+/)[0],pick=hits[sel]&&!qlist.hidden?hits[sel]:null;
  const sameName=(pick?pick.l:name)===t.function.toLowerCase(),samePath=pick?H(pick.p)===H(t.path):true;
  Q.answered.add(P.k+1);Q.tries++;qin.value="";closeAC();qin.disabled=true;
  const where=`<code>${esc(t.function)}()</code> in ${esc(short(t.path))}`;
  if(sameName&&samePath){const p=Q.hint?1:2;Q.pts+=p;Q.right++;fb("ok",`✓ Right: ${where}. +${p}`);setTimeout(advance,1100)}
  else if(sameName){Q.pts+=1;fb("half",`Right name, but this one is ${where}. +1`,`<button type="button" data-a="next">Continue ▸</button>`)}
  else fb("no",`✗ Not quite. It was ${where}.`,`<button type="button" data-a="next">Continue ▸</button>`);
  renderScore();setTimeout(()=>qfb.querySelector("button")?.focus(),0)}
// autocomplete over every function in the city
let hits=[],sel=-1;
function closeAC(){qlist.hidden=true;qin.setAttribute("aria-expanded","false");sel=-1}
function ac(){const q=qin.value.trim().replace(/\(\)$/,"").toLowerCase();if(!q){hits=[];return closeAC()}
  hits=ALL.map(x=>[x.l===q?3:x.l.startsWith(q)?2:x.l.includes(q)?1:0,x]).filter(([s])=>s).sort((a,b)=>b[0]-a[0]||a[1].n.length-b[1].n.length).slice(0,8).map(([,x])=>x);
  sel=hits.length?0:-1;qlist.hidden=!hits.length;qin.setAttribute("aria-expanded",String(!!hits.length));
  qlist.innerHTML=hits.map((x,k)=>`<li id="qz${k}" role="option" aria-selected="${k===sel}" data-k="${k}">${esc(x.n)}()<span>${esc(short(x.p))}</span></li>`).join("");
  qin.setAttribute("aria-activedescendant",sel>=0?"qz"+sel:"")}
function mv(d){if(!hits.length)return;sel=(sel+d+hits.length)%hits.length;[...qlist.children].forEach((li,k)=>li.setAttribute("aria-selected",String(k===sel)));
  qin.setAttribute("aria-activedescendant","qz"+sel);qlist.children[sel].scrollIntoView({block:"nearest"})}
qin.addEventListener("input",ac);
qin.addEventListener("keydown",e=>{if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();mv(e.key==="ArrowDown"?1:-1)}
  else if(e.key==="Enter"){e.preventDefault();grade(sel>=0&&!qlist.hidden?hits[sel].n:qin.value)}
  else if(e.key==="Escape"){e.preventDefault();e.stopPropagation();qlist.hidden?qin.blur():closeAC()}});
qlist.addEventListener("pointerdown",e=>{const li=e.target.closest("li");if(!li)return;e.preventDefault();sel=+li.dataset.k;grade(hits[sel].n)});
qin.addEventListener("blur",()=>setTimeout(closeAC,120));
$q("qzSubmit").onclick=()=>grade(sel>=0&&!qlist.hidden?hits[sel].n:qin.value);
$q("qzHint").onclick=()=>{Q.hint=true;renderQ();qin.focus()};
$q("qzSkip").onclick=()=>{const t=target();if(!t||Q.answered.has(P.k+1))return;Q.answered.add(P.k+1);Q.tries++;closeAC();qin.disabled=true;
  fb("no",`It was <code>${esc(t.function)}()</code> in ${esc(short(t.path))}.`,`<button type="button" data-a="next">Continue ▸</button>`);renderScore();setTimeout(()=>qfb.querySelector("button")?.focus(),0)};
$q("qzExit").onclick=()=>endQuiz();
async function startQuiz(fi){viewing=false;if(iso.fi!==null)await unisolate();if(mode==="2d")await to3D();
  if(P.fi!==fi)openPlayer(fi);pause();Object.assign(Q,{on:true,fi,answered:new Set(),pts:0,right:0,tries:0,hint:false});
  pl.classList.add("quiz");box.hidden=false;qfb.hidden=true;modeBtn.disabled=true;await _gotoStep(0);renderQ();qin.focus()}
function endQuiz(){if(!Q.on)return;Q.on=false;pl.classList.remove("quiz","qok","qno");box.hidden=true;modeBtn.disabled=false;closeAC();
  const F=D.flows[Q.fi];[...$("plTrack").children].forEach((b,k)=>{b.classList.remove("ahead");b.title=`${k+1}. ${F.steps[k].function}()`})}
// while quizzing: no autoplay, and no jumping ahead of what has been answered
const _gotoStep=gotoStep;gotoStep=function(k){if(Q.on&&!advancing){qfb.hidden=true;const N=D.flows[Q.fi].steps.length;k=Math.max(0,Math.min(N-1,k));
    for(let j=P.k+1;j<=k;j++)if(!Q.answered.has(j)){const r=_gotoStep(j-1);Promise.resolve(r).then(()=>{renderQ();qin.focus()});return r}}
  const r=_gotoStep(k);if(Q.on)Promise.resolve(r).then(renderQ);return r};
const _play=play;play=function(){if(Q.on){qin.focus();return}return _play()};
const _stopFlow=stopFlow;stopFlow=function(){if(Q.on)endQuiz();return _stopFlow()};
// a quiz button on every flow in the gallery
const _showGallery=showGallery;showGallery=function(){viewing=false;setMin(false);const r=_showGallery();
  panel.querySelectorAll("li.flowitem").forEach(li=>{const fi=+li.dataset.fi,b=document.createElement("button");b.type="button";b.className="qzGo";
    b.textContent=qBest(fi)<0?"🎯 Quiz":`🎯 Quiz · best ${qBest(fi)}/${qMax(fi)}`;b.onclick=e=>{e.stopPropagation();startQuiz(fi)};li.querySelector(".isoLink")?.before(b)});return r};
document.getElementById("galleryBtn").onclick=showGallery;  // the button was bound to the unwrapped function
window.cityAPI=Object.assign(window.cityAPI||{},{learn:{state:()=>({pct:overall(),won:[...won],badges:BADGES.map(b=>({id:b.id,...prog(b),it:undefined})),quiz:{...Q,answered:[...Q.answered]},min:mini}),
  show:showOnboarding,quiz:startQuiz,answer:grade}});
}
/* /learn */
"""


def main(src, out):
    h = open(src, encoding="utf-8").read()
    # re-running on an already injected page replaces the previous injection
    for a, b in ((MARK, END), (CSS_MARK, CSS_END)):
        while a in h:
            i, j = h.index(a), h.index(b, h.index(a)) + len(b)
            h = h[:i] + h[j:]
    style_end = h.index("</style>")
    h = h[:style_end] + CSS_MARK + CSS.strip() + CSS_END + h[style_end:]
    end = h.index("</script>", h.index('<script type="module">'))
    h = h[:end] + JS.strip() + "\n" + h[end:]
    open(out, "w", encoding="utf-8").write(h)
    print(f"{out}: learning layer added")


if __name__ == "__main__":
    main(*sys.argv[1:3])
