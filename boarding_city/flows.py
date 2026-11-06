"""AI passes that need judgement, kept small and cheap:
  propose (fast model): recognisable user actions + ~30 candidate files each, from paths and function names only
  (a library with no UI entry points gets API calls instead: "Call is.string(value)", from the exported function)
  narrow  (fast model): the 8-12 files each action actually runs through
  trace   (trace model): ordered steps over those files only; every step must be a function id from the listing
then verify (no AI): drop steps that aren't real functions in that file, label each hop direct or indirect from the code.
"""
import contextvars, json, os, re
from concurrent.futures import ThreadPoolExecutor
from . import config
from .llm import ask


def _lines(src, p, cache={}):
    k = (str(src), p)
    if k not in cache:
        cache[k] = open(os.path.join(src, p), encoding="utf-8", errors="replace").read().split("\n")
    return cache[k]


def propose(work, repo, S, n, api=None):
    """-> up to n walkthroughs. api (exported function ids, for a library with no UI entry points) makes them API
    calls a developer makes ("Call is.string(value)"), traced from the exported function to its result."""
    if api:
        return _propose_api(work, repo, S, n, api)
    small = len(S) <= 900
    rows = "\n".join((f"{f['path']} ({f['lines']}L): {', '.join(x['name'] for x in f['functions'][:20])}"[:260] if small else f["path"])
                     for f in S if f["functions"])
    schema = {"type": "object", "additionalProperties": False, "required": ["flows"], "properties": {"flows": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["title", "desc", "candidates"], "properties": {
            "title": {"type": "string"}, "desc": {"type": "string"}, "candidates": {"type": "array", "items": {"type": "string"}}}}}}}
    out = ask(work, config.model("fast"), f"""You map the {repo} codebase for a new developer's onboarding. Below is every source file{' with its line count and first function names' if small else ''}.
Propose {n} user-facing actions a new developer would want explained end to end: everyday things a user (or an API caller, for a library) does, each traceable in this code.
For each: title (max 5 words, imperative, e.g. "Add a text label"), desc (one plain sentence, max 16 words: what the user does and sees), candidates: the ~30 file paths most likely involved, from the first event handler or public entry function to the visible result. Use paths exactly as listed.

{rows}""", schema, "propose")
    return _keep(S, out["flows"], n)


def _keep(S, proposed, n):
    """Candidates must be real paths; a flow needs 3 of them (or every file, in a repo with fewer)."""
    ok = {f["path"] for f in S}
    need = min(3, sum(1 for f in S if f["functions"]))
    for f in proposed:
        f["candidates"] = [p for p in dict.fromkeys(f["candidates"]) if p in ok]
    return [f for f in proposed if f["candidates"] and len(f["candidates"]) >= need][:n]


def _propose_api(work, repo, S, n, api):
    by = {f["path"]: f for f in S}
    calls = {f"{f['path']}::{x['name']}": len(x.get("calls", [])) for f in S for x in f["functions"]}
    rows = "\n".join(f"{i} (calls {calls.get(i, 0)})" for i in sorted(api, key=lambda i: -calls.get(i, 0))[:400])
    schema = {"type": "object", "additionalProperties": False, "required": ["flows"], "properties": {"flows": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["title", "desc", "entry"], "properties": {
            "title": {"type": "string"}, "desc": {"type": "string"}, "entry": {"type": "string", "enum": sorted(api)}}}}}}
    out = ask(work, config.model("fast"), f"""{repo} is a library: it has no UI, developers call its exported functions. Below are its exported functions (file::name), with how many other functions each one calls.
Propose {n} different calls a new developer would want explained end to end: the most typical uses of the public API, preferring functions that call others (a longer path through the code).
For each: title (max 5 words, the call, e.g. "Call is.string(value)" or "Assert a value"), desc (one plain sentence, max 16 words: what the call does and returns), entry: the exported function it starts at.

{rows}""", schema, "propose api")
    flows = []
    for f in out["flows"]:
        p = f["entry"].split("::")[0]
        others = [q for q in by if q != p and by[q]["functions"]]
        flows.append({"title": f["title"], "desc": f["desc"], "api": True, "candidates": [p] + others[:29]})
    return _keep(S, flows, n)


def _narrow(work, src, by, repo, fl):
    def head(p):
        return " | ".join(l.strip() for l in _lines(src, p)[:40] if l.strip().startswith(("export", "function", "const", "class")))[:300]
    rows = "\n".join(f"{p} ({by[p]['lines']}L): fns {', '.join(x['name'] for x in by[p]['functions'][:30])[:400]} || {head(p)}" for p in fl["candidates"])
    sch = {"type": "object", "additionalProperties": False, "required": ["files"], "properties": {"files": {"type": "array", "items": {"type": "string", "enum": fl["candidates"]}}}}
    out = ask(work, config.model("fast"), f"""{repo}. User action: "{fl['title']}: {fl['desc']}". From these candidate files, pick the 8-12 that the action actually runs through (or all of them, if there are fewer), in execution order ({'the exported function first, the result last' if fl.get('api') else 'UI or entry handler first, visible result last'}).

{rows}""", sch, f"narrow {fl['title']}")
    return {**fl, "files": out["files"]}


def _trace(work, src, by, repo, fl):
    rel = set(fl["files"])
    ids, parts = [], []
    for p in fl["files"]:
        L, rows = _lines(src, p), []
        for fn in by[p]["functions"]:
            ids.append(f"{p}::{fn['name']}")
            calls = [c.split("::")[1] for c in fn.get("calls", []) if c.split("::")[0] in rel]
            rows.append(f"  L{fn['line']} {fn['name']}: {L[fn['line'] - 1].strip()[:90]}{'  → ' + ', '.join(calls[:12]) if calls else ''}")
        parts.append(f"## {p} ({by[p]['lines']} lines)\n" + "\n".join(rows))
    api = fl.get("api")
    if not ids:
        return {"title": fl["title"], "desc": fl["desc"], "api": api, "steps": []}
    sch = {"type": "object", "additionalProperties": False, "required": ["steps"], "properties": {"steps": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["id", "narration"], "properties": {"id": {"type": "string", "enum": ids}, "narration": {"type": "string"}}}}}}
    out = ask(work, config.model("trace"), f"""Trace this {'call to the library' if api else 'user action'} through the {repo} source, end to end, for a new developer: "{fl['title']}: {fl['desc']}".
Below: the relevant files with every function (line, declaration, and the functions it statically calls among these files, after →).
Return {'2-8 ordered steps from the exported function the developer calls to the value it returns or the effect it has' if api else '6-10 ordered steps from the first event handler or entry function to the visible result'}. Each step is one function id "path::name" from the listing; narration is one plain-English sentence (max 22 words). Prefer chains where each step calls the next; if a hop goes through an event, callback or state update, say so. Only use functions from the listing.

""" + "\n\n".join(parts), sch, f"trace {fl['title']}", effort=config.model("effort"))
    return {"title": fl["title"], "desc": fl["desc"], "api": api,
            "steps": [{"path": s["id"].split("::")[0], "function": s["id"].split("::")[1], "narration": s["narration"]} for s in out["steps"]]}


def trace_all(work, src, S, repo, proposed):
    by = {f["path"]: f for f in S}
    ctx = contextvars.copy_context()  # worker threads keep this build's model settings
    with ThreadPoolExecutor(6) as ex:
        narrowed = list(ex.map(lambda f: ctx.copy().run(_narrow, work, src, by, repo, f), proposed))
    with ThreadPoolExecutor(6) as ex:
        return list(ex.map(lambda f: ctx.copy().run(_trace, work, src, by, repo, f), narrowed))


def verify(src, S, raw):
    """Keep a step only if the function is defined in that file. A hop is "direct call" only if the previous function's
    body (method-aware: up to the next declaration at the same or lower indentation) references the next one."""
    by = {f["path"]: f for f in S}
    ind = lambda s: len(s) - len(s.lstrip())

    def find(p, name):
        fns = [x for x in by.get(p, {"functions": []})["functions"] if x["name"] == name]
        if not fns:
            return None
        L, fn = _lines(src, p), fns[0]
        d = fn["line"] - 1
        if not re.search(r"\b" + re.escape(name) + r"\b", L[d]):
            return None
        lvl = ind(L[d])
        nxt = [x["line"] - 1 for x in by[p]["functions"] if x["line"] - 1 > d and ind(L[x["line"] - 1]) <= lvl]
        return {"line": fn["line"], "body": "\n".join(L[d + 1:(min(nxt) if nxt else len(L))]), "calls": fn.get("calls", [])}

    kept, tot, ok = [], 0, 0
    for f in raw:
        steps = []
        for s in f["steps"]:
            tot += 1
            info = find(s["path"], s["function"])
            if not info or (steps and (steps[-1]["path"], steps[-1]["function"]) == (s["path"], s["function"])):
                continue
            if any((x["path"], x["function"]) == (s["path"], s["function"]) for x in steps):
                continue  # a trace that loops back to an earlier step
            ok += 1
            steps.append({**s, "line": info["line"], "_i": info})
        for k, s in enumerate(steps):
            if k == 0:
                s["link"] = "first step"
                continue
            p = steps[k - 1]["_i"]
            direct = f"{s['path']}::{s['function']}" in p["calls"] or re.search(r"\b" + re.escape(s["function"]) + r"\b", p["body"])
            s["link"] = "direct call" if direct else "indirect (callback, event or state)"
        for s in steps:
            s.pop("_i")
        if len(steps) >= (2 if f.get("api") else 4):  # library calls are short by nature: the call and what it uses
            kept.append({"title": f["title"], "desc": f["desc"], "steps": steps, **({"api": True} if f.get("api") else {})})
    return kept, {"steps_verified": ok, "steps_total": tot, "flows_kept": len(kept), "flows_total": len(raw)}


def why_none(api, proposed, report):
    """Why a city has no walkthroughs, in plain words (None when it has some)."""
    if report["flows_kept"]:
        return None
    if not proposed:
        return ("This is a library, and none of its exported functions gave a call worth tracing." if api else
                "No user actions were found to trace: no event handlers, listeners, routes or registered actions, and no exported API.")
    return (f"{report['flows_total']} walkthroughs were traced, but none kept enough steps that match real functions in the source "
            f"({report['steps_verified']} of {report['steps_total']} steps checked out), so none is shown rather than a wrong one.")


def describe(work, repo, S, dist, targets):
    """Fast model: one sentence for the repo, a name + sentence per district, and a one-liner per building file."""
    groups = {i: [] for i in range(len(dist.keys))}
    for f in S:
        groups[dist(f["path"])].append(f)
    ctx = "\n\n".join(f"# District {i}: {dist.keys[i]} ({len(g)} files)\n" + "\n".join(
        f"{f['path']} ({f['lines']}L): {', '.join(x['name'] for x in f['functions'][:10])}"[:200] for f in sorted(g, key=lambda f: -f["lines"])[:40])
        for i, g in groups.items())
    sch = {"type": "object", "additionalProperties": False, "required": ["app", "districts", "files"], "properties": {"app": {"type": "string"},
           "districts": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["index", "name", "summary"],
                                                    "properties": {"index": {"type": "integer"}, "name": {"type": "string"}, "summary": {"type": "string"}}}},
           "files": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["path", "summary"],
                                                "properties": {"path": {"type": "string", "enum": targets}, "summary": {"type": "string"}}}}}}
    return ask(work, config.model("fast"), f"""You map the {repo} codebase for a new developer. Return:
app: one plain sentence on what this code is;
districts: for each district index 0-{len(dist.keys) - 1}, a short name (max 3 words, e.g. "Editor engine", "UI components") and one plain sentence on what lives there;
files: a plain one-liner (max 14 words) for EACH of these {len(targets)} files: {', '.join(targets)}.

{ctx}""", sch, "describe")
