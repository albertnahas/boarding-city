"""Add the Health layer to a built code-city page: well-known design smells, computed in the page from data
every city already has (no extra analysis, no AI), shown in red.

usage: python3 inject_health.py <built demo.html> <out.html>

- Import cycles: files that import each other in a loop break the Acyclic Dependencies Principle (Robert C. Martin).
  Found as strongly connected components of the import graph and drawn as red bridges.
- Hotspots: big files that also change often (Adam Tornhill, "Your Code as a Crime Scene": lines of code times
  commits). Needs change history, so cities built without it (web builds) leave this part out.
- Hub files: imported by many files and importing many themselves, the "god class" smell (Lanza & Marinescu,
  "Object-Oriented Metrics in Practice"): a change there ripples both ways. Marked with a warning sign.
"""
import sys

MARK, END = "/* health */", "/* /health */"
CSS_MARK, CSS_END = "/* health-css */", "/* /health-css */"

CSS = """
.hl-sec{margin:12px 0 4px;font-weight:700;font-size:13px;color:#fca5a5}
.hl-why{color:var(--mute);font-size:12px;margin:0 0 6px}
.hl-list li b{color:var(--ink)}
.hl-ok{color:#6ee7b7;font-size:12.5px}
"""

JS = r"""
/* health */
{
const H=p=>home[p]||p,ids=Object.keys(buildings);
// ---- the import graph between buildings (small files count as their block) ----
const G={};ids.forEach(p=>G[p]=new Set());
D.files.forEach(f=>{const a=H(f.path);(f.imports||[]).forEach(q=>{const b=H(q);if(b!==a&&G[a]&&G[b])G[a].add(b)})});
// import cycles: strongly connected components with more than one file (Tarjan, iterative)
const cycles=[];{let n=0;const idx={},low={},on=new Set(),st=[];
  for(const s of ids){if(s in idx)continue;const work=[[s,[...G[s]],0]];idx[s]=low[s]=n++;st.push(s);on.add(s);
    while(work.length){const top=work[work.length-1],[v,ns]=top;
      if(top[2]<ns.length){const w=ns[top[2]++];if(!(w in idx)){idx[w]=low[w]=n++;st.push(w);on.add(w);work.push([w,[...G[w]],0])}else if(on.has(w))low[v]=Math.min(low[v],idx[w])}
      else{work.pop();if(work.length){const u=work[work.length-1][0];low[u]=Math.min(low[u],low[v])}
        if(low[v]===idx[v]){const c=[];let w;do{w=st.pop();on.delete(w);c.push(w)}while(w!==v);if(c.length>1)cycles.push(c)}}}}}
cycles.sort((a,b)=>b.length-a.length);
const inCycle=new Map();cycles.forEach((c,i)=>c.forEach(p=>inCycle.set(p,i)));
// hotspots: lines x commits, for files that changed in the history window
const churn=new Map((D.layers?.cranes?.files||[]).map(([p,n])=>[H(p),n]).filter(([p])=>buildings[p]));
const hot=[...churn].map(([p,n])=>({p,n,s:(+byPath[p].lines||0)*n})).sort((a,b)=>b.s-a.s).slice(0,10);
// hub files: high fan-in and high fan-out at once
const fanIn={};ids.forEach(p=>G[p].forEach(q=>fanIn[q]=(fanIn[q]||0)+1));
const hubs=ids.map(p=>({p,i:fanIn[p]||0,o:G[p].size})).filter(x=>x.i>=8&&x.o>=8).sort((a,b)=>b.i*b.o-a.i*a.o).slice(0,8);

// ---- 3D: red bridges for cycles, a red haze over hotspots, warning signs on hubs ----
const HG=new THREE.Group();HG.visible=false;scene.add(HG);
const red=new THREE.MeshBasicMaterial({color:0xef4444,transparent:true,opacity:.75});
const top=p=>{const b=buildings[p];return new THREE.Vector3(b.x,0.15+b.H+0.2,b.z)};
cycles.forEach(c=>c.forEach(a=>G[a].forEach(b=>{if(inCycle.get(b)!==inCycle.get(a)||!G[b])return;const pa=top(a),pb=top(b),mid=pa.clone().lerp(pb,.5);mid.y=Math.max(pa.y,pb.y)+1.2+pa.distanceTo(pb)*0.2;
  HG.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(pa,mid,pb),20,.045,5),red))})));
const maxS=hot[0]?.s||1;hot.forEach(h=>{const b=buildings[h.p],w=byPath[h.p].cluster?2.9:2.2,m=new THREE.Mesh(new THREE.BoxGeometry(w,b.H+0.4,w),
  new THREE.MeshBasicMaterial({color:0xef4444,transparent:true,opacity:.12+.33*h.s/maxS,depthWrite:false}));m.position.set(b.x,0.15+(b.H+0.4)/2,b.z);HG.add(m)});
{const c=document.createElement("canvas");c.width=c.height=128;const g=c.getContext("2d");g.fillStyle="#fbbf24";g.strokeStyle="#7c2d12";g.lineWidth=8;g.lineJoin="round";
  g.beginPath();g.moveTo(64,10);g.lineTo(120,114);g.lineTo(8,114);g.closePath();g.fill();g.stroke();g.fillStyle="#7c2d12";g.font="bold 72px system-ui,sans-serif";g.textAlign="center";g.fillText("!",64,104);
  const tex=new THREE.CanvasTexture(c);tex.colorSpace=THREE.SRGBColorSpace;
  hubs.forEach(h=>{const s=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,depthTest:false}));const t=top(h.p);s.position.set(t.x,t.y+1.6,t.z);s.scale.set(1.3,1.3,1);s.renderOrder=11;HG.add(s)})}
(function frame(){HG.visible=!!ON.health&&mode==="3d"&&!open.path&&iso3.fi===null;requestAnimationFrame(frame)})();

// ---- the layer row and the report in the side panel ----
const parts=[cycles.length&&`${cycles.length} import cycle${cycles.length===1?"":"s"}`,hot.length&&`${hot.length} hotspots`,hubs.length&&`${hubs.length} hub file${hubs.length===1?"":"s"}`].filter(Boolean);
document.getElementById("layerList").insertAdjacentHTML("afterbegin",`<label title="Known design smells in red: import cycles, change hotspots and hub files."><input type="checkbox" data-k="health" id="healthToggle"><b>Health</b><em>${esc(parts[0]||"no issues found")}</em><i>Design smells in red: import cycles (red bridges), hotspots (red haze), hub files (⚠).</i></label>`);
const li=(p,sub)=>`<li data-p="${esc(p)}"><b>${esc(short(p))}</b><span>${esc(sub)}</span></li>`;
function showHealth(){stopFlow();closeBuilding();highlight(null);clearArcs();if(mode==="3d")fly(CITY,CITYD,1.1);crumb([["City",showCity],["Health"]]);
  panel.innerHTML=`<h2>Health</h2><div class="sub">${parts.length?esc(parts.join(" · ")):"No import cycles, hotspots or hub files found."} Computed from the import graph${churn.size?" and the change history":""} of ${esc(D.repo)}.</div>`+
    (cycles.length?`<div class="hl-sec">Import cycles</div><p class="hl-why">Files that import each other in a loop can't be understood, tested or changed one at a time (Acyclic Dependencies Principle). Red bridges in the city.</p>`+
      cycles.slice(0,6).map((c,i)=>{const deg=p=>[...G[p]].filter(q=>inCycle.get(q)===i).length,top=[...c].sort((a,b)=>deg(b)-deg(a));  // the most entangled files first
      return `<ul class="list hl-list"><li class="hl-head"><b>Cycle ${i+1}</b><span>${c.length} files</span></li>${top.slice(0,8).map(p=>li(p,`imports ${deg(p)} file${deg(p)===1?"":"s"} in this cycle`)).join("")}${c.length>8?`<li><span>and ${c.length-8} more</span></li>`:""}</ul>`}).join(""):"")+
    (hot.length?`<div class="hl-sec">Hotspots</div><p class="hl-why">Big files that keep changing: where bugs cluster and refactoring pays off first (lines × commits). Red haze in the city.</p><ul class="list hl-list">${hot.map(h=>li(h.p,`${byPath[h.p].lines} lines · ${h.n} commits`)).join("")}</ul>`:"")+
    (hubs.length?`<div class="hl-sec">Hub files</div><p class="hl-why">Imported by many files and importing many themselves: a change here ripples both ways. ⚠ in the city.</p><ul class="list hl-list">${hubs.map(h=>li(h.p,`used by ${h.i} files · uses ${h.o}`)).join("")}</ul>`:"")+
    (parts.length?"":`<p class="hl-ok">Nothing flagged.</p>`);
  panel.querySelectorAll("li[data-p]").forEach(el=>el.onclick=()=>showFile(el.dataset.p))}
document.getElementById("healthToggle").addEventListener("change",e=>{if(e.target.checked)showHealth()});
window.cityAPI=Object.assign(window.cityAPI||{},{health:{show:showHealth,state:()=>({cycles:cycles.map(c=>c.length),hot:hot.map(h=>h.p),hubs:hubs.map(h=>h.p)})}});
}
/* /health */
"""


def inject(h):
    # re-running on an already injected page replaces the previous injection
    for a, b in ((MARK, END), (CSS_MARK, CSS_END)):
        while a in h:
            i, j = h.index(a), h.index(b, h.index(a)) + len(b)
            h = h[:i] + h[j:]
    style_end = h.index("</style>")
    h = h[:style_end] + CSS_MARK + CSS.strip() + CSS_END + h[style_end:]
    end = h.index("</script>", h.index('<script type="module">'))
    return h[:end] + JS.strip() + "\n" + h[end:]


def main(src, out):
    open(out, "w", encoding="utf-8").write(inject(open(src, encoding="utf-8").read()))
    print(f"{out}: health layer added")


if __name__ == "__main__":
    main(*sys.argv[1:3])
