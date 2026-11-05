"""Add a name search (districts, files, functions) to a built code-city page.

usage: python3 inject_search.py <built demo.html> <out.html>

Post-build step, run after inject_nav. It appends to the city's own module script, so picking a
result calls the city's showDistrict/showFile/showFn directly (and the fog of war reveals what it opens).
"""
import sys

MARK, END = "/* search */", "/* /search */"
CSS_MARK, CSS_END = "/* search-css */", "/* /search-css */"

CSS = """
#bar:focus-within{z-index:12}
#find{position:relative;display:flex}
#findIn{width:230px;height:34px;box-sizing:border-box;padding:0 30px 0 32px;border-radius:8px;border:1px solid #ffffff26;background:#121726e6 no-repeat 10px 50%/14px url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Ccircle cx='6.5' cy='6.5' r='5' fill='none' stroke='%238b93a7' stroke-width='1.8'/%3E%3Cpath d='M10.5 10.5 15 15' stroke='%238b93a7' stroke-width='1.8' stroke-linecap='round'/%3E%3C/svg%3E");color:var(--ink);font:13px system-ui,sans-serif;backdrop-filter:blur(6px)}
#findIn::placeholder{color:#8b93a7}
#findIn:focus{outline:2px solid var(--acc);outline-offset:1px}
#find .k{position:absolute;right:8px;top:50%;transform:translateY(-50%);font:11px ui-monospace,Menlo,monospace;color:#8b93a7;border:1px solid #ffffff26;border-radius:4px;padding:0 5px;pointer-events:none}
#findIn:focus+.k,#findIn:not(:placeholder-shown)+.k{display:none}
#findList{position:absolute;top:calc(100% + 6px);left:0;width:min(420px,calc(100vw - 24px));max-height:min(60vh,440px);overflow:auto;margin:0;padding:6px;list-style:none;background:#121726f7;border:1px solid #ffffff26;border-radius:10px;box-shadow:0 12px 40px #000a;z-index:20}
#findList[hidden]{display:none}
#findList li{display:grid;grid-template-columns:18px 1fr;gap:0 8px;align-items:baseline;padding:7px 8px;border-radius:7px;cursor:pointer}
#findList li[aria-selected=true]{background:#ffffff14}
#findList .ic{font:600 12px ui-monospace,Menlo,monospace;text-align:center}
#findList .nm{font:600 13px ui-monospace,Menlo,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#findList .nm mark{background:none;color:var(--acc)}
#findList .sb{grid-column:2;color:#8b93a7;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#findList .none{display:block;color:#8b93a7;cursor:default}
#panel .list li.found{background:#5eead41f;box-shadow:inset 2px 0 var(--acc)}
@media (max-width:700px){#findIn{width:min(230px,calc(100vw - 24px))}#find{position:static}#findList{left:0;right:0;width:auto}}
"""

JS = r"""
/* search */
{
const box=document.createElement("div");box.id="find";box.setAttribute("role","search");
box.innerHTML=`<input id="findIn" type="search" placeholder="Find a file or function" autocomplete="off" spellcheck="false" role="combobox" aria-expanded="false" aria-controls="findList" aria-autocomplete="list" aria-label="Find a district, file or function"><span class="k" aria-hidden="true">/</span><ul id="findList" role="listbox" hidden></ul>`;
document.getElementById("bar").appendChild(box);
const input=box.querySelector("input"),list=box.querySelector("ul"),hex=i=>"#"+COLORS[i%COLORS.length].toString(16).padStart(6,"0");
// the index: every district, file (small files resolve to their block) and function, searchable by name and by path
const ITEMS=[...D.districts.map((d,i)=>({kind:"district",name:d.name,sub:`District · ${d.files.length} buildings`,i,go:()=>showDistrict(i)})),
  ...D.files.flatMap(f=>f.cluster?f.members.map(m=>({kind:"file",name:short(m.path),path:m.path,sub:`${m.path} · in ${short(f.path)}`,i:fileDistrict[f.path],go:()=>{showFile(f.path);const b=short(m.path),li=[...panel.querySelectorAll(".list li")].find(li=>li.querySelector("b")?.textContent===b);if(li){li.classList.add("found");li.scrollIntoView({block:"nearest"})}}}))
    :[{kind:"file",name:short(f.path),path:f.path,sub:`${f.path} · ${f.lines} lines`,i:fileDistrict[f.path],go:()=>showFile(f.path)},
      ...f.functions.map(fn=>({kind:"fn",name:fn.name,path:f.path,sub:`${short(f.path)}:${fn.line}`,i:fileDistrict[f.path],go:()=>showFn(f.path,fn.name)}))])];
ITEMS.forEach(t=>{t.n=t.name.toLowerCase();t.s=t.kind==="file"?t.n.replace(/\.[^.]+$/,""):t.n;t.p=(t.path||"").toLowerCase()});
const RANK={district:0,file:1,fn:2};
// exact name, then prefix, then the start of a word or camelCase hump, then anywhere in the name, then anywhere in the path
function score(t,q){const n=t.n;if(n===q||t.s===q)return 100;if(n.startsWith(q))return 80-n.length/100;
  const at=n.indexOf(q);if(at>0){const c=t.name[at],prev=t.name[at-1];return(/[^a-z0-9]/i.test(prev)||c!==c.toLowerCase()?60:40)-at/100}
  return t.p.includes(q)?20:0}
let hits=[],sel=0;
function run(){const q=input.value.trim().toLowerCase();
  hits=q?ITEMS.map(t=>[score(t,q),t]).filter(([s])=>s>0).sort((a,b)=>b[0]-a[0]||RANK[a[1].kind]-RANK[b[1].kind]||a[1].name.length-b[1].name.length).slice(0,40).map(([,t])=>t):[];
  sel=0;render(q)}
function mark(name,q){const at=name.toLowerCase().indexOf(q);return at<0?esc(name):esc(name.slice(0,at))+"<mark>"+esc(name.slice(at,at+q.length))+"</mark>"+esc(name.slice(at+q.length))}
function render(q){const show=!!q;list.hidden=!show;input.setAttribute("aria-expanded",String(show));if(!show)return;
  list.innerHTML=hits.length?hits.map((t,k)=>`<li id="find${k}" role="option" aria-selected="${k===sel}" data-k="${k}"><span class="ic" style="color:${hex(t.i)}">${t.kind==="district"?"■":t.kind==="file"?"▮":"ƒ"}</span><span class="nm">${mark(t.name,q)}${t.kind==="fn"?"()":""}</span><span class="sb">${esc(t.sub)}</span></li>`).join("")
    :`<li class="none">Nothing named “${esc(q)}” in this city.</li>`;
  input.setAttribute("aria-activedescendant",hits.length?"find"+sel:"")}
function move(d){if(!hits.length)return;sel=(sel+d+hits.length)%hits.length;
  list.querySelectorAll("li").forEach((li,k)=>li.setAttribute("aria-selected",String(k===sel)));
  input.setAttribute("aria-activedescendant","find"+sel);list.children[sel].scrollIntoView({block:"nearest"})}
function pick(k){const t=hits[k];if(!t)return;input.value="";render("");input.blur();t.go()}
input.addEventListener("input",run);
input.addEventListener("keydown",e=>{
  if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();move(e.key==="ArrowDown"?1:-1)}
  else if(e.key==="Enter"){e.preventDefault();pick(sel)}
  else if(e.key==="Escape"){e.preventDefault();e.stopPropagation();if(input.value){input.value="";render("")}else input.blur()}});
list.addEventListener("pointerdown",e=>{const li=e.target.closest("li[data-k]");if(li){e.preventDefault();pick(+li.dataset.k)}});
input.addEventListener("blur",()=>setTimeout(()=>{if(document.activeElement!==input)render("")},0));
input.addEventListener("focus",()=>{if(input.value.trim())run()});
// "/" focuses the search, from the city and from the app shell around it
function focusFind(){input.focus();input.select();return true}
addEventListener("keydown",e=>{const t=e.target;if(e.key!=="/"||e.ctrlKey||e.metaKey||e.altKey||(t&&(t.isContentEditable||/^(input|textarea|select)$/i.test(t.tagName))))return;e.preventDefault();focusFind()});
const navKey=window.cityAPI.key;window.cityAPI.key=k=>k==="/"?focusFind():navKey(k);
window.cityAPI.find=q=>{input.value=q;run();return hits.map(t=>({kind:t.kind,name:t.name,path:t.path}))};
}
/* /search */
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
    print(f"{out}: search added")


if __name__ == "__main__":
    main(*sys.argv[1:3])
