"""Resolve a GitHub repo, clone it once per commit into .cache/, and list its JS/TS source files."""
import re, subprocess
from . import config

SRC_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
SKIP_DIR = re.compile(r"(^|/)(node_modules|dist|build|out|coverage|vendor|\.next|\.turbo|\.git|__snapshots__|fixtures?|e2e|storybook-static)(/|$)")
TEST = re.compile(r"(\.test\.|\.spec\.|\.test-d\.|\.stories\.|(^|/)__tests__/|(^|/)tests?(-d)?/)")


def parse(spec):
    m = re.search(r"(?:github\.com[/:])?([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", spec.strip())
    if not m:
        raise SystemExit(f"not a GitHub repo: {spec} (use owner/name or https://github.com/owner/name)")
    return m.group(1), m.group(2)


def git(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def checkout(owner, name):
    """-> (work dir for this commit, short sha). The clone is shallow, deepened to the last 90 days for the cranes layer."""
    url = f"https://github.com/{owner}/{name}.git"
    sha = git("ls-remote", url, "HEAD").split()[0][:7]
    work = config.CACHE / f"{owner}__{name}" / sha
    src = work / "src"
    if not (src / ".git").exists():
        work.mkdir(parents=True, exist_ok=True)
        git("clone", "--depth", "1", "--single-branch", url, str(src))
        subprocess.run(["git", "fetch", "--shallow-since=90.days.ago"], cwd=src, capture_output=True)
    return work, sha


def source_files(src):
    out = []
    for p in git("ls-files", cwd=src).splitlines():
        if p.endswith(SRC_EXT) and not p.endswith((".d.ts", ".min.js")) and not SKIP_DIR.search(p) and not TEST.search(p):
            out.append(p)
    return out


def test_files(src):
    return [p for p in git("ls-files", cwd=src).splitlines() if p.endswith(SRC_EXT) and TEST.search(p) and "node_modules" not in p]
