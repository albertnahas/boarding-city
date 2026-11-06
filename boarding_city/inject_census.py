"""Add a "City stats" card to a built code-city page's overview: what the skyline says about the code, in plain
sentences with real numbers (computed in the page from data every city already has, no AI).

usage: python3 inject_census.py <built demo.html> <out.html>
"""
import sys

MARK, END = "/* census */", "/* /census */"
CSS_MARK, CSS_END = "/* census-css */", "/* /census-css */"

CSS = """
.census{margin:10px 0 12px;padding:10px 12px;border:1px solid #5eead433;border-radius:10px;background:#5eead40a}
.census h4{margin:0 0 6px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--acc)}
.census ul{margin:0;padding:0;list-style:none;display:grid;gap:6px}
.census li{font-size:12.5px;line-height:1.4;color:#d5dbe8}.census li b{color:var(--ink)}
.census li a{color:var(--acc);cursor:pointer;text-decoration:none}.census li a:hover{text-decoration:underline}
.census small{display:block;margin-top:6px;color:var(--mute);font-size:11.5px}
"""

JS = r"""
/* census */
{
// every source file, small ones included (they live inside their block)
const all=D.files.flatMap(f=>f.cluster?f.members.map(m=>({p:m.path,l:+m.lines||0,home:f.path})):[{p:f.path,l:+f.lines||0,home:f.path}]).sort((a,b)=>b.l-a.l);
const total=all.reduce((a,x)=>a+x.l,0),n=all.length,fmt=v=>v.toLocaleString("en"),pct=v=>v<.01?"under 1%":Math.round(100*v)+"%";
// generated or data files: tall, but not where the logic lives
const DATA=/(\.gen\.|generated|\/data\/|\.d\.ts$|constants?\.|bindings|icons?\.|\.json$|locales?\/|fixtures?|mocks?\/|\.min\.)/i;
const facts=[];
if(n>=5){const top=all.slice(0,Math.max(1,Math.round(n/10))),share=top.reduce((a,x)=>a+x.l,0)/total;
  facts.push(share>=.45?`<b>Downtown-heavy skyline.</b> The biggest 10% of files hold ${pct(share)} of the code: most of the work happens in a few towers.`
    :share<=.3?`<b>Even skyline.</b> The biggest 10% of files hold only ${pct(share)} of the code: the work is spread out.`
    :`<b>Mixed skyline.</b> The biggest 10% of files hold ${pct(share)} of the code.`)}
const logic=all.filter(x=>!DATA.test(x.p)),data=all.slice(0,5).filter(x=>DATA.test(x.p));
const churn=new Map((D.layers?.cranes?.files||[]).map(([p,c])=>[p,c])),commits=D.layers?.cranes?.commits;
if(logic[0]){const t=logic[0],c=churn.get(t.p);facts.push(`<b>Tallest tower:</b> <a data-p="${esc(t.home)}">${esc(short(t.p))}</a>, ${fmt(t.l)} lines, ${pct(t.l/total)} of all the code.${t.l>3000?" A file that size is hard to hold in your head":""}${c&&commits?`${t.l>3000?", and it":" It"} changed in ${c} of the last ${commits} commits.`:t.l>3000?".":""}`)}
if(data.length)facts.push(`<b>Some tall towers are data, not logic:</b> ${data.map(x=>`<a data-p="${esc(x.home)}">${esc(short(x.p))}</a>`).join(", ")} (generated files, constants or assets). Skip them when reading the code.`);
const tiny=all.filter(x=>x.l<50).length,mid=all[Math.floor(n/2)]?.l;
if(n)facts.push(`<b>${fmt(tiny)} cottages</b> under 50 lines (${pct(tiny/n)} of files): small helpers and glue. A typical file has ${fmt(mid)} lines.`);
const sampled=D.meta?.files>n?D.meta.files:0;  // big repos are mapped from a sample
const R=Object.entries(D.reach||{}),dead=R.filter(([,r])=>r.n===0&&r.b!=="infra").length;
if(R.length&&dead)facts.push(`<b>${pct(dead/R.length)} of functions</b> (${fmt(dead)}) aren't reached from any user action in the static call graph: the ghost town. Some run dynamically; some may be unused.`);
const parks=Object.values(D.layers?.parks||{}).reduce((a,v)=>a+v,0);
if(parks)facts.push(`<b>${fmt(parks)} test files</b> (the parks): about one for every ${Math.max(1,Math.round((sampled||n)/parks))} source files.`);
const card=()=>facts.length?`<div class="census"><h4>City stats</h4><ul>${facts.map(f=>`<li>${f}</li>`).join("")}</ul>${sampled?`<small>Mapped from a sample of ${fmt(n)} source files of ${fmt(sampled)}.</small>`:""}</div>`:"";
const _showCity=showCity;showCity=function(){const r=_showCity();panel.querySelector(".sub")?.insertAdjacentHTML("afterend",card());
  panel.querySelectorAll(".census a[data-p]").forEach(a=>a.onclick=()=>showFile(a.dataset.p));return r};
// the Skyline button: the overview with these stats, seen from street level like a real skyline
const home=document.getElementById("homeBtn");home.textContent="🏙 Skyline";home.title="See the whole skyline and what it says about the code";
function skyline(){showCity();if(mode==="3d")fly(CITY.clone().setY(4),CITYD*0.9,0.07,1300)}
home.onclick=skyline;backBtn.onclick=showCity;  // both were bound to the unwrapped function
if(crumbs.textContent==="City"){panel.querySelector(".sub")?.insertAdjacentHTML("afterend",card());panel.querySelectorAll(".census a[data-p]").forEach(a=>a.onclick=()=>showFile(a.dataset.p))}  // the overview already on screen
window.cityAPI=Object.assign(window.cityAPI||{},{skyline,census:()=>facts.map(f=>f.replace(/<[^>]+>/g,""))});
}
/* /census */
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
    print(f"{out}: city stats added")


if __name__ == "__main__":
    main(*sys.argv[1:3])
