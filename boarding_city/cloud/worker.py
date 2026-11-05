"""Runs a build in the background of the request that started it (Fluid compute wait_until; see DESIGN.md).
Every stage saves its output before the next starts, so a build cut off by the function's time limit or a deploy
resumes from its first unfinished stage the next time its progress is polled, instead of starting over."""
import shutil, time, traceback
from . import jobs, stages

STALE = 840  # seconds without progress before a poll resumes a build: longer than one invocation can live (800 s),
             # so the run that went quiet is certainly gone
TRIES = 2    # per stage; each AI call also retries on its own


def next_stage(st):
    return next((s for s in st["stages"] if s not in st.get("costs", {})), None)


def stalled(st):
    return st["status"] in ("queued", "running") and time.time() - st["updated"] > STALE


def run(job, n=0):
    """Run (or resume) a job as its n-th runner, which must hold lease n. It stops if a newer run takes over."""
    st = jobs.state(job)
    stage = None
    try:
        while st["status"] not in ("done", "error"):
            if jobs.leased(job) != n:
                return  # a newer run owns the job now
            stage = next_stage(st)
            if stage is None:
                stages.finish(st)
                return
            for attempt in range(1, TRIES + 1):
                try:
                    st, _ = stages.run(st, stage)
                    break
                except jobs.Refused:
                    raise
                except Exception:
                    if attempt == TRIES:
                        raise
                    traceback.print_exc()
                    st = jobs.state(job)
    except jobs.Refused as e:
        jobs.log(jobs.state(job) or st, str(e), status="error", error=str(e))
    except Exception as e:
        traceback.print_exc()
        msg = f"The build stopped at “{stage}” ({type(e).__name__}). Try again in a minute."
        jobs.log(jobs.state(job) or st, msg, status="error", error=msg)
    finally:
        # settle today's total at what the job really cost (releasing the rest of its reservation), clear its files
        final = jobs.state(job) or st
        if final["status"] in ("done", "error"):
            jobs.record_spend(job, stages.ACTUAL.pop(job, sum(final.get("costs", {}).values())))
        shutil.rmtree(stages.TMP / job, ignore_errors=True)


def resume(st):
    """For a poll that finds the job stalled: claim the next run. -> the run number to start, or None."""
    n = jobs.leased(st["id"]) + 1
    if n > jobs.RESUMES:
        jobs.log(st, "The build kept getting cut off, so it was stopped. Try again in a minute.", status="error",
                 error="The build kept getting cut off, so it was stopped. Try again in a minute.")
        jobs.record_spend(st["id"], sum(st.get("costs", {}).values()))
        return None
    if not jobs.lease(st["id"], n):
        return None  # another poll resumed it first
    jobs.log(st, "Resuming where the build left off")
    return n
