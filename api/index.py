"""Boarding City's API: estimate a build, start one (fire and forget), poll its progress, list recent cities, serve
built cities from Blob storage. The build runs after the 202 is sent, in the background of the same invocation (boarding_city/cloud/worker.py)."""
import asyncio, os, re, time
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from vercel.functions import wait_until
from boarding_city import repo as gitrepo, site
from boarding_city.cloud import jobs, store, worker

app = FastAPI(title="Boarding City", docs_url=None, redoc_url=None)


def visitor(request):
    return jobs.visitor(request.headers.get("x-real-ip") or (request.headers.get("x-forwarded-for") or "").split(",")[0])


def refuse(e):
    return JSONResponse({"error": str(e)}, status_code=e.status)


async def body(request):
    try:
        b = await request.json()
    except ValueError:
        b = None
    if not isinstance(b, dict):
        raise jobs.Refused("Send a JSON body like {\"repo\": \"owner/name\"}.")
    return b


def resolve(owner, name, ref=None):
    try:
        return gitrepo.resolve(owner, name, ref)
    except LookupError as e:
        raise jobs.Refused(f"{e}. Check the spelling, and that the repository is public.", 404)


def cached(key):
    path = f"cities/{key}.json"
    return store.get_json(path) if store.url_of(path) else None


@app.post("/api/estimate")
async def estimate(request: Request):
    try:
        b = await body(request)
        owner, name, ref = jobs.parse_repo(b.get("repo"))
        params = jobs.parse_params(b.get("params"))
        jobs.take("estimate", visitor(request), jobs.ESTIMATES, "That's a lot of estimates in one hour. Try again in a bit.")
        sha = resolve(owner, name, ref)
        hit = cached(jobs.cache_key(owner, name, sha, params))
        files, lines, complete, ui = gitrepo.count(owner, name, sha)
        minutes, usd = jobs.estimate(files, lines, params, library=complete and not ui)
        capped, usd = usd[1] > jobs.BUILD_CAP, [min(u, jobs.BUILD_CAP) for u in usd]
        too_big = not complete or files > params["max_files"]
        return {"repo": f"{owner}/{name}", "sha": sha, "files": files, "lines": lines, "complete": complete, "too_big": too_big, "library": complete and not ui,
                "max_files": params["max_files"], "builds": bool(os.environ.get("OPENAI_API_KEY")), "minutes": minutes, "usd": usd, "cap": jobs.BUILD_CAP, "capped": capped, "params": params, "cached": hit,
                "message": None if not too_big else (f"This repository has {files:,} source files; on-demand builds take up to {params['max_files']:,}."
                            if complete else "This repository is too large to scan here.") + " Use the command-line tool for big repositories."}
    except jobs.Refused as e:
        return refuse(e)


@app.post("/api/build")
async def build(request: Request):
    try:
        b = await body(request)
        owner, name, ref = jobs.parse_repo(b.get("repo"))
        params = jobs.parse_params(b.get("params"))
        sha = b["sha"] if re.fullmatch(r"[0-9a-f]{40}", str(b.get("sha"))) else resolve(owner, name, ref)
        key = jobs.cache_key(owner, name, sha, params)
        if b.get("use_cache", True) and (hit := cached(key)):
            return {"cached": True, "city": hit}
        if not os.environ.get("OPENAI_API_KEY"):
            raise jobs.Refused("Live builds need the server's AI key, which isn't set up here yet. Cached cities still open; "
                                 f"to map {owner}/{name} now, run: python -m boarding_city build {owner}/{name}@{sha[:7]}", 503)
        jobs.take("build", visitor(request), jobs.RATE,
                  f"You've started {jobs.RATE} builds in the last hour. Try again in a bit, or open a city that's already built.")
        # sized here too (not only in the estimate), so a request that skips the estimate can't start an oversized build
        files, lines, complete, ui = gitrepo.count(owner, name, sha)
        if not complete or files > params["max_files"]:
            raise jobs.Refused(f"This repository has {'more than ' if not complete else ''}{files:,} source files; on-demand builds take up to "
                               f"{params['max_files']:,}. Build it with the command-line tool.")
        job = jobs.new_job_id()
        usd = min(jobs.estimate(files, lines, params, library=not ui)[1][1], jobs.BUILD_CAP)
        jobs.reserve(job, usd)
        st = {"id": job, "repo": f"{owner}/{name}", "sha": sha, "key": key, "params": params, "status": "queued", "stage": "queued",
              "pct": 1, "cost": 0.0, "reserved": usd, "created": time.time(), "stages": ["fetch", "structure", "describe", "propose", "analysis"],
              "log": [{"t": 0, "msg": "Queued"}]}
        jobs.save(st)
        jobs.lease(job, 0)
        wait_until(asyncio.to_thread(worker.run, job, 0))
        return JSONResponse({"job": job, "poll": f"/api/jobs/{job}"}, status_code=202)
    except jobs.Refused as e:
        return refuse(e)


@app.get("/api/jobs/{job}")
async def job_state(job: str):
    if not jobs.valid_job_id(job):
        return JSONResponse({"error": "Unknown build."}, status_code=404)
    st = await asyncio.to_thread(jobs.state, job)
    if not st:
        return JSONResponse({"error": "Unknown build."}, status_code=404)
    if worker.stalled(st) and (n := await asyncio.to_thread(worker.resume, st)) is not None:
        # cut off by the time limit or a deploy: carry on from the first unfinished stage, as the job's only runner
        wait_until(asyncio.to_thread(worker.run, job, n))
        st = await asyncio.to_thread(jobs.state, job)
    keep = ("id", "repo", "sha", "key", "status", "stage", "pct", "cost", "log", "snapshot", "snaps", "city", "error",
            "flows_ready", "stages", "created", "updated", "params")
    return JSONResponse({k: st.get(k) for k in keep}, headers={"cache-control": "no-store"})


@app.get("/api/recent")
def recent():
    # newest build per commit: cities/<owner>__<name>__<sha12>__<settings>.json
    newest = {}
    for r in sorted((r for r in store.listing("cities/") if r[0].endswith(".json")), key=lambda r: r[2], reverse=True):
        newest.setdefault(r[0].rsplit("__", 1)[0], r)
    rows = list(newest.values())[:12]
    with ThreadPoolExecutor(6) as ex:
        metas = [m for m in ex.map(lambda r: store.get_json(r[1]), rows) if m]
    return JSONResponse(metas, headers={"cache-control": "public, s-maxage=30"})


@app.get("/api/find")
def find(repo: str = "", sha: str = "", k: str = ""):
    """A finished city from a share link (#r=owner/name@sha&k=<settings hash>): the newest match."""
    try:
        owner, name, _ = jobs.parse_repo(repo)
    except jobs.Refused as e:
        return refuse(e)
    if not re.fullmatch(r"[0-9a-f]{0,40}", sha.lower()) or not re.fullmatch(r"[0-9a-f]{0,8}", k):
        return JSONResponse({"error": "Not a city."}, status_code=404)
    rows = [r for r in store.listing(f"cities/{owner}__{name}__{sha}".lower()) if r[0].endswith(f"__{k}.json" if k else ".json")]
    if not rows:
        return JSONResponse({"error": "That city isn't built yet."}, status_code=404)
    return JSONResponse(store.get_json(max(rows, key=lambda r: r[2])[1]), headers={"cache-control": "public, s-maxage=60"})


@app.get("/api/city")
def city(path: str):
    """Serves a city page on this origin (Blob sends HTML as a sandboxed download, and the app shell needs same-origin
    access to the city). A finished city is rendered from its stored data with the current front end, so every city
    picks up front-end fixes (the CDN cache is per deployment); a build snapshot is served as built. Never other blobs."""
    if m := re.fullmatch(r"cities/([a-z0-9._-]+)\.html", path or ""):
        stored = store.get_json(f"city-data/{m.group(1)}.json")
        page = stored and site.page(stored["data"], fog=stored["fog"]).encode()
        cache = "public, max-age=300, s-maxage=86400"
    elif re.fullmatch(r"jobs/\d{14}-[0-9a-f]{8}/snap/\d{4}\.html", path or "") and (url := store.url_of(path)):
        page, cache = store.get_bytes(url), "public, max-age=300, s-maxage=31536000, immutable"
    else:
        page = None
    if not page:
        return JSONResponse({"error": "Not a city."}, status_code=404)
    return HTMLResponse(page, headers={"cache-control": cache, "content-security-policy": site.csp(page.decode()) + "; frame-ancestors 'self'"})
