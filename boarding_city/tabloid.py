"""The Daily Commit: real facts computed from the analysis, plus one fast-model call that only adds tabloid wit.
Numbers in a headline always come from the analysis, never from the model."""
import collections, os
from . import config
from .llm import ask


def facts(S, G, reach, LY, shown, home):
    def scene(p, fn=None):
        b = p if p in shown else home.get(p)
        return {"path": b, "fn": fn if (b == p and fn) else None} if b else None
    out = []
    indeg = collections.Counter(b for a, o in G["edges"].items() for b, k in o.items() if k == "static")
    if indeg:
        k, n = indeg.most_common(1)[0]
        p, f = k.split("::")
        out.append({"id": "most_called", "fact": f"The most-called function is {f}() in {os.path.basename(p)}, called from {n} places in the code", "number": n, "scene": scene(p, f)})
    big = max(S, key=lambda x: x["lines"])
    out.append({"id": "biggest_file", "fact": f"The biggest file is {os.path.basename(big['path'])} with {big['lines']:,} lines", "number": big["lines"], "scene": scene(big["path"])})
    un = [k for k, v in reach.items() if v["n"] == 0 and v["b"] != "infra"]
    if reach:
        worst = collections.Counter(k.split("::")[0] for k in un).most_common(1)
        out.append({"id": "unreached", "fact": f"{len(un):,} of {len(reach):,} mapped functions are not reached by any user action in the static call graph (they may still run dynamically)",
                    "number": len(un), "scene": scene(worst[0][0]) if worst else None})
    pub = collections.Counter()
    for a, b, kind, c in LY["buses"]["routes"]:
        pub[a] += c
    if pub:
        p, n = pub.most_common(1)[0]
        out.append({"id": "busiest_events", "fact": f"The busiest event publisher is {os.path.basename(p)}, with {n} event subscriptions listening to it", "number": n, "scene": scene(p)})
    if LY["cranes"]["files"]:
        p, n = LY["cranes"]["files"][0]
        out.append({"id": "most_commits", "fact": f"The file changed most often lately is {os.path.basename(p)}: {n} commits in the last 90 days", "number": n, "scene": scene(p)})
    imp = collections.Counter(q for x in S for q in x["imports"])
    if imp:
        p, n = imp.most_common(1)[0]
        out.append({"id": "most_imported", "fact": f"The most-imported module is {os.path.basename(p)}, imported by {n} files", "number": n, "scene": scene(p)})
    return out


def paper(work, repo, F):
    schema = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["id", "headline", "deck"],
        "properties": {"id": {"type": "string", "enum": [f["id"] for f in F]}, "headline": {"type": "string"}, "deck": {"type": "string"}}}}}}
    items = ask(work, config.model("fast"), f"""You write the front page of "The Daily Commit", a playful tabloid about the {repo} codebase seen as a city.
For EACH fact write: headline (UPPERCASE, max 10 words, tabloid wit, e.g. "LOCAL HELPER CALLED 5,603 TIMES, STILL NO PROMOTION") and deck (one plain sentence, max 18 words, saying the fact straight).
Rules: keep every number EXACTLY as given; be kind: joke about the code, never about people; never name contributors or invent facts.

""" + "\n".join(f"- {f['id']}: {f['fact']}" for f in F), schema, "daily commit")["items"]
    H = {h["id"]: h for h in items}
    return [{**f, "headline": H[f["id"]]["headline"], "deck": H[f["id"]]["deck"]} for f in F if f["id"] in H]
