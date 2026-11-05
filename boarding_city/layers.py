"""City layers from static analysis only (no AI): roads (imports), traffic (cross-file static calls), buses (events),
flights (external/async I/O), power lines (shared state), cranes (git churn, last 90 days), lit windows and doors
(per function), entry-point landmarks and parks (test files per district)."""
import collections, os, re, subprocess

SERVICES = {
    "HTTP": r"\bfetch\(|XMLHttpRequest|\baxios\b|\bky\b\.",
    "WebSocket": r"new WebSocket|socket\.io|\bio\(|RealtimeClient|\.channel\(",
    "Firebase": r"\bfirebase\b",
    "Storage": r"localStorage|sessionStorage|indexedDB|idb-keyval",
    "Workers": r"new Worker\(|\bpostMessage\(|workerpool",
    "Clipboard": r"navigator\.clipboard|ClipboardItem|\bcopyToClipboard\(",
    "Files": r"\bfileOpen\(|\bfileSave\(|showSaveFilePicker|showOpenFilePicker",
    "Analytics": r"posthog|\btelemetry\b|\bsendEvent\(",
}
PLANTS = {
    "React Query": (r"\buseQuery\(|\buseInfiniteQuery\(|\bgetQueryData\(|\buse\w+(?:Query|InfiniteQuery)\(", r"\buseMutation\(|\binvalidateQueries\(|\bsetQueryData\(|\buse\w+Mutation\("),
    "Atoms & stores": (r"\buseAtomValue\(|\buseAtom\(|\buseSnapshot\(|\buse\w+Store\(|\buseSelector\(", r"\buseSetAtom\(|\bproxy\(|\bcreateStore\(|\bdispatch\(|\bset\w*State\("),
    "React context": (r"\buseContext\(|\buse\w+Context\(\)", r"\bcreateContext\(|\.Provider\b"),
}


def build(src, S, G, dist, tests):
    by = {f["path"]: f for f in S}
    text = {p: open(os.path.join(src, p), encoding="utf-8", errors="replace").read() for p in by}
    out = {}
    pairs, imp = collections.Counter(), 0
    for f in S:
        for q in f["imports"]:
            imp += 1
            a, b = dist(f["path"]), dist(q)
            if a != b:
                pairs[tuple(sorted((a, b)))] += 1
    out["roads"] = {"imports": imp, "highways": [[a, b, n] for (a, b), n in pairs.most_common()]}
    calls = collections.Counter()
    for a, o in G["edges"].items():
        for b, k in o.items():
            pa, pb = a.split("::")[0], b.split("::")[0]
            if k == "static" and pa != pb:
                calls[(pa, pb)] += 1
    out["traffic"] = {"edges": sum(calls.values()), "pairs": [[a, b, n] for (a, b), n in calls.most_common()]}
    pub, sub, bus = collections.defaultdict(set), collections.defaultdict(set), collections.Counter()
    for p, t in text.items():
        for name, verb in re.findall(r"\b(\w*Emitter)\b\s*\.\s*(trigger|emit|on|once|subscribe)\(", t):
            (pub if verb in ("trigger", "emit") else sub)[name].add(p)
    for name in pub:
        for a in pub[name]:
            for b in sub.get(name, ()):
                if a != b:
                    bus[(a, b, "emitter " + name)] += 1
    comp = {}
    for f in S:
        for fn in f["functions"]:
            if fn["name"][:1].isupper():
                comp.setdefault(fn["name"], f["path"])
    for p, t in text.items():  # <Child onX={...}>: the child's file publishes the event, the parent's file listens
        for m in re.finditer(r"<([A-Z]\w*)\b", t):
            end = t.find(">", m.end())
            seg = t[m.end():end if end > 0 else m.end() + 400][:1500]
            c = comp.get(m.group(1))
            if c and c != p:
                for ev in set(re.findall(r"\b(on[A-Z]\w*)=\{", seg)):
                    bus[(c, p, "prop " + ev)] += 1
    dom = collections.Counter({p: n for p, t in text.items() if (n := len(re.findall(r"\.addEventListener\(", t)))})
    out["buses"] = {"emitters": sorted(set(pub) | set(sub)), "routes": [[a, b, k, n] for (a, b, k), n in bus.most_common()],
                    "dom": [[p, n] for p, n in dom.most_common()], "edges": sum(bus.values()) + sum(dom.values())}
    fl = [[p, s, n] for p, t in text.items() for s, rx in SERVICES.items() if (n := len(re.findall(rx, t)))]
    out["flights"] = {"services": list(SERVICES), "routes": sorted(fl, key=lambda x: -x[2]), "edges": sum(x[2] for x in fl)}
    pw = [[p, plant, r, w] for p, t in text.items() for plant, (rd, wr) in PLANTS.items()
          if (r := len(re.findall(rd, t))) | (w := len(re.findall(wr, t)))]
    out["power"] = {"plants": list(PLANTS), "lines": sorted(pw, key=lambda x: -(x[2] + x[3])), "edges": len(pw)}
    git = lambda *a: subprocess.run(["git", "-C", str(src), *a], capture_output=True, text=True).stdout
    churn = collections.Counter(x for x in git("log", "--since=90 days ago", "--format=", "--name-only").split() if x in by)
    out["cranes"] = {"commits": int(git("rev-list", "--count", "--since=90 days ago", "HEAD").strip() or 0), "files": churn.most_common()}
    indeg = collections.Counter(b for a, o in G["edges"].items() for b, k in o.items() if k == "static")
    lines = {p: t.split("\n") for p, t in text.items()}
    out["functions"] = {f"{f['path']}::{x['name']}": [1 if lines[f["path"]][x["line"] - 1].lstrip().startswith("export") else 0,
                                                      indeg.get(f"{f['path']}::{x['name']}", 0)] for f in S for x in f["functions"]}
    out["entries"] = collections.Counter(e.split("::")[0] for e in G["entries"]).most_common()
    out["parks"] = {str(d): n for d, n in collections.Counter(dist(p) for p in tests).items()}
    return out
