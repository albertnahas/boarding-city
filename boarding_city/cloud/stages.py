"""The build as a chain of short, resumable stages. Each stage's output is saved before the next one starts, so a
retried or resumed build reuses the saved outputs instead of paying for the work again.

  fetch      tarball of the commit -> source files (and the size check)
  structure  functions, imports, districts -> first snapshot: the skyline, in seconds
  describe   one fast-model call per district, each landing in the city as it finishes
  propose    the walkthroughs to trace (or the visitor's own requests)
  flow:<k>   one walkthrough: narrow, trace, verify -> it appears in the gallery, playable
  analysis   call graph, reach, layers, the Daily Commit, ghost town -> the finished city
"""
import contextvars, json, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from .. import config, repo as gitrepo, extract, flows as fl, graph, reach, layers, tabloid, city, site
from ..districts import Districts
from ..llm import ask, on_cost, spent
from . import jobs, store

TMP = Path(os.environ.get("BC_TMP", "/tmp/boarding-city"))
TEX = "/tex/"
ACTUAL = {}  # job -> its AI spend so far in this process, to settle the day's total when a run ends


class Ctx:
    """One job's working set inside one invocation: the state, the source on local disk, and saved stage outputs."""

    def __init__(self, st):
        self.st, self.p = st, st["params"]
        self.owner, self.name = st["repo"].split("/")
        self.work = TMP / st["id"]
        self.work.mkdir(parents=True, exist_ok=True)
        self.src = self.work / "src"
        self._base = spent(self.work)
        on_cost.set(self.spend)
        config.use_models(fast=self.p["fast_model"], trace=self.p["trace_model"], effort=self.p["effort"])

    def source(self):
        if not (self.src / ".fetched").exists():
            try:
                gitrepo.fetch(self.owner, self.name, self.st["sha"], self.src, self.p["max_files"])
            except ValueError as e:
                raise jobs.Refused(str(e))
            (self.src / ".fetched").write_text("1")
        return self.src

    def art(self, name):
        p = self.work / f"art-{name}.json"
        if not p.exists():
            got = store.get_json(f"jobs/{self.st['id']}/art/{name}.json")
            if got is None:
                return None
            p.write_text(json.dumps(got))
        return json.loads(p.read_text())

    def save_art(self, name, out):
        (self.work / f"art-{name}.json").write_text(json.dumps(out))
        store.put(f"jobs/{self.st['id']}/art/{name}.json", out)

    def cost(self):
        """This job's AI spend so far: the finished stages' costs plus the calls made in the stage running now."""
        return round(sum(self.st.get("costs", {}).values()) + self.live(), 5)

    def live(self):
        return spent(self.work) - self._base

    def spend(self):
        """After every AI call: today's total holds this job at its reservation, or its real cost once that's higher."""
        ACTUAL[self.st["id"]] = cost = self.cost()
        jobs.record_spend(self.st["id"], max(self.st.get("reserved", 0), cost))

    def log(self, msg, **f):
        self.st = jobs.log(self.st, msg, **{"cost": self.cost(), **f})


def run(st, stage):
    """Run one stage, unless an earlier run already saved its output. -> (state, next stage or None)."""
    c = Ctx(st)
    art = c.art(stage)
    if art is None:
        if stage not in ("fetch", "structure"):
            if not os.environ.get("OPENAI_API_KEY"):
                raise jobs.Refused("This server has no AI key configured yet, so it can map the skyline but not name districts or "
                                   "trace walkthroughs. The owner adds OPENAI_API_KEY in the Vercel project settings.", 503)
            jobs.check_budget()
        art = {"out": STAGES[stage.split(":")[0]](c, stage), "cost": round(c.live(), 5)}
        c.save_art(stage, art)
    # recorded from the saved output, so a run cut off right after saving it still moves on
    if stage == "propose":  # one stage per walkthrough, then the analysis
        c.st["stages"] = c.st["stages"][:c.st["stages"].index("propose") + 1] + [f"flow:{k}" for k in range(len(art["out"]))] + ["analysis"]
    if stage not in c.st.setdefault("costs", {}):
        c.st["costs"][stage] = art["cost"]
        c._base = spent(c.work)
    c.st = jobs.save(c.st)
    i = c.st["stages"].index(stage)
    return c.st, (c.st["stages"][i + 1] if i + 1 < len(c.st["stages"]) else None)


# ---- stages ----
def s_fetch(c, _):
    c.log("Downloading the source from GitHub", stage="fetch", status="running", pct=3)
    paths = gitrepo.source_files(c.source())
    if not paths:
        raise jobs.Refused("No JavaScript or TypeScript source files found. Boarding City maps JS/TS repositories.")
    if len(paths) > c.p["max_files"]:
        raise jobs.Refused(f"This repository has {len(paths):,} source files; on-demand builds take up to {c.p['max_files']:,}. "
                           "Lower the scope or build it with the command-line tool.")
    c.log(f"Got {len(paths):,} source files", pct=8)
    return {"paths": paths, "tests": gitrepo.test_files(c.src)}


def s_structure(c, _):
    c.log("Mapping files, functions and imports", stage="structure", pct=10)
    S = extract.callgraph(c.source(), extract.run(c.src, c.art("fetch")["out"]["paths"]))
    snapshot(c, S=S)
    c.log(f"Skyline up: {len(S):,} files in {len(Districts([f['path'] for f in S]).keys)} districts", pct=18)
    return S


def s_describe(c, _):
    S = c.art("structure")["out"]
    dist = Districts([f["path"] for f in S])
    sel, _ = city.select(S, [], dist)
    c.log("Naming the districts", stage="describe", pct=20)
    desc = {"app": "", "districts": [], "files": []}
    by_d = {i: [] for i in range(len(dist.keys))}
    for f in S:
        by_d[dist(f["path"])].append(f)
    targets = {i: [e["src"]["path"] for e in sel if "src" in e and not e.get("nosnip") and e["district"] == i] for i in by_d}
    with ThreadPoolExecutor(6) as ex:
        ctx = contextvars.copy_context()
        futs = {ex.submit(ctx.copy().run, _describe_district, c, i, by_d[i], targets[i], dist): i for i in by_d if by_d[i]}
        futs[ex.submit(ctx.copy().run, _describe_app, c, dist)] = "app"
        done = 0
        for fut in as_completed(futs):
            i, out = futs[fut], fut.result()
            if i == "app":
                desc["app"] = out
                continue
            desc["districts"].append({"index": i, "name": out["name"], "summary": out["summary"]})
            desc["files"] += out["files"]
            done += 1
            snapshot(c, S=S, desc=desc)
            c.log(f"District {done}/{len(futs) - 1}: {out['name']}", pct=20 + round(15 * done / (len(futs) - 1)))
    return desc


def _describe_district(c, i, files, targets, dist):
    rows = "\n".join(f"{f['path']} ({f['lines']}L): {', '.join(x['name'] for x in f['functions'][:10])}"[:200]
                     for f in sorted(files, key=lambda f: -f["lines"])[:40])
    sch = {"type": "object", "additionalProperties": False, "required": ["name", "summary", "files"], "properties": {
        "name": {"type": "string"}, "summary": {"type": "string"},
        "files": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["path", "summary"],
                  "properties": {"path": {"type": "string", "enum": targets or ["-"]}, "summary": {"type": "string"}}}}}}
    out = ask(c.work, config.model("fast"), f"""One district of the {c.st['repo']} codebase, for a new developer: the folder {dist.keys[i]} ({len(files)} files).
Return name (max 3 words, e.g. "Editor engine", "UI components"), summary (one plain sentence on what lives here), and files: a plain one-liner (max 14 words) for EACH of: {', '.join(targets) or 'none (return an empty list)'}.

{rows}""", sch, f"describe {dist.keys[i]}")
    out["files"] = [f for f in out["files"] if f["path"] in targets]
    return out


def _describe_app(c, dist):
    sch = {"type": "object", "additionalProperties": False, "required": ["app"], "properties": {"app": {"type": "string"}}}
    return ask(c.work, config.model("fast"), f"In one plain sentence, what is the {c.st['repo']} codebase? Its main folders: {', '.join(dist.keys)}.",
               sch, "describe app")["app"]


def s_propose(c, _):
    S = c.art("structure")["out"]
    reqs = c.p["requests"]
    c.log("Choosing walkthroughs to trace" if not reqs else "Matching your walkthrough requests to the code", stage="propose", pct=37)
    if reqs:
        proposed = [_request(c, S, r) for r in reqs]
        proposed = [p for p in proposed if p]
    else:
        proposed = fl.propose(c.work, c.st["repo"], S, c.p["flows"])
    c.log(f"{len(proposed)} walkthroughs to trace: " + "; ".join(p["title"] for p in proposed), pct=40)
    return proposed


def _request(c, S, text):
    """A visitor's own walkthrough ("export as PNG") -> title, description and candidate files, like propose() makes."""
    rows = "\n".join(f["path"] for f in S if f["functions"])
    sch = {"type": "object", "additionalProperties": False, "required": ["title", "desc", "candidates"], "properties": {
        "title": {"type": "string"}, "desc": {"type": "string"}, "candidates": {"type": "array", "items": {"type": "string"}}}}
    out = ask(c.work, config.model("fast"), f"""A new developer wants this user action in {c.st['repo']} explained end to end: "{text}".
Return title (max 5 words, imperative), desc (one plain sentence, max 16 words) and candidates: the ~30 files most likely involved, exactly as listed.

{rows}""", sch, f"request {text}")
    ok = {f["path"] for f in S}
    out["candidates"] = [p for p in dict.fromkeys(out["candidates"]) if p in ok]
    return out if len(out["candidates"]) >= 3 else None


def s_flow(c, stage):
    k = int(stage.split(":")[1])
    S, proposed = c.art("structure")["out"], c.art("propose")["out"]
    n = len(proposed)
    c.log(f"Tracing walkthrough {k + 1}/{n}: {proposed[k]['title']}", stage=stage, pct=40 + round(45 * k / max(n, 1)))
    raw = fl.trace_all(c.work, c.source(), S, c.st["repo"], [proposed[k]])
    kept, report = fl.verify(c.src, S, raw)
    flows = _flows(c, upto=k) + kept
    snapshot(c, S=S, desc=c.art("describe")["out"], flows=flows)
    if kept:
        c.log(f"Walkthrough ready: {kept[0]['title']} ({report['steps_verified']}/{report['steps_total']} steps checked against the source)",
              pct=40 + round(45 * (k + 1) / n), flows_ready=len(flows))
    else:
        c.log(f"Dropped “{proposed[k]['title']}”: too few steps matched real functions", pct=40 + round(45 * (k + 1) / n))
    return {"flows": kept, "report": report}


def _flows(c, upto):
    return [f for j in range(upto) for f in (c.art(f"flow:{j}") or {"out": {"flows": []}})["out"]["flows"]]


def s_analysis(c, _):
    S, desc = c.art("structure")["out"], c.art("describe")["out"]
    flows = _flows(c, upto=len(c.art("propose")["out"]))
    feat = c.p["features"]
    c.log("Analysing calls, events, state and reach", stage="analysis", pct=87)
    dist = Districts([f["path"] for f in S])
    sel, home = city.select(S, flows, dist)
    G = graph.build(c.source(), S)
    actions = reach.name_actions(c.work, c.st["repo"], G, flows)
    buildings = {e["src"]["path"] for e in sel if "src" in e}
    R = reach.compute(G, actions, flows, dist, buildings)
    # cranes need commit history, which a tarball doesn't carry: the web builder leaves that layer empty
    LY = layers.build(c.src, S, G, dist, c.art("fetch")["out"]["tests"], churn={"commits": 0, "files": {}})
    paper = []
    if feat["tabloid"]:
        c.log("Writing The Daily Commit", pct=93)
        paper = tabloid.paper(c.work, c.st["repo"], tabloid.facts(S, G, R, LY, buildings, home))
    return {"actions": actions, "reach": R, "layers": LY if feat["layers"] else layers.empty(), "paper": paper}


STAGES = {"fetch": s_fetch, "structure": s_structure, "describe": s_describe, "propose": s_propose, "flow": s_flow, "analysis": s_analysis}


# ---- the city so far ----
def data(c, S, desc=None, flows=(), extra=None):
    dist = Districts([f["path"] for f in S])
    flows = list(flows)
    sel, home = city.select(S, flows, dist)
    x = extra or {"actions": [], "reach": {}, "layers": layers.empty(), "paper": []}
    d = city.assemble(c.source(), c.st["repo"], c.st["key"], c.st["sha"][:7], dist, desc or {"app": "", "districts": [], "files": []},
                      sel, home, flows, x["actions"], x["reach"], x["layers"], x["paper"], c.cost(), len(S))
    d["texBase"] = TEX
    on = {}
    if not c.p["features"]["layers"]:
        on.update(roads=False, traffic=False)
    if not c.p["features"]["ghost"]:
        on["ghost"] = False
    if on:
        d["layersOn"] = on
    return d


def snapshot(c, **parts):
    page = site.page({**data(c, **parts), "building": True}, fog=c.p["features"]["fog"])
    n = c.st.get("snaps", 0) + 1
    path = f"jobs/{c.st['id']}/snap/{n:04d}.html"
    store.put(path, page, "text/html; charset=utf-8")
    c.st.update(snaps=n, snapshot=path)


def finish(st):
    """Assemble the finished city, publish it under its cache key, and mark the job done."""
    c = Ctx(st)
    S, desc, x = c.art("structure")["out"], c.art("describe")["out"], c.art("analysis")["out"]
    d = data(c, S=S, desc=desc, flows=_flows(c, upto=len(c.art("propose")["out"])), extra=x)
    page = site.page(d, fog=c.p["features"]["fog"])
    meta = {**d["meta"], "sha": st["sha"][:7], "key": st["key"], "params": c.p, "built": time.time(), "path": f"cities/{st['key']}.html"}
    store.put(meta["path"], page, "text/html; charset=utf-8")
    store.put(f"cities/{st['key']}.json", meta)
    c.st = jobs.log(c.st, f"Done: {meta['flows']} walkthroughs, ${c.cost():.3f} of AI", status="done", stage="done", pct=100,
                    city=meta["path"], snapshot=meta["path"], cost=c.cost())
    return c.st
