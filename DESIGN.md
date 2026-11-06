# Boarding City on Vercel: the web builder

Anyone can paste a public JS/TS GitHub repo, see the time and cost, confirm, and watch the city fill in.

## Shape

```
site/ (static)          the app shell + prebuilt cities; polls the API, swaps in each new snapshot keeping the camera
api/index.py (FastAPI)  POST /api/estimate · POST /api/build (202, fire and forget) · GET /api/jobs/<id>
                        GET /api/recent · GET /api/find (share links) · GET /api/city (serves a built page)
boarding_city/cloud/    worker.py (runs/resumes a build) · stages.py · jobs.py · store.py
Vercel Blob             job state, stage outputs, snapshots, finished cities, spend and rate-limit markers
```

## Why Fluid compute + wait_until, with stage-level resume

- **Background work, not a held request.** `POST /api/build` validates, writes the job, returns 202 in about a
  second, and keeps running the build after the response (`wait_until`). The client polls `GET /api/jobs/<id>`.
- **Resumable and idempotent.** A build is 5 + N stages (fetch, structure, describe, propose, one per walkthrough,
  analysis). Each stage saves its output (`jobs/<id>/art/<stage>.json`) and cost before the next starts; a stage
  whose output exists is skipped (no second AI bill). A stage that throws is retried once; AI calls retry on their own.
- **Time limit.** `api/index.py` has `maxDuration: 800` (Pro). A build cut off by the limit or a deploy stops
  updating; the next poll that finds it idle for 14 minutes (longer than one invocation can live, so the old run is
  certainly gone) resumes it from its first unfinished stage, at most 3 times. Builds longer than 800 s still
  finish, as long as someone is watching.
- **One runner per job.** Each run claims a lease (`jobs/<id>/lease/<n>`, a create-only blob: whoever creates it
  owns the job). A runner checks it still holds the newest lease before every stage, and state snapshots are
  create-only too, so two writers fail loudly instead of overwriting each other.
- **Python all the way.** The CLI and the web builder share `boarding_city/`.
- **Tried first: Vercel Queues, one message per stage** (durability without a watcher). The push consumer
  (`experimentalTriggers` on a Python function) received deliveries on one preview, but on the next preview the
  messages sat undelivered in the consumer group, and the Python subscriber/trigger wiring is beta and thinly
  documented. `worker.run` is the single swap point if Queues (or the Python Workflow SDK) is adopted later.

## Progressive city

`structure` renders the skyline from static analysis in seconds. `describe` runs one fast-model call per district
in parallel and publishes a snapshot as each lands. Every `flow:<k>` stage publishes a snapshot with that walkthrough
playable. `analysis` adds reach, layers, the Daily Commit and the ghost town. Snapshots are immutable
(`jobs/<id>/snap/<n>.html`); the shell swaps the iframe to the newest one, saving and restoring the camera through
`cityAPI.state()` / `cityAPI.setView()`, and waits while a walkthrough or a 2D view is open.

## Storage without races or stale reads

Public blobs are CDN-cached, so nothing is ever overwritten: job state is a numbered series
(`jobs/<id>/state/<seq>.json`, newest wins, found by listing). Counters are folders of empty marker files whose
names carry the value. A day's spend is `spend/<day>/<job>/<ns>-<microdollars>` (newest per job), summed from a listing with no
read-modify-write. Rate limits are `rl/<kind>/<visitor>/<epoch>-<rand>`, ranked over the last hour. Blob serves HTML as a
sandboxed download, so finished pages are served through `GET /api/city`, which only serves `cities/…` and
`jobs/<id>/snap/…`, on the app's own origin. A finished city is stored as data (`city-data/<key>.json`) and rendered with the
current template and injectors each time it's served (the CDN cache is per deployment), so every city ever built
picks up front-end fixes; only in-progress snapshots are stored as pages.

A Redis store (Upstash via the Marketplace) would make the counters atomic; marker files give the same guarantees
here without another service.

## Guards

- **Untrusted repo content.** File names, snippets and summaries come from the mapped repo. Every value put into
  HTML goes through `esc()` (which escapes quotes, so attributes are safe too), and every city page carries a
  Content-Security-Policy that allows only its own inline scripts (by hash) and three.js from the CDN. An unescaped
  value somewhere would still be inert: no inline handlers, `javascript:` URLs or injected scripts run. Built pages
  are served from `/api/city` with the same policy as a header (plus `frame-ancestors 'self'`). A sandboxed iframe
  (opaque origin) was considered and rejected: the shell drives the city through `cityAPI` (keys, flow state,
  keeping the camera across snapshot swaps), and fog, onboarding and the tour keep progress in `localStorage`.

- Only `github.com/<owner>/<repo>` or `owner/repo`. The server fetches from `github.com` (ref advertisement for
  the commit sha) and `codeload.github.com` (the tarball), nothing else.
- Up to `BC_MAX_FILES` source files (1,500 by default). Larger repos are refused with a pointer to the CLI.
- `BC_BUILDS_PER_HOUR` builds and `BC_ESTIMATES_PER_HOUR` estimates per visitor per hour (3 and 20). A visitor
  is a salted hash of the IPv4 address or of the IPv6 /64. The marker is written before counting and the first N
  of the hour pass, so a burst of parallel requests can't slip past the limit.
- `BC_BUILD_CAP_USD` per build ($0.10 by default): the estimate is capped at it, and walkthroughs stop before a build
  would pass it (the analysis still runs). The estimate says so and points to forking the repo to run it with your own key.
- `BC_DAILY_CAP_USD` of AI per day across all builds ($5 by default). A build reserves its high-end estimate before
  it starts (first come, first served, so parallel builds can't all pass), spend is recorded after every AI call
  (a build cut off mid-stage is still counted), and the budget is checked before every AI stage. When the build
  ends, its entry is settled at the real cost.
- The size is checked again at build time (not only in the estimate), and the download is bounded: source files,
  extracted bytes, archive bytes, and a per-file limit; links, absolute and `..` paths are never extracted.
- Each build's working folder is deleted when its run ends.
- Every AI call has a timeout and retries (`BOARDING_TIMEOUT`, `BOARDING_RETRIES`).
- Cache: key = owner, name, commit sha and a hash of the settings. An identical request opens the finished city
  instantly and for free.

## Not in the web builder

- Cranes (git churn) need commit history, which a tarball doesn't carry, so that layer is empty for web builds.
  The CLI keeps it.
- No accounts: limits are per visitor and per day.

## Configuration

| Variable | Default | |
|---|---|---|
| `OPENAI_API_KEY` | none | required for builds; set as a sensitive project variable |
| `BLOB_READ_WRITE_TOKEN` | set by linking the Blob store | |
| `BC_MAX_FILES` / `BC_BUILDS_PER_HOUR` / `BC_ESTIMATES_PER_HOUR` / `BC_DAILY_CAP_USD` / `BC_BUILD_CAP_USD` | 1500 / 3 / 20 / 5 / 0.10 | guards |
| `BC_SALT` | `boarding-city` | salt for visitor hashes; set a private value in production |
| `BOARDING_FAST_MODEL` / `BOARDING_TRACE_MODEL` / `BOARDING_TRACE_EFFORT` | gpt-6-luna / gpt-6.1-terra / low | defaults for the settings panel |
