"""Bounded benchmark workers, with one reusable session/client per worker and app.

Apps run in sequence so no more than eight sessions are live across the whole run.
Each worker saves completed episodes before attempting the next one.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event

from specx.client import SandboxClient
from specx.evalx.agent import run_episode
from specx.evalx.benchmark_store import TrialJob, TrialStore
from specx.evalx.llm import AgentLLM


def check_sandbox(client_factory: Callable[[], SandboxClient], apps: list[str]) -> None:
    with client_factory() as client:
        health = client.health()
        if health.get("ok") is not True:
            raise RuntimeError("Sandbox health check failed")
        missing = set(apps) - set(health.get("apps", []))
        if missing:
            raise RuntimeError(f"Sandbox is missing apps: {sorted(missing)}")


def execute_jobs(
    jobs: list[TrialJob],
    *,
    workers: int,
    max_steps: int,
    llm: AgentLLM,
    store: TrialStore,
    client_factory: Callable[[], SandboxClient],
) -> None:
    stopped = Event()

    def worker(shard: list[TrialJob]) -> None:
        with client_factory() as client:
            session_id = client.create_session(shard[0].task.app, seed=shard[0].seed)
            try:
                for job in shard:
                    if stopped.is_set():
                        return
                    trial, trace = run_episode(
                        client,
                        job.task.app,
                        job.task,
                        job.condition,
                        job.seed,
                        tools=job.tools,
                        contracts=job.contracts,
                        llm=llm,
                        max_steps=max_steps,
                        session_id=session_id,
                        trial_id=job.trial_id,
                    )
                    store.save(job, trial, trace, llm.model, max_steps)
            except BaseException:
                stopped.set()
                raise
            finally:
                client.close(session_id)

    for app in sorted({job.task.app for job in jobs}):
        app_jobs = [job for job in jobs if job.task.app == app]
        count = min(workers, len(app_jobs))
        with ThreadPoolExecutor(max_workers=count) as executor:
            futures = [executor.submit(worker, app_jobs[index::count]) for index in range(count)]
            for future in as_completed(futures):
                future.result()
