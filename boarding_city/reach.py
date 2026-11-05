"""User actions (entry points named by the fast model) and reach: for each function on the map, which actions reach it,
by a reverse walk of the call graph. Buckets: part (<10% of actions: list them), used (10-40%: group by district),
infra (>40%, or wrappers like providers and loggers: "runs on almost every action")."""
import collections, re
from . import config
from .llm import ask

WRAP = re.compile(r"ErrorBoundary|Provider|Context|^log|[Ll]ogger|^debug", re.I)


def name_actions(work, repo, G, flows):
    ids = sorted(G["entries"])
    titles = [F["title"] for F in flows]
    schema = {"type": "object", "additionalProperties": False, "required": ["entries"], "properties": {"entries": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["i", "actions"], "properties": {"i": {"type": "integer"}, "actions": {"type": "array", "items": {"type": "string"}}}}}}}
    acts, B = {}, 300
    for b0 in range(0, len(ids), B):
        chunk = ids[b0:b0 + B]
        rows = "\n".join(f"{k}. {i} — {'; '.join(G['entries'][i])[:120]}" for k, i in enumerate(chunk))
        out = ask(work, config.model("fast"), f"""These are user-triggered entry points detected in the {repo} source (file::function — how it is triggered: JSX event handler, DOM listener, registered action or page route).
For EACH entry (by number) list the 1-2 plain user actions it triggers, as short imperative names (max 4 words, e.g. "Create a table", "Undo").
Reuse EXACTLY an existing name when the action is the same, so duplicates merge. Names already used: {sorted(acts)[:400]}. When an entry triggers one of these walkthroughs, use its title verbatim: {titles}.
Page routes are "Open <page>" actions. Use an empty list for entries that are not user actions (layout bookkeeping, focus, resize, analytics).

{rows}""", schema, f"name entries {b0}")
        for e in out["entries"]:
            if 0 <= e["i"] < len(chunk):
                for a in e["actions"]:
                    acts.setdefault(a.strip(), set()).add(chunk[e["i"]])
    A = [{"name": n, "entries": sorted(v), "flow": titles.index(n) if n in titles else None} for n, v in sorted(acts.items())]
    # a verified walkthrough's first step is a user event by definition, even when the detector missed it
    for fi, F in enumerate(flows):
        a = next((a for a in A if a["flow"] == fi), None)
        if a is None:
            a = {"name": F["title"], "entries": [], "flow": fi}
            A.append(a)
        ids_ = {s["path"] + "::" + s["function"] for s in F["steps"]}
        a["entries"] = sorted(set(a["entries"]) | (ids_ & set(G["entries"])) | {F["steps"][0]["path"] + "::" + F["steps"][0]["function"]})
    return A


def compute(G, A, flows, dist, building_paths):
    N, M = G["nodes"], max(len(A), 1)
    rev = collections.defaultdict(list)
    for a, outs in G["edges"].items():
        for b, k in outs.items():
            if k != "listener":  # a listener registration is not a call; the handler is an entry point itself
                rev[b].append(a)
    ent2act = collections.defaultdict(list)
    for ai, a in enumerate(A):
        for e in a["entries"]:
            ent2act[e].append(ai)
    traced = {(fi, s["path"] + "::" + s["function"]) for fi, F in enumerate(flows) for s in F["steps"]}

    def reaching(f):
        d, q, best = {f: 0}, collections.deque([f]), {}
        while q:
            x = q.popleft()
            for y in rev[x]:
                if y not in d:
                    d[y] = d[x] + 1
                    q.append(y)
        for e, dist_ in d.items():
            for ai in ent2act.get(e, ()):
                if ai not in best or dist_ < best[ai][0]:
                    best[ai] = (dist_, e)
        return best

    def label(ai, f):
        fi = A[ai]["flow"]
        return "traced" if fi is not None and (fi, f) in traced else "likely"

    out = {}
    for f, n in N.items():
        if n["path"] not in building_paths:
            continue
        best = reaching(f)
        k, order = len(best), sorted(best, key=lambda ai: (best[ai][0], A[ai]["name"]))
        if WRAP.search(n["name"]) or k / M > 0.40:
            callers = collections.defaultdict(list)
            for c in rev[f]:
                callers[dist(N[c]["path"])].append(N[c]["name"])
            out[f] = {"b": "infra", "n": k, "wrap": bool(WRAP.search(n["name"])), "eg": [order[0], best[order[0]][0]] if order else None,
                      "callers": {str(d): sorted(set(v))[:4] + ([f"+{len(set(v)) - 4}"] if len(set(v)) > 4 else [])
                                  for d, v in sorted(callers.items(), key=lambda x: -len(x[1]))}}
        elif k / M >= 0.10:
            g = collections.defaultdict(list)
            for ai in order:
                g[dist(N[best[ai][1]]["path"])].append([ai, best[ai][0], label(ai, f)])
            out[f] = {"b": "used", "n": k, "mods": {str(d): v for d, v in g.items()}}
        else:
            out[f] = {"b": "part", "n": k, "acts": [[ai, best[ai][0], label(ai, f)] for ai in order]}
    return out
