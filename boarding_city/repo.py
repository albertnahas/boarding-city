"""Resolve a GitHub repo, get its files once per commit (a git clone for the CLI, a tarball for the web builder, which
has no git), and list its JS/TS source files."""
import os, re, subprocess, tarfile
import requests
from . import config

SRC_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
SKIP_DIR = re.compile(r"(^|/)(node_modules|dist|build|out|coverage|vendor|\.next|\.turbo|\.git|__snapshots__|fixtures?|e2e|storybook-static)(/|$)")
TEST = re.compile(r"(\.test\.|\.spec\.|\.test-d\.|\.stories\.|(^|/)__tests__/|(^|/)tests?(-d)?/)")


# owner/name, a github.com URL, or either pinned to a commit: owner/name@<sha|branch|tag>, github.com/o/n/tree/<ref>,
# github.com/o/n/commit/<sha>. Nothing else: the web builder only ever fetches from github.com.
SPEC = re.compile(r"(?:(?:https?://)?(?:www\.)?github\.com/|git@github\.com:)?([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100}?)(?:\.git)?"
                  r"(?:/(?:tree|commit)/(?P<t>[\w./-]{1,200}?)|@(?P<a>[\w./-]{1,200}))?/?")


def parse(spec):
    """-> (owner, name, ref or None). Raises ValueError for anything that isn't a GitHub repo."""
    m = SPEC.fullmatch((spec or "").strip())
    ref = m and (m.group("t") or m.group("a"))
    if not m or m.group(2) in (".", "..") or (ref and (".." in ref or ref[0] in "-/")):
        raise ValueError("Paste a public GitHub repository, like sindresorhus/ky, github.com/sindresorhus/ky, "
                         "or one pinned to a commit: sindresorhus/ky@v1.7.0")
    return m.group(1), m.group(2), ref


def git(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def checkout(owner, name, ref=None):
    """-> (work dir for this commit, short sha). The clone is shallow, deepened to the last 90 days for the cranes layer."""
    url = f"https://github.com/{owner}/{name}.git"
    sha = resolve(owner, name, ref)
    work = config.CACHE / f"{owner}__{name}" / sha[:7]
    src = work / "src"
    if not (src / ".git").exists():
        src.mkdir(parents=True, exist_ok=True)
        git("init", "-q", cwd=src)
        git("fetch", "-q", "--depth", "1", url, sha, cwd=src)
        git("checkout", "-q", "FETCH_HEAD", cwd=src)
        subprocess.run(["git", "fetch", "-q", "--shallow-since=90.days.ago", url, sha], cwd=src, capture_output=True)
    return work, sha[:7]


def resolve(owner, name, ref=None):
    """Full commit sha of ref (default: the default branch). Branches and tags come from git's smart-HTTP ref
    advertisement (no API rate limit); a commit sha, short or full, is checked with the GitHub API."""
    r = requests.get(f"https://github.com/{owner}/{name}.git/info/refs?service=git-upload-pack", timeout=20)
    if r.status_code in (401, 404):
        raise LookupError(f"{owner}/{name} isn't a public GitHub repository")
    r.raise_for_status()
    refs = {n.decode(): h.decode() for h, n in re.findall(rb"([0-9a-f]{40}) ([^\s\x00]+)", r.content)}
    for k in ([ref, f"refs/heads/{ref}", f"refs/tags/{ref}^{{}}", f"refs/tags/{ref}"] if ref else ["HEAD"]):
        if k in refs:
            return refs[k]
    if ref and re.fullmatch(r"[0-9a-fA-F]{7,40}", ref):
        token = os.environ.get("GITHUB_TOKEN")
        c = requests.get(f"https://api.github.com/repos/{owner}/{name}/commits/{ref}", timeout=20,
                         headers={"Accept": "application/vnd.github.sha", **({"Authorization": f"Bearer {token}"} if token else {})})
        if c.ok and re.fullmatch(r"[0-9a-f]{40}", c.text.strip()):
            return c.text.strip()
        if c.status_code in (403, 429):
            raise LookupError("GitHub's API is rate-limiting commit lookups right now; pin a branch or tag, or try again later")
    raise LookupError(f"{owner}/{name} has no commits yet" if not ref else f"{owner}/{name} has no branch, tag or commit called {ref}")


def _tarball(owner, name, sha):
    r = requests.get(f"https://codeload.github.com/{owner}/{name}/tar.gz/{sha}", stream=True, timeout=60)
    r.raise_for_status()
    r.raw.decode_content = True
    return r


def _wanted(rel):
    return (rel.endswith(SRC_EXT) or os.path.basename(rel) == "package.json") and not re.search(r"(^|/)node_modules/", rel)


def count(owner, name, sha, max_bytes=80_000_000):
    """Stream the tarball without saving it: (source files, approx lines, complete?). Stops at max_bytes of archive."""
    files = lines = 0
    with _tarball(owner, name, sha) as r:
        with tarfile.open(fileobj=r.raw, mode="r|gz") as tar:
            for m in tar:
                if r.raw.tell() > max_bytes:
                    return files, lines, False
                rel = m.name.split("/", 1)[-1]
                if m.isfile() and _is_source(rel):
                    files += 1
                    lines += m.size // 32  # ~32 bytes per line of JS/TS
    return files, lines, True


def fetch(owner, name, sha, dest, max_files, max_bytes=60_000_000, max_member=2_000_000, max_archive=250_000_000):
    """Extract the source files (and package.json files, for workspace imports) of one commit into dest. Bounded:
    a file over max_member is skipped, and more than max_files source files or max_bytes extracted stops it."""
    dest.mkdir(parents=True, exist_ok=True)
    files = total = 0
    with _tarball(owner, name, sha) as r:
        with tarfile.open(fileobj=r.raw, mode="r|gz") as tar:
            for m in tar:
                if r.raw.tell() > max_archive:
                    raise ValueError("This repository is too large to download here. Build it with the command-line tool.")
                rel = m.name.split("/", 1)[-1]
                if not m.isfile() or not _wanted(rel) or m.name.startswith("/") or ".." in rel.split("/") or m.size > max_member:
                    continue
                files += _is_source(rel)
                total += m.size
                if files > max_files or total > max_bytes:
                    raise ValueError(f"This repository has more than {max_files:,} source files (or {max_bytes // 1_000_000} MB of them); "
                                     "on-demand builds stop there. Build it with the command-line tool.")
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(tar.extractfile(m).read())
    return dest


def _all_files(src):
    if (src / ".git").exists():
        return git("ls-files", cwd=src).splitlines()
    out = []
    for root, dirs, fs in os.walk(src):
        dirs[:] = [d for d in dirs if d != "node_modules"]
        out += [os.path.relpath(os.path.join(root, f), src) for f in fs]
    return sorted(out)


def _is_source(p):
    return p.endswith(SRC_EXT) and not p.endswith((".d.ts", ".min.js")) and not SKIP_DIR.search(p) and not TEST.search(p)


def source_files(src):
    return [p for p in _all_files(src) if _is_source(p)]


def test_files(src):
    return [p for p in _all_files(src) if p.endswith(SRC_EXT) and TEST.search(p) and "node_modules" not in p]
