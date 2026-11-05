"""Deterministic structure: files -> functions/methods (with line), internal imports, line counts, first doc line.

Imports resolve relative paths, workspace packages (any package.json "name" in the repo) and app-local "@/" or "~/" aliases.
"""
import json, os, re

TOP = re.compile(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\*?\s+(\w+)|(?:const|let)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\(|<[A-Z]|function\b|\w+\s*=>|(?:React\.)?(?:memo|forwardRef)\b)|(?:abstract\s+)?class\s+(\w+))")
MODS = r"(?:(?:private|public|protected|static|readonly|override|async|get|set)\s+)"
ARROWPROP = re.compile(rf"^  {MODS}*(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\(|\w+\s*=>|withBatchedUpdates|throttle)")
METHOD = re.compile(rf"^  {MODS}*(\w+)\s*(?:<[^>]*>)?\((?:.*\)\s*(?::[^{{]+)?\{{\s*$|\s*$)")
INNER = re.compile(r"^  (?:const\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)\s*(?::[^=]+)?=>|\w+\s*=>|useCallback\(|async\s*\()|(?:async\s+)?function\s+(\w+)\s*\()")
KW = {"if", "for", "while", "switch", "catch", "constructor", "return", "super", "this", "function", "else", "new", "await", "typeof"}
IM = re.compile(r"""(?:import|export)\s[^'"]*?from\s+['"]([^'"]+)['"]|import\(['"]([^'"]+)['"]\)|require\(['"]([^'"]+)['"]\)""")
EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def packages(src):
    """Workspace packages: npm name -> folder, from every package.json in the repo (outside node_modules)."""
    out = {}
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "dist", "build")]
        if "package.json" in files and root != str(src):
            try:
                n = json.load(open(os.path.join(root, "package.json"))).get("name")
            except (ValueError, OSError):
                continue
            if n:
                out[n] = os.path.relpath(root, src)
    return out


def run(src, files):
    fileset = set(files)
    pkg = sorted(packages(src).items(), key=lambda kv: -len(kv[0]))

    def first(base):
        stem = re.sub(r"\.(?:m|c)?jsx?$", "", base)  # ESM TypeScript imports "./x.js" for the file x.ts
        for c in [base, *(stem + e for e in EXT), *(base + "/index" + e for e in EXT)]:
            if c in fileset:
                return c

    def resolve(f, spec):
        if spec.startswith("."):
            return first(os.path.normpath(os.path.join(os.path.dirname(f), spec)))
        if spec.startswith(("@/", "~/")):
            app = "/".join(f.split("/")[:2]) if f.split("/")[0] in ("apps", "packages") else ""
            for base in (f"{app}/{spec[2:]}", f"{app}/src/{spec[2:]}", f"src/{spec[2:]}", spec[2:]):
                if r := first(base.lstrip("/")):
                    return r
            return None
        for name, d in pkg:
            if spec == name or spec.startswith(name + "/"):
                rest = spec[len(name) + 1:]
                bases = [f"{d}/{rest}", f"{d}/src/{rest}"] if rest else [f"{d}/index", f"{d}/src/index"]
                return next((r for b in bases if (r := first(b))), None)

    out = []
    for f in files:
        lines = open(os.path.join(src, f), encoding="utf-8", errors="replace").read().split("\n")
        fns = [{"name": next(g for g in m.groups() if g), "line": i + 1} for i, l in enumerate(lines) if (m := TOP.match(l))]
        is_class = any(re.match(r"^(export\s+)?(default\s+)?(abstract\s+)?class\s", l) for l in lines)
        for i, l in enumerate(lines):
            m = (ARROWPROP.match(l) or METHOD.match(l)) if is_class else INNER.match(l)
            n = m and next((g for g in m.groups() if g), None)
            if n and n not in KW:
                fns.append({"name": n, "line": i + 1})
        fns.sort(key=lambda x: x["line"])
        seen = set()
        fns = [x for x in fns if not (x["name"] in seen or seen.add(x["name"]))]
        text = "\n".join(lines)
        imps = sorted({r for m in IM.finditer(text) if (r := resolve(f, next(g for g in m.groups() if g))) and r != f})
        doc = next((l.strip(" /*") for l in lines[:12] if l.strip().startswith(("//", "/**", "*")) and len(l.strip(" /*")) > 8), "")
        out.append({"path": f, "lines": len(lines), "functions": fns, "imports": imps, "doc": doc[:120]})
    return out


def callgraph(src, S):
    """Crude static calls: a function's body runs to the next extracted function in the same file; callees are known
    names in the same file or an imported one (barrel index files stand for what they re-export)."""
    CALL = re.compile(r"(?:\bthis\.|\.|\b)(\w+)\s*(?:\(|<[\w\s,|]*>\()|(?:this\.)(\w+)\b")
    by = {f["path"]: f for f in S}
    for f in S:
        L = open(os.path.join(src, f["path"]), encoding="utf-8", errors="replace").read().split("\n")
        known, seen = {}, set()

        def expand(q):
            if q in seen or q not in by:
                return
            seen.add(q)
            for fn in by[q]["functions"]:
                known.setdefault(fn["name"], q)
            if q.endswith(tuple("/index" + e for e in EXT)):
                for r in by[q]["imports"]:
                    expand(r)

        for q in f["imports"]:
            expand(q)
        for fn in f["functions"]:
            known[fn["name"]] = f["path"]
        fns = f["functions"]
        for k, fn in enumerate(fns):
            end = fns[k + 1]["line"] - 1 if k + 1 < len(fns) else f["lines"]
            names = {a or b for a, b in CALL.findall("\n".join(L[fn["line"]:end]))}
            fn["calls"] = sorted(f"{known[n]}::{n}" for n in names if n in known and not (known[n] == f["path"] and n == fn["name"]))
    return S
