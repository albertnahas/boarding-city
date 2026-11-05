"""Choose the buildings and assemble city.json (the data the template renders).

Small repos (<=600 files): every file of 300+ lines, or on a walkthrough, is a building; smaller files are grouped
into one block per folder. Large repos: per district, the walkthrough files and the 6 biggest files are buildings;
the rest becomes the 10 biggest folder blocks plus one "other folders" block, so a monorepo stays around 200 buildings.
"""
import os
from collections import defaultdict

SMALL_REPO, SMALL_FILE, TOP, BLOCKS = 600, 300, 6, 10
PALETTE = ["#2dd4bf", "#f59e0b", "#8b5cf6", "#f43f5e", "#60a5fa", "#84cc16", "#fb923c", "#10b981", "#e879f9", "#94a3b8"]


def select(S, flows, dist):
    """-> (file entries without summaries, home: member file -> its block building)."""
    onflow = {s["path"] for F in flows for s in F["steps"]}
    big = len(S) > SMALL_REPO
    byd = defaultdict(list)
    for f in S:
        byd[dist(f["path"])].append(f)
    files, home = [], {}
    for d, g in byd.items():
        if big:
            keep = {f["path"] for f in sorted(g, key=lambda f: -f["lines"])[:TOP]} | {f["path"] for f in g if f["path"] in onflow}
        else:
            keep = {f["path"] for f in g if f["lines"] >= SMALL_FILE or f["path"] in onflow}
        files += [{"src": f, "district": d} for f in g if f["path"] in keep]
        groups = defaultdict(list)
        for f in g:
            if f["path"] not in keep:
                groups[os.path.dirname(f["path"]) or "."].append(f)
        ranked = sorted(groups.items(), key=lambda kv: -sum(x["lines"] for x in kv[1]))
        if big and len(ranked) > BLOCKS:
            ranked = ranked[:BLOCKS] + [(f"{dist.names[d]} · other folders", [x for _, v in ranked[BLOCKS:] for x in v])]
        for folder, members in ranked:
            if len(members) == 1:
                files.append({"src": members[0], "district": d, "nosnip": True})
                continue
            key = folder + "/ (block)"
            files.append({"block": key, "members": members, "district": d})
            home.update({m["path"]: key for m in members})
    return files, home


def assemble(src, repo, key, sha, dist, desc, sel, home, flows, actions, reach, LY, tabloid, cost, nfiles):
    summ = {f["path"]: f["summary"] for f in desc["files"]}
    names = {d["index"]: d for d in desc["districts"]}
    out = []
    for e in sel:
        if "block" in e:
            g = e["members"]
            nm = sorted(os.path.basename(x["path"]) for x in g)
            out.append({"path": e["block"], "lines": sum(x["lines"] for x in g), "cluster": True, "district": e["district"],
                        "members": [{"path": x["path"], "lines": x["lines"], "summary": summ.get(x["path"], x["doc"])} for x in sorted(g, key=lambda x: -x["lines"])[:40]],
                        "functions": [], "imports": [], "summary": f"{len(g)} files, {sum(x['lines'] for x in g):,} lines: " + ", ".join(nm[:6]) + (" …" if len(nm) > 6 else "")})
            continue
        f = e["src"]
        L = [] if e.get("nosnip") else open(os.path.join(src, f["path"]), encoding="utf-8", errors="replace").read().split("\n")
        out.append({"path": f["path"], "lines": f["lines"], "district": e["district"], "imports": f["imports"], "summary": summ.get(f["path"], f["doc"]),
                    "functions": [{"name": x["name"], "line": x["line"], "snippet": "\n".join(L[x["line"] - 1:x["line"] + 5]) if L else ""} for x in f["functions"]]})
    keep = {f["path"] for f in out}
    for f in out:
        f["imports"] = [q for q in f["imports"] if q in keep]
    counts = dist.counts()
    districts = [{"name": names.get(i, {}).get("name") or dist.names[i], "summary": names.get(i, {}).get("summary", ""), "total": counts.get(i, 0),
                  "files": [f["path"] for f in sorted(out, key=lambda f: -f["lines"]) if f["district"] == i]} for i in range(len(dist.keys))]
    for f in out:
        f.pop("district")
    shown = {f["path"] + "::" + x["name"] for f in out if not f.get("cluster") for x in f["functions"]}
    LY = {**LY, "functions": {k: v for k, v in LY["functions"].items() if k in shown}}
    data = {"repo": repo.split("/")[-1], "app": desc["app"], "colors": PALETTE[:len(districts)], "districts": districts, "files": out,
            "flows": flows, "actions": [{"name": a["name"], "flow": a["flow"], "mod": dist(a["entries"][0].split("::")[0]) if a["entries"] else 0} for a in actions],
            "reach": {k: v for k, v in reach.items() if k in shown}, "layers": LY, "home": home, "tabloid": tabloid,
            "meta": {"key": key, "repo": repo, "sha": sha, "files": nfiles, "flows": len(flows), "cost": round(cost, 2)}}
    if nfiles > SMALL_REPO:
        data["blockHeightCap"] = 4000
    return data
