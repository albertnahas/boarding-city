"""Web-builder bookkeeping: request validation, cache keys, job state, the daily spend cap and per-visitor rate limits.

Blob layout (all write-once):
  jobs/<id>/state/<seq>.json     job state snapshots; the newest one is the current state
  jobs/<id>/art/<stage>.json     each stage's output (a re-delivered stage finds it and skips the work)
  jobs/<id>/snap/<seq>.html      the city as built so far
  cities/<key>.html|.json        finished cities and their metadata, key = owner__name__sha12__paramshash
  jobs/<id>/lease/<n>            run n of the job (create-only: whoever creates it is the job's only runner)
  spend/<day>/<job>/<ns>-<microdollars>   spend markers; a job's newest marker is its cost (or its reservation)
  rl/<kind>/<visitor>/<epoch>-<rand>      one marker per build or estimate, for the hourly limits
"""
import hashlib, ipaddress, json, os, re, secrets, time
from datetime import datetime, timezone
from .. import config, repo as gitrepo
from . import store

MAX_FILES = int(os.environ.get("BC_MAX_FILES", "1500"))
DAILY_CAP = float(os.environ.get("BC_DAILY_CAP_USD", "5"))
RATE = int(os.environ.get("BC_BUILDS_PER_HOUR", "3"))
ESTIMATES = int(os.environ.get("BC_ESTIMATES_PER_HOUR", "20"))
RESUMES = 3  # a job that keeps getting cut off is stopped instead of retried forever
EFFORTS = ("low", "medium", "high")
FEATURES = ("layers", "fog", "tabloid", "ghost")


class Refused(Exception):
    """A request we won't run, with a message written for the person who sent it."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def parse_repo(spec):
    """-> (owner, name, ref or None): only github.com repos, so the builder never fetches any other host."""
    try:
        return gitrepo.parse(spec)
    except ValueError as e:
        raise Refused(str(e))


def parse_params(p):
    p = p or {}
    models = [m for m in config.PRICES]
    try:
        flows = int(p.get("flows", 6))
        max_files = int(p.get("max_files", MAX_FILES))
    except (TypeError, ValueError):
        raise Refused("Flows and max files must be whole numbers.")
    requests_ = [str(r).strip()[:80] for r in (p.get("requests") or []) if str(r).strip()][:10]
    out = {"flows": len(requests_) or min(max(flows, 1), 10), "requests": requests_,
           "fast_model": p.get("fast_model") or config.MODELS["fast"], "trace_model": p.get("trace_model") or config.MODELS["trace"],
           "effort": p.get("effort") or config.MODELS["effort"], "max_files": min(max(max_files, 20), MAX_FILES),
           "features": {f: bool((p.get("features") or {}).get(f, True)) for f in FEATURES}}
    for k in ("fast_model", "trace_model"):
        if out[k] not in models:
            raise Refused(f"Unknown model {out[k]!r}. Choose one of: {', '.join(models)}.")
    if out["effort"] not in EFFORTS:
        raise Refused(f"Reasoning effort must be one of: {', '.join(EFFORTS)}.")
    return out


def cache_key(owner, name, sha, params):
    h = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:8]
    return f"{owner}__{name}__{sha[:12]}__{h}".lower()


def estimate(files, lines, params, library=False):
    """(minutes low, high), (dollars low, high) from measured builds: ky (31 files, 4 flows) $0.02, Excalidraw (425, 8)
    $0.25, Supabase (6.8k files, 6 flows) $0.10 on gpt-6-luna + gpt-6.1-terra; each flow is one stage."""
    n = params["flows"]
    ti, to = config.PRICES[params["trace_model"]]
    scale = (ti + to * 0.2) / 2.0  # the trace calls dominate; gpt-6.1-terra = 1.0
    effort = {"low": 1.0, "medium": 1.6, "high": 2.5}[params["effort"]]
    # a trace reads the functions of the files on its path, so its cost grows with the repo (ky: $0.005/flow, Excalidraw: $0.03)
    usd = (0.003 + n * (0.003 + files * 0.00002) * scale * effort, 0.01 + n * (0.008 + files * 0.00008) * scale * effort)
    if library:  # every exported function is named as an API call, and a trace reads whole (often large) API files
        usd = usd[0] * 1.5, usd[1] * 1.6  # measured: sindresorhus/is, 4 API walkthroughs, $0.044
    sec = 25 + files * 0.04 + lines / 20000 + n * 18 * effort, 45 + files * 0.09 + lines / 8000 + n * 40 * effort
    return [round(s / 60, 1) for s in sec], [round(u, 2) for u in usd]


# ---- job state ----
def new_job_id():
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)


def valid_job_id(job):
    return bool(re.fullmatch(r"\d{14}-[0-9a-f]{8}", job or ""))


def state(job):
    """The newest state snapshot of a job, or None."""
    rows = store.listing(f"jobs/{job}/state/")
    if not rows:
        return None
    return store.get_json(max(rows)[1])


def save(st):
    """Write the next state snapshot. Create-only: a job has one runner at a time (see lease), so a collision means
    a second writer, which must fail rather than overwrite."""
    st["seq"] = st.get("seq", 0) + 1
    st["updated"] = time.time()
    if not store.create(f"jobs/{st['id']}/state/{st['seq']:06d}.json", json.dumps(st, separators=(",", ":")).encode(), "application/json"):
        raise RuntimeError(f"job {st['id']}: state {st['seq']} written twice")
    return st


def lease(job, n):
    """Claim run n of a job. -> True if this caller is now its only runner."""
    return store.create(f"jobs/{job}/lease/{n:02d}")


def leased(job):
    """The newest run number of a job."""
    return max((int(p.rsplit("/", 1)[1]) for p, _, _ in store.listing(f"jobs/{job}/lease/")), default=-1)


def log(st, msg, **fields):
    st.update(fields)
    st.setdefault("created", time.time())
    st["log"] = (st.get("log", []) + [{"t": round(time.time() - st["created"], 1), "msg": msg}])[-40:]
    return save(st)


# ---- spend and rate limits ----
def _day():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def spent_today(before=None):
    """Today's AI spend: each job's newest marker. With before (a marker time), only jobs that started earlier count,
    so of two simultaneous reservations the first one in is the one that passes."""
    first, latest = {}, {}
    for path, _, _ in store.listing(f"spend/{_day()}/"):
        job, mark = path.split("/")[2], path.split("/")[3]
        ns, micro = (int(x) for x in mark.split("-"))
        first[job] = min(first.get(job, ns), ns)
        if ns >= latest.get(job, (-1, 0))[0]:
            latest[job] = (ns, micro)
    return sum(m for job, (_, m) in latest.items() if before is None or first[job] <= before) / 1e6


def record_spend(job, usd):
    """A job's running cost (or its reservation); its newest marker replaces the earlier ones in the day's total."""
    ns = time.time_ns()
    store.create(f"spend/{_day()}/{job}/{ns}-{int(usd * 1e6)}")
    return ns


BUDGET = "Today's build budget (${:.2f}) is used up. Cached cities still open instantly; new builds reopen tomorrow (UTC)."


def reserve(job, usd):
    """Hold a new build's estimated cost against today's budget before it starts, so parallel builds can't all pass."""
    if spent_today(before=record_spend(job, usd)) > DAILY_CAP:
        record_spend(job, 0)
        raise Refused(BUDGET.format(DAILY_CAP), 429)


def check_budget():
    if spent_today() > DAILY_CAP:
        raise Refused(BUDGET.format(DAILY_CAP), 429)


def visitor(ip):
    """A salted hash of the visitor's address: IPv4 as is, IPv6 by its /64 (one household or host gets one id)."""
    try:
        a = ipaddress.ip_address((ip or "").strip())
        key = str(ipaddress.ip_network(f"{a}/64", strict=False).network_address) if a.version == 6 else str(a)
    except ValueError:
        key = "?"
    return hashlib.sha256((os.environ.get("BC_SALT", "boarding-city") + key).encode()).hexdigest()[:16]


def take(kind, who, limit, message):
    """Count one use of `kind` against a visitor's hourly limit. The marker is written before counting, so parallel
    requests see each other, and the first `limit` of the hour pass; a refused request removes its own marker."""
    mine = f"rl/{kind}/{who}/{time.time():.6f}-{secrets.token_hex(3)}"
    store.create(mine)
    hour_ago = time.time() - 3600
    recent = sorted(p for p, _, _ in store.listing(f"rl/{kind}/{who}/") if float(p.rsplit("/", 1)[1].split("-")[0]) > hour_ago)
    if mine not in recent[:limit]:
        store.delete([mine])
        raise Refused(message, 429)
