"""Deterministic districts by folder (no AI): start from the top-level folders and keep splitting the biggest one
until there are about ten districts of readable size; the smallest leftovers merge into "Other"."""
import os
from collections import Counter

MAX = 10


def _group(p, prefix):
    """The next-level group of path p under prefix: a subfolder, or prefix itself for files directly in it."""
    rest = p[len(prefix):].lstrip("/") if prefix else p
    return f"{prefix}/{rest.split('/')[0]}".lstrip("/") if "/" in rest else (prefix or ".")


class Districts:
    def __init__(self, paths):
        groups, done = {".": list(paths)}, set()
        while len(groups) < MAX:
            open_ = [kv for kv in groups.items() if kv[0] not in done]
            if not open_:
                break
            key, members = max(open_, key=lambda kv: len(kv[1]))
            if len(members) < 0.25 * len(paths) and len(groups) >= 4:
                break
            prefix = "" if key == "." else key
            split = {}
            for p in members:
                split.setdefault(_group(p, prefix), []).append(p)
            if len(split) == 1 or len(groups) - 1 + len(split) > 3 * MAX:
                done.add(key)  # nothing to split, or it would shatter into too many tiny districts
                continue
            del groups[key]
            for k, v in split.items():
                groups.setdefault(k, []).extend(v)
                if k == key:
                    done.add(k)  # the files directly in the split folder
        ranked = sorted(groups.items(), key=lambda kv: -len(kv[1]))
        keep, rest = ranked[:MAX - 1], ranked[MAX - 1:]
        if len(ranked) == MAX:
            keep, rest = ranked, []
        self.keys = [k for k, _ in keep] + (["(other)"] if rest else [])
        self.of = {p: i for i, (_, v) in enumerate(keep) for p in v}
        for _, v in rest:
            for p in v:
                self.of[p] = len(keep)
        self.names = [self.pretty(k) for k in self.keys]

    @staticmethod
    def pretty(key):
        if key in (".", "(other)"):
            return "Root files" if key == "." else "Other"
        segs = [s for s in key.split("/") if s not in ("apps", "packages", "src", "lib", "")]
        return " · ".join(s.replace("-", " ").replace("_", " ").capitalize() for s in segs[-2:]) or key

    def __call__(self, p):
        """District index of any path (also files outside the mapped set, such as tests): longest matching prefix."""
        if p in self.of:
            return self.of[p]
        best, n = len(self.keys) - 1, -1
        for i, k in enumerate(self.keys):
            pre = "" if k == "." else k.rstrip("/")
            if (pre == "" or p.startswith(pre + "/")) and len(pre) > n:
                best, n = i, len(pre)
        return best

    def counts(self):
        return Counter(self.of.values())
