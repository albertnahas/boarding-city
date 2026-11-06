"""Add on-screen navigation controls, keyboard shortcuts and window.cityAPI to a built code-city page.

usage: python3 inject_nav.py <built demo.html> <out.html>

Post-build step: re-run it after every rebuild of the city template. It appends to the city's own
module script, so it reuses its camera, OrbitControls, fly() and 2D/isolated-view state directly.
"""
import sys

MARK = "/* nav-controls */"
END = "/* /nav-controls */"
CSS_MARK, CSS_END = "/* nav-css */", "/* /nav-css */"

CSS = """
#nav{position:absolute;z-index:9;right:12px;bottom:12px;display:grid;gap:8px;justify-items:end;user-select:none;-webkit-user-select:none;touch-action:none}
#nav .grp{display:grid;gap:4px;background:#121726e6;border:1px solid #ffffff1a;border-radius:12px;padding:6px;backdrop-filter:blur(6px)}
#nav .pad{grid-template-columns:repeat(3,40px)}#nav .row{grid-auto-flow:column}
#nav button{width:40px;height:40px;padding:0;border-radius:8px;font-size:17px;line-height:1;display:grid;place-items:center;background:#1c2335;color:var(--ink);border:1px solid #ffffff1f}
#nav button:hover{background:#26304a}#nav button:active{background:#33405f}
#nav button:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
#nav button.wide{width:auto;padding:0 10px;font-size:13px}
#nav .gap{width:40px;height:40px}
#nav.flat .rot{display:none}
#navHelp{position:absolute;z-index:9;background:#121726f2;border:1px solid #ffffff22;border-radius:12px;padding:12px 14px;font-size:12.5px;min-width:250px}
#navHelp[hidden]{display:none}
#extractBtn{background:#1c2335;color:var(--acc);border:1px solid #5eead466;font-weight:600}
#extractBtn.ready{background:var(--acc);color:#04201b;border-color:transparent}
#app.isolated #extractBtn{display:none}
.xhint{margin:0 0 10px;padding:8px 10px;border-radius:8px;background:#5eead41a;border:1px solid #5eead455;color:var(--acc);font-size:12.5px}
#xToast{position:absolute;left:50%;top:64px;transform:translateX(-50%);z-index:9;background:var(--acc);color:#04201b;border:0;border-radius:999px;padding:10px 16px;font:600 13.5px system-ui,sans-serif;cursor:pointer;box-shadow:0 6px 24px #0008}
#xToast[hidden]{display:none}
#navHelp h3{margin:0 0 8px;font-size:13px}
#navHelp dl{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin:0}
#navHelp dt{font:600 11.5px ui-monospace,Menlo,monospace;color:var(--acc);white-space:nowrap}#navHelp dd{margin:0;color:#cbd5e1}
#nav .mini{display:none}
@media (max-width:700px){#nav{gap:6px}#nav .mini{display:grid}#nav:not(.open) .rot,#nav:not(.open) .pad{display:none}#nav.open .pad [data-act="help"]{visibility:hidden}}
"""

HTML = """
<div class="grp row mini"><button data-act="zin" aria-label="Zoom in" title="Zoom in (+)">+</button><button data-act="zout" aria-label="Zoom out" title="Zoom out (−)">−</button><button data-act="more" aria-label="More controls" title="More controls" aria-expanded="false">✥</button><button data-act="help" aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)" aria-expanded="false">?</button></div>
<div class="grp row rot"><button data-act="orbitL" aria-label="Rotate left" title="Rotate left (Q)">↺</button><button data-act="tiltU" aria-label="Tilt up" title="Tilt up (R)">⤒</button><button data-act="tiltD" aria-label="Tilt down" title="Tilt down (F)">⤓</button><button data-act="orbitR" aria-label="Rotate right" title="Rotate right (E)">↻</button></div>
<div class="grp pad"><button data-act="zin" aria-label="Zoom in" title="Zoom in (+)">+</button><button data-act="panU" aria-label="Pan up" title="Pan up (W / ↑)">▲</button><button data-act="zout" aria-label="Zoom out" title="Zoom out (−)">−</button><button data-act="panL" aria-label="Pan left" title="Pan left (A / ←)">◀</button><button data-act="fit" aria-label="Fit all" title="Fit all">⤢</button><button data-act="panR" aria-label="Pan right" title="Pan right (D / →)">▶</button><button data-act="reset" aria-label="Reset view" title="Reset view (0)">⌂</button><button data-act="panD" aria-label="Pan down" title="Pan down (S / ↓)">▼</button><button data-act="help" aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)" aria-expanded="false">?</button></div>
"""

HELP = """<h3>Keyboard</h3><dl>
<dt>W A S D · arrows</dt><dd>Pan</dd><dt>Q / E</dt><dd>Rotate</dd><dt>R / F</dt><dd>Tilt</dd>
<dt>+ / −</dt><dd>Zoom</dd><dt>0</dt><dd>Reset view</dd><dt>G</dt><dd>Flow gallery</dd>
<dt>2</dt><dd>Switch 2D diagram / 3D city</dd><dt>I</dt><dd>Extract the selected flow as a diagram</dd><dt>Esc</dt><dd>Back</dd><dt>?</dt><dd>This help</dd></dl>
<p style="margin:8px 0 0;color:#8b93a7">Mouse: drag to rotate, right-drag to pan, scroll to zoom. Touch: drag and pinch.</p>"""

JS = r"""
/* nav-controls */
{
const reduce=matchMedia("(prefers-reduced-motion: reduce)").matches;
const nav=document.createElement("div");nav.id="nav";nav.setAttribute("role","toolbar");nav.setAttribute("aria-label","Map controls");nav.innerHTML=__HTML__;app.appendChild(nav);
const help=document.createElement("div");help.id="navHelp";help.hidden=true;help.setAttribute("role","dialog");help.setAttribute("aria-label","Keyboard shortcuts");help.innerHTML=__HELP__;app.appendChild(help);
const helpBtns=nav.querySelectorAll('[data-act="help"]');
const view=()=>!isoEl.hidden?"iso":mode==="3d"?"3d":"2d";
// pending motion, eased in over a few frames (instant with reduced motion)
const P={zoom:0,az:0,pol:0,px:0,py:0},isoT={s:1,x:0,y:0};
const off=new THREE.Vector3(),sph=new THREE.Spherical(),rt=new THREE.Vector3(),up=new THREE.Vector3(),fw=new THREE.Vector3();
function interrupt(){if(anim){const a=anim;anim=null;a.ok()}}
function applyIso(){const svg=isoFig.querySelector("svg");if(svg){svg.style.transformOrigin="50% 50%";svg.style.transform=`translate(${isoT.x}px,${isoT.y}px) scale(${isoT.s})`}}
new MutationObserver(applyIso).observe(isoFig,{childList:true});
new MutationObserver(()=>{if(isoEl.hidden){isoT.s=1;isoT.x=0;isoT.y=0}sync()}).observe(isoEl,{attributes:true,attributeFilter:["hidden"]});
function step(dz,da,dp,dx,dy){
  if(view()==="iso"){isoT.s=THREE.MathUtils.clamp(isoT.s*Math.exp(dz),.4,6);const k=isoFig.clientHeight*0.5;isoT.x-=dx*k;isoT.y+=dy*k;applyIso();return}
  off.subVectors(camera.position,controls.target);
  if(dz){const max=Number.isFinite(controls.maxDistance)?controls.maxDistance:1e5;off.setLength(THREE.MathUtils.clamp(off.length()*Math.exp(-dz),controls.minDistance,max))}
  if((da||dp)&&mode==="3d"){sph.setFromVector3(off);sph.theta+=da;sph.phi=THREE.MathUtils.clamp(sph.phi+dp,0.08,controls.maxPolarAngle);off.setFromSpherical(sph)}
  if(dx||dy){const d=off.length();camera.updateMatrixWorld();rt.setFromMatrixColumn(camera.matrixWorld,0).setY(0).normalize();
    camera.getWorldDirection(fw);fw.y=0;if(fw.lengthSq()<1e-3){up.setFromMatrixColumn(camera.matrixWorld,1);fw.copy(up).setY(0)}fw.normalize();
    controls.target.addScaledVector(rt,dx*d).addScaledVector(fw,dy*d)}
  camera.position.copy(controls.target).add(off)}
(function tick(){const k=reduce?1:0.22;const dz=P.zoom*k,da=P.az*k,dp=P.pol*k,dx=P.px*k,dy=P.py*k;
  if(Math.abs(dz)+Math.abs(da)+Math.abs(dp)+Math.abs(dx)+Math.abs(dy)>1e-5){step(dz,da,dp,dx,dy);P.zoom-=dz;P.az-=da;P.pol-=dp;P.px-=dx;P.py-=dy}
  requestAnimationFrame(tick)})();
function push(z,a,p,x,y){interrupt();P.zoom+=z;P.az+=a;P.pol+=p;P.px+=x;P.py+=y}
const zoomBy=f=>push(Math.log(f),0,0,0,0),rotateBy=(a,p)=>push(0,a,p||0,0,0),panBy=(x,y)=>push(0,0,0,x,y||0);
function fit(){if(view()==="iso"){isoT.s=1;isoT.x=0;isoT.y=0;applyIso();return}P.zoom=P.az=P.pol=P.px=P.py=0;
  if(mode==="2d")fit2D();else if(mode==="3d")fly(CITY,CITYD,1.1)}
function reset(){if(view()==="iso")return fit();P.zoom=P.az=P.pol=P.px=P.py=0;showCity()}
function focus(name){const q=String(name).toLowerCase(),p=Object.keys(buildings).find(k=>k.toLowerCase()===q)||Object.keys(buildings).find(k=>k.toLowerCase().includes(q));
  if(p&&!isoEl.hidden)return null;if(p)showFile(p);return p||null}
const ACTS={zin:()=>zoomBy(1.25),zout:()=>zoomBy(0.8),orbitL:()=>rotateBy(-0.14,0),orbitR:()=>rotateBy(0.14,0),tiltU:()=>rotateBy(0,-0.09),tiltD:()=>rotateBy(0,0.09),
  panU:()=>panBy(0,0.08),panD:()=>panBy(0,-0.08),panL:()=>panBy(-0.08,0),panR:()=>panBy(0.08,0)};
const moreBtn=nav.querySelector('[data-act="more"]');
const ONCE={fit,fit2:fit,reset,help:()=>toggleHelp(),more:()=>{nav.classList.toggle("open");moreBtn.setAttribute("aria-expanded",String(nav.classList.contains("open")));place()}};
// buttons: tap acts once; holding repeats after a short delay
let rep=null;const stopRep=()=>{clearTimeout(rep);clearInterval(rep);rep=null};
nav.addEventListener("pointerdown",e=>{const b=e.target.closest("button");if(!b)return;e.preventDefault();const a=b.dataset.act;
  if(ONCE[a])return ONCE[a]();ACTS[a]();stopRep();rep=setTimeout(()=>{rep=setInterval(ACTS[a],70)},320)});
["pointerup","pointerleave","pointercancel"].forEach(t=>nav.addEventListener(t,stopRep));addEventListener("blur",stopRep);
nav.addEventListener("click",e=>{if(e.detail===0){const b=e.target.closest("button");if(b){const a=b.dataset.act;(ONCE[a]||ACTS[a])()}}}); // keyboard activation
function toggleHelp(show){help.hidden=show===undefined?!help.hidden:!show;helpBtns.forEach(b=>b.setAttribute("aria-expanded",String(!help.hidden)));place()}
// keep the controls clear of the info panel: beside it on wide screens, above it on narrow ones
const pnl=document.getElementById("panel"),lay=document.getElementById("layers");
function place(){const wide=app.clientWidth>700,pr=pnl.getBoundingClientRect(),ar=app.getBoundingClientRect(),iso=view()==="iso";
  const lr=lay&&!iso&&lay.offsetParent?lay.getBoundingClientRect():null;
  const right=wide&&!iso?ar.right-pr.left+12:12;let bottom=!wide&&!iso&&!pnl.hidden?ar.bottom-pr.top+8:12;
  // narrow screens: if the Layers panel would sit under the controls, lift them above it too
  if(lr&&!wide&&lr.right>ar.right-right-nav.offsetWidth){const top=ar.bottom-bottom-nav.offsetHeight,bot=ar.bottom-bottom;
    const lifted=ar.bottom-lr.top+8,bar=document.getElementById("bar")?.getBoundingClientRect();
    // lift above the Layers panel only when that still leaves the controls on screen below the top bar
    if(lr.bottom>top&&lr.top<bot&&ar.bottom-lifted-nav.offsetHeight>=(bar?bar.bottom:ar.top)+8)bottom=lifted}
  nav.style.right=right+"px";nav.style.bottom=bottom+"px";help.style.right=right+"px";help.style.bottom=(bottom+nav.offsetHeight+8)+"px"}
function sync(){nav.classList.toggle("flat",view()!=="3d");place()}
new ResizeObserver(place).observe(pnl);if(lay)new ResizeObserver(place).observe(lay);new ResizeObserver(place).observe(app);
modeBtn.addEventListener("click",()=>setTimeout(sync,0));setInterval(sync,500);sync();
// keyboard
const KEYS={w:"panU",arrowup:"panU",s:"panD",arrowdown:"panD",a:"panL",arrowleft:"panL",d:"panR",arrowright:"panR",q:"orbitL",e:"orbitR",r:"tiltU",f:"tiltD","+":"zin","=":"zin","-":"zout",_:"zout"};
function key(k){k=String(k).toLowerCase();
  if(KEYS[k]){const a=KEYS[k];if(view()!=="3d"&&/orbit|tilt/.test(a))return false;ACTS[a]();return true}
  if(k==="0"){reset();return true}if(k==="?"){toggleHelp();return true}
  if(k==="g"){if(view()!=="iso")showGallery();return true}
  if(k==="2"){if(view()!=="iso")modeBtn.click();return true}
  if(k==="i"){extract();return true}
  if(k==="escape"){if(!help.hidden)toggleHelp(false);else if(!isoModal.hidden)document.getElementById("mClose")?.click();else if(!isoEl.hidden)document.getElementById("isoBack").click();
    else if(flow.on){stopFlow();if(mode==="2d")clear2DFlow();showGallery()}else if(mode==="2d")modeBtn.click();else if(!open.path&&mode==="3d")showCity();return true}
  return false}
addEventListener("keydown",e=>{if(e.ctrlKey||e.metaKey||e.altKey)return;const t=e.target;if(t&&(t.isContentEditable||/^(input|textarea|select)$/i.test(t.tagName)))return;
  if(e.key==="Escape"&&open.path)return; // the city's own handler closes an open building
  if(key(e.key))e.preventDefault()});
// ---- extract a flow as a diagram: a toolbar button, the I key, and a one-time hint after the first walkthrough ----
const xBtn=document.getElementById("extractBtn")||document.createElement("button");
if(!xBtn.isConnected){xBtn.id="extractBtn";xBtn.type="button";xBtn.innerHTML="⧉ Flow diagram";xBtn.title="Extract the selected flow as a 2D diagram (I)";
  const bar=document.getElementById("bar");if(bar)bar.insertBefore(xBtn,document.getElementById("modeBtn"));}
let lastFi=null,hinted=false;try{hinted=localStorage.getItem("bc-extract-hint")==="1"}catch{}
const toast=document.createElement("button");toast.id="xToast";toast.type="button";toast.hidden=true;toast.textContent="Extract this flow as a diagram ⧉";app.appendChild(toast);
const selected=()=>flow.on?flow.fi:mode==="2d"&&typeof two!=="undefined"&&two.fi!=null?two.fi:lastFi;
function extract(){toast.hidden=true;const fi=selected();if(!isoEl.hidden)return;if(fi!=null)return isolate(fi);
  showGallery();const h=document.createElement("p");h.className="xhint";h.textContent="Pick a flow to extract: play it, then press “Extract flow as diagram” (or I).";panel.prepend(h)}
xBtn.onclick=extract;toast.onclick=extract;
setInterval(()=>{if(flow.on)lastFi=flow.fi;
  // a walkthrough that played to its end (the flow player reports ended) earns the one-time hint
  if(window.cityAPI?.flow?.state?.().ended&&!hinted&&isoEl.hidden){hinted=true;try{localStorage.setItem("bc-extract-hint","1")}catch{};toast.hidden=false;setTimeout(()=>toast.hidden=true,7000)}
  const ready=selected()!=null;xBtn.classList.toggle("ready",ready);xBtn.setAttribute("aria-label",ready?`Extract “${D.flows[selected()].title}” as a diagram`:"Extract a flow as a diagram")},250);
window.cityAPI=Object.assign(window.cityAPI||{},{extract,zoomBy,rotateBy,panBy,reset,fit,focus,key,
  state:()=>({view:view(),pos:camera.position.toArray().map(v=>+v.toFixed(3)),target:controls.target.toArray().map(v=>+v.toFixed(3)),iso:{...isoT},help:!help.hidden}),
  // restores a camera saved with state(): the app shell uses it to refresh a city that is still being built without moving the viewer
  setView:s=>{if(view()!=="3d"||!s?.pos||!s?.target)return;camera.position.fromArray(s.pos);controls.target.fromArray(s.target);controls.update()}});
}
/* /nav-controls */
"""


def inject(h):
    # re-running on an already injected page replaces the previous injection
    for a, b in ((MARK, END), (CSS_MARK, CSS_END)):
        while a in h:
            i, j = h.index(a), h.index(b, h.index(a)) + len(b)
            i -= h[i - 1] == "\n"  # the newlines the injection added around its block
            j += h[j:j + 1] == "\n" and b == END
            h = h[:i] + h[j:]
    js = JS.replace("__HTML__", repr(HTML.strip())).replace("__HELP__", repr(HELP.strip()))
    style_end = h.index("</style>")
    h = h[:style_end] + "\n" + CSS_MARK + CSS.strip() + CSS_END + h[style_end:]
    module = h.index('<script type="module">')
    end = h.index("</script>", module)
    return h[:end] + js + h[end:]


def main(src, out):
    open(out, "w", encoding="utf-8").write(inject(open(src, encoding="utf-8").read()))
    print(f"{out}: navigation controls added")


if __name__ == "__main__":
    main(*sys.argv[1:3])
