"""Boarding City CLI.

  python -m boarding_city build <owner/name[@ref] | https://github.com/owner/name[/tree/<ref>]> [--flows N] [--key KEY] [--out DIR]
  python -m boarding_city site      regenerate site/index.html's repo list from site/repos.json

Every step's output is cached in .cache/<owner>__<name>/<commit>/, so re-running a build for the same commit is free.
"""
import argparse, json, re, sys, time
from pathlib import Path
from . import config, repo as gitrepo, extract, flows as fl, graph, reach, layers, tabloid, city, site
from .districts import Districts
from .llm import LLMError, spent


def step(work, name, fn):
    p = work / f"{name}.json"
    if p.exists():
        return json.loads(p.read_text())
    t = time.time()
    out = fn()
    p.write_text(json.dumps(out))
    print(f"  {name:10s} {time.time() - t:5.1f}s  (spent so far ${spent(work):.3f})")
    return out


def build(spec, n_flows, key, out):
    try:
        owner, name, ref = gitrepo.parse(spec)
        repo = f"{owner}/{name}"
        key = key or re.sub(r"[^a-z0-9]", "", name.lower()) or "repo"
        work, sha = gitrepo.checkout(owner, name, ref)
    except (ValueError, LookupError) as e:
        raise SystemExit(str(e))
    src = work / "src"
    print(f"{repo} @ {sha}  ->  {work}")
    paths = gitrepo.source_files(src)
    if not paths:
        raise SystemExit("no JS/TS source files found (Boarding City maps JavaScript and TypeScript repos)")
    S = step(work, "structure", lambda: extract.callgraph(src, extract.run(src, paths)))
    dist = Districts([f["path"] for f in S])
    G = step(work, "graph", lambda: graph.build(src, S))
    api = graph.api_entries(src, S, G)  # a library: walk its exported API instead of UI actions
    if api:
        print(f"  library: no UI entry points; tracing calls to its {len(api)} exported functions")
    proposed = step(work, "proposed", lambda: fl.propose(work, repo, S, n_flows, api))
    raw = step(work, "traces", lambda: fl.trace_all(work, src, S, repo, proposed))
    flows, report = step(work, "flows", lambda: fl.verify(src, S, raw))
    print(f"  verified: {report['steps_verified']}/{report['steps_total']} steps are real functions; {report['flows_kept']}/{report['flows_total']} flows kept")
    sel, home = city.select(S, flows, dist)
    targets = [e["src"]["path"] for e in sel if "src" in e and not e.get("nosnip")]
    desc = step(work, "describe", lambda: fl.describe(work, repo, S, dist, targets))
    actions = step(work, "actions", lambda: reach.name_actions(work, repo, G, flows))
    buildings = {e["src"]["path"] for e in sel if "src" in e}
    R = step(work, "reach", lambda: reach.compute(G, actions, flows, dist, buildings))
    LY = step(work, "layers", lambda: layers.build(src, S, G, dist, gitrepo.test_files(src)))
    shown = {e["src"]["path"] for e in sel if "src" in e}
    paper = step(work, "paper", lambda: tabloid.paper(work, repo, tabloid.facts(S, G, R, LY, shown, home)))
    data = city.assemble(src, repo, key, sha, dist, desc, sel, home, flows, actions, R, LY, paper, spent(work), len(S),
                         library=bool(api), note=fl.why_none(api, proposed, report))
    out_dir = Path(out) if out else config.SITE / key
    site.render(data, out_dir)
    site.register(data["meta"])
    print(f"done: {out_dir}/demo.html  ({len(data['files'])} buildings, {len(flows)} walkthroughs, total AI cost ${spent(work):.3f})")


def main():
    ap = argparse.ArgumentParser(prog="boarding_city", description="Boarding City: explore a codebase as a 3D city.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="map a GitHub JS/TS repo into site/<key>/")
    b.add_argument("repo", help="owner/name or https://github.com/owner/name, optionally pinned: owner/name@<sha|branch|tag>")
    b.add_argument("--flows", type=int, default=6, help="walkthroughs to propose and trace (default 6)")
    b.add_argument("--key", help="short id used in the URL (default: the repo name)")
    b.add_argument("--out", help="output folder (default: site/<key>)")
    sub.add_parser("site", help="regenerate site/index.html's repo list from site/repos.json")
    a = ap.parse_args()
    if a.cmd == "build":
        try:
            build(a.repo, a.flows, a.key, a.out)
        except LLMError as e:
            raise SystemExit(f"AI call failed: {e}")
    else:
        site.write_index()


if __name__ == "__main__":
    sys.exit(main())
