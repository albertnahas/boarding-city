"""Static call graph + user entry points (no AI). Edge kinds: static (shown direct) and listener, registry, state,
callback (shown indirect). Body extent is method-aware: from the declaration to the next declaration at the same or
lower indentation. Hidden patterns resolved statically:
  listener  JSX on*={handler} and addEventListener(..., handler)  -> the handler (also an entry point)
  registry  fetch-style calls to "/api/..." -> the matching Next.js pages/api route handler
  state     a React Query mutation that invalidates/sets queries -> the query hooks in the same folder
  callback  <Child onSave={save}/> + the child calling onSave(...); const { mutate: x } = useYMutation() + x(...)
Entry points: JSX and DOM event handlers, registered actions (`register({...})`) and Next.js page components.
"""
import collections, os, re

CALL = re.compile(r"(?:\bthis\.|\.|\b)(\w+)\s*(?:\(|<[\w\s,|]*>\()|(?:this\.)(\w+)\b")
REG = re.compile(r"^(?:export\s+)?const\s+(\w+)\s*=\s*register\(")
JSXH = re.compile(r"\b(on[A-Z]\w*)=\{\s*(?:this\.)?(\w+)\s*\}")
JSXI = re.compile(r"\b(on[A-Z]\w*)=\{\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>")
AEL = re.compile(r"addEventListener\(\s*(?:EVENT\.)?[\"'`]?(\w+)[\"'`]?\s*,\s*(?:this\.)?(\w+)")
URL = re.compile(r"\b(?:get|post|put|patch|del|fetch|handleFetch\w*|fetchHandler)\(\s*[`'\"](?:\$\{\w+\})?/api/([^`'\"?]*)")
SETTER = re.compile(r"\binvalidateQueries\(|\bsetQueryData\(|\bresetQueries\(|\brefetchQueries\(")
ALIAS = re.compile(r"\{([^}]*\bmutate(?:Async)?\b[^}]*)\}\s*=\s*(use\w+Mutation)\(")
PAGE = re.compile(r"(?:^|/)pages/(?!api/)(.+?)(?:/index)?\.(?:t|j)sx$|(?:^|/)app/(.*?)/?page\.(?:t|j)sx$")
ind = lambda s: len(s) - len(s.lstrip())


def build(src, S):
    by = {f["path"]: f for f in S}
    nodes, files = {}, {}
    for f in S:
        L = open(os.path.join(src, f["path"]), encoding="utf-8", errors="replace").read().split("\n")
        files[f["path"]] = L
        ns = [{"name": x["name"], "line": x["line"]} for x in f["functions"]]
        have = {x["name"] for x in ns}
        for i, l in enumerate(L):
            m = REG.match(l)
            if m and m.group(1) not in have:
                ns.append({"name": m.group(1), "line": i + 1, "action": True})
        ns.sort(key=lambda x: x["line"])
        for k, n in enumerate(ns):
            lvl = ind(L[n["line"] - 1])
            end = next((m["line"] - 1 for m in ns[k + 1:] if ind(L[m["line"] - 1]) <= lvl), len(L))
            nid = f"{f['path']}::{n['name']}"
            if nid not in nodes:
                nodes[nid] = {"path": f["path"], "name": n["name"], "line": n["line"], "body": "\n".join(L[n["line"]:end]),
                              "action": n.get("action", False), "method": ind(L[n["line"] - 1]) == 2}
    names_in = {f["path"]: {} for f in S}
    for nid, n in nodes.items():
        names_in[n["path"]][n["name"]] = nid
    known_cache = {}

    def known(p):
        if p in known_cache:
            return known_cache[p]
        k, seen = {}, set()

        def ex(q):
            if q in seen or q not in by:
                return
            seen.add(q)
            for nm, i in names_in[q].items():
                k.setdefault(nm, i)
            if re.search(r"/index\.\w+$", q):
                for r in by[q]["imports"]:
                    ex(r)
        for q in by[p]["imports"]:
            ex(q)
        k.update(names_in[p])
        known_cache[p] = k
        return k

    edges = {nid: {} for nid in nodes}
    entries = collections.defaultdict(set)

    def add(a, b, kind):
        if a != b and (b not in edges[a] or edges[a][b] != "static"):
            edges[a][b] = kind

    def jsx_spans(body):
        out = []
        for m in re.finditer(r"\bon[A-Z]\w*=\{", body):
            d = 0
            for j in range(m.end() - 1, min(len(body), m.end() + 4000)):
                d += (body[j] == "{") - (body[j] == "}")
                if d == 0:
                    out.append((m.end(), j))
                    break
        return out

    routes = []  # Next.js pages/api: path segments ("[id]" matches any) -> handler
    for p in by:
        m = re.search(r"pages/api/(.+?)(?:/index)?\.(?:t|j)sx?$", p)
        h = m and (names_in[p].get("handler") or next(iter(names_in[p].values()), None))
        if h:
            routes.append(([None if x.startswith("[") else x for x in m.group(1).split("/")], h))

    def route_for(url):
        segs = [None if re.fullmatch(r"\{\w+\}|\$\{[^}]+\}", x) else x for x in url.strip("/").split("/")]
        for pat, h in routes:
            if len(pat) == len(segs) and all(a is None or b is None or a == b for a, b in zip(pat, segs)):
                return h

    qhooks = collections.defaultdict(list)  # folder -> React Query hooks defined there
    for i, n in nodes.items():
        if re.search(r"[-.]query\.(?:t|j)sx?$|Query\.(?:t|j)sx?$", n["path"]) and n["name"].startswith("use"):
            qhooks[os.path.dirname(n["path"])].append(i)

    for p in by:
        K = known(p)
        for nm, nid in names_in[p].items():
            n = nodes[nid]
            body = n["body"]
            spans = jsx_spans(body)
            for m in CALL.finditer(body):
                a, b = m.group(1), m.group(2)
                t = a or b
                if t not in K:
                    continue
                tgt = K[t]
                # obj.x( only binds to class methods, so ctx.restore() doesn't resolve to an unrelated restore()
                if a and body[m.start():m.start() + 5] != "this." and body[m.start()] == "." and not nodes[tgt]["method"]:
                    continue
                add(nid, tgt, "listener" if (b or any(x <= m.start() < y for x, y in spans)) else "static")
            for t in set(re.findall(r"\b(action[A-Z]\w*)\b", body)):
                if t in K:
                    add(nid, K[t], "static")
            for ev, h in JSXH.findall(body):
                if h in K:
                    add(nid, K[h], "listener")
                    entries[K[h]].add(f"{ev} handler, set in {nm}")
            for ev in JSXI.findall(body):
                entries[nid].add(f"inline {ev} in {nm}")
            for ev, h in AEL.findall(body):
                if h in K:
                    add(nid, K[h], "listener")
                    entries[K[h]].add(f"{ev} listener, added in {nm}")
            if n["action"]:
                lab = re.search(r"name:\s*[\"'](\w+)[\"']", body)
                entries[nid].add(f"registered action {lab.group(1) if lab else nm}{' (keyboard shortcut)' if 'keyTest' in body else ''}")
            if SETTER.search(body):
                for q in qhooks[os.path.dirname(p)]:
                    add(nid, q, "state")
            for u in URL.findall(body):
                if h := route_for(u):
                    add(nid, h, "registry")
            pg = PAGE.search(p)
            if pg and nm[:1].isupper() and re.match(r"(export\s+default\s+)?(const|function)", files[p][n["line"] - 1].lstrip()):
                entries[nid].add(f"page /{pg.group(1) or pg.group(2) or ''}")
    props = collections.defaultdict(list)
    for p in by:
        K, t = known(p), "\n".join(files[p])
        for m in re.finditer(r"<([A-Z]\w*)\b", t):
            end = t.find(">", m.end())
            seg = t[m.end():end if end > 0 else m.end() + 400][:1500]
            c = K.get(m.group(1))
            if c:
                for prop, fn in re.findall(r"\b(\w+)=\{\s*(?:this\.)?(\w+)\s*\}", seg):
                    if fn in K and prop != "key":
                        props[(nodes[c]["path"], prop)].append(K[fn])
    for (cf, prop), targets in props.items():
        for nm, nid in names_in.get(cf, {}).items():
            if re.search(r"(?<![\w.])(?:props\.)?" + re.escape(prop) + r"\??\.?\(", nodes[nid]["body"]):
                for tg in targets:
                    add(nid, tg, "callback")
    for p in by:
        K, t = known(p), "\n".join(files[p])
        for body, hook in ALIAS.findall(t):
            if hook in K:
                for al in re.findall(r"\bmutate(?:Async)?\s*(?::\s*(\w+))?", body):
                    for nm, nid in names_in[p].items():
                        if re.search(r"(?<![\w.])" + re.escape(al or "mutate") + r"\(", nodes[nid]["body"]):
                            add(nid, K[hook], "callback")
    return {"nodes": {i: {"path": n["path"], "name": n["name"], "line": n["line"], "action": n["action"]} for i, n in nodes.items()},
            "edges": edges, "entries": {i: sorted(h) for i, h in entries.items()}}
