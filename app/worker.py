"""Scan worker: python -m app.worker

Claims a job in a short transaction and scans outside it, so no row lock is held
across network or LLM calls. A worker that dies leaves its job 'running'; the job
is picked up again once locked_at is older than STALE.
"""
import asyncio
import logging
from typing import NamedTuple, Optional

from sqlalchemy import insert, text, update

from .db import Session
from .models import Link, Scan, ScanJob
from .scanner import pipeline

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 30
POLL_SECONDS = 1
LINK_STATUS = {"allow": "active", "review": "review", "block": "blocked"}

CLAIM = text("""
    UPDATE scan_jobs SET status = 'running', locked_at = now(), attempts = attempts + 1
    WHERE id = (
        SELECT id FROM scan_jobs
        WHERE (status = 'queued' AND run_after <= now())
           OR (status = 'running' AND locked_at < now() - interval '5 minutes')
        ORDER BY id
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING id, link_id, target_url, attempts
""")


class Job(NamedTuple):
    id: int
    link_id: int
    target_url: str
    attempts: int


async def claim() -> Optional[Job]:
    async with Session.begin() as session:
        row = (await session.execute(CLAIM)).first()
    return Job(*row) if row else None


async def retry_later(job: Job) -> None:
    async with Session.begin() as session:
        await session.execute(
            text("UPDATE scan_jobs SET status = 'queued', run_after = now() + make_interval(secs => :delay) WHERE id = :id"),
            {"delay": RETRY_DELAY_SECONDS * job.attempts, "id": job.id},
        )


async def finish(job: Job, result: pipeline.ScanResult) -> None:
    async with Session.begin() as session:
        await session.execute(insert(Scan).values(
            link_id=job.link_id, target_url=job.target_url, verdict=result.verdict,
            reasons=result.reasons, signals=result.signals,
        ))
        # The target_url match stops a verdict for an old destination from activating a newer, unscanned one.
        await session.execute(
            update(Link)
            .where(Link.id == job.link_id, Link.target_url == job.target_url, Link.status == "pending")
            .values(status=LINK_STATUS[result.verdict])
        )
        await session.execute(update(ScanJob).where(ScanJob.id == job.id).values(status="done"))


async def run_once() -> bool:
    """Process one job. Returns False when the queue is empty."""
    job = await claim()
    if job is None:
        return False
    failed = pipeline.ScanResult("review", ["scan failed"])
    if job.attempts > MAX_ATTEMPTS:  # earlier attempts died without reporting back
        await finish(job, failed)
        return True
    try:
        result = await pipeline.scan(job.target_url)
    except Exception:
        logger.exception("Scan failed for job %s (attempt %s)", job.id, job.attempts)
        if job.attempts < MAX_ATTEMPTS:
            await retry_later(job)
        else:
            await finish(job, failed)
        return True
    await finish(job, result)
    return True


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            worked = await run_once()
        except Exception:  # e.g. the database restarting; the job is reclaimed once stale
            logger.exception("Worker loop error")
            worked = False
        if not worked:
            await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
