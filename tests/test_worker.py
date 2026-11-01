from sqlalchemy import select, text, update

from app import worker
from app.db import Session
from app.models import Link, Scan, ScanJob
from app.scanner.pipeline import ScanResult

TARGET = "https://example.com/page"


async def queue(user, target=TARGET):
    async with Session.begin() as session:
        link = Link(slug="abc2345", owner_id=user.id, target_url=target)
        session.add(link)
        await session.flush()
        session.add(ScanJob(link_id=link.id, target_url=target))


async def state():
    async with Session() as session:
        link = await session.scalar(select(Link))
        job = await session.scalar(select(ScanJob))
        scans = list(await session.scalars(select(Scan)))
    return link, job, scans


def scanner_returning(verdict):
    async def scan(url):
        return ScanResult(verdict, ["because"])
    return scan


async def broken_scanner(url):
    raise RuntimeError("feed down")


async def test_empty_queue(user):
    assert await worker.run_once() is False


async def test_each_verdict_sets_the_link_status(user, monkeypatch):
    for verdict, status in worker.LINK_STATUS.items():
        await queue(user)
        monkeypatch.setattr(worker.pipeline, "scan", scanner_returning(verdict))
        assert await worker.run_once() is True
        link, job, scans = await state()
        assert (link.status, job.status) == (status, "done")
        assert (scans[0].verdict, scans[0].reasons, scans[0].target_url) == (verdict, ["because"], TARGET)
        async with Session.begin() as session:
            await session.execute(text("TRUNCATE links, scan_jobs, scans CASCADE"))


async def test_verdict_for_an_old_target_cannot_activate_a_new_one(user, monkeypatch):
    await queue(user)

    async def edited_mid_scan(url):
        async with Session.begin() as session:
            await session.execute(update(Link).values(target_url="https://evil.example/"))
        return ScanResult("allow")

    monkeypatch.setattr(worker.pipeline, "scan", edited_mid_scan)
    await worker.run_once()
    link, job, scans = await state()
    assert (link.status, link.target_url) == ("pending", "https://evil.example/")
    assert job.status == "done"
    assert scans[0].target_url == TARGET


async def test_failure_retries_later_then_goes_to_review(user, monkeypatch):
    await queue(user)
    monkeypatch.setattr(worker.pipeline, "scan", broken_scanner)
    await worker.run_once()
    link, job, _ = await state()
    assert (link.status, job.status, job.attempts) == ("pending", "queued", 1)
    assert await worker.run_once() is False  # the retry isn't due yet

    for _ in range(worker.MAX_ATTEMPTS - 1):
        async with Session.begin() as session:
            await session.execute(update(ScanJob).values(run_after=text("now()")))
        await worker.run_once()
    link, job, scans = await state()
    assert (link.status, job.status) == ("review", "done")
    assert scans[0].reasons == ["scan failed"]


async def test_two_workers_cannot_claim_the_same_job(user):
    await queue(user)
    async with Session.begin() as session:
        await session.execute(text("SELECT 1 FROM scan_jobs FOR UPDATE"))  # another worker mid-claim
        assert await worker.claim() is None


async def test_crashed_workers_job_is_reclaimed(user, monkeypatch):
    await queue(user)
    await worker.claim()  # a worker claims it, then dies
    assert await worker.run_once() is False

    async with Session.begin() as session:
        await session.execute(update(ScanJob).values(locked_at=text("now() - interval '6 minutes'")))
    monkeypatch.setattr(worker.pipeline, "scan", scanner_returning("allow"))
    assert await worker.run_once() is True
    assert (await state())[0].status == "active"


async def test_job_that_keeps_crashing_workers_goes_to_review(user):
    await queue(user)
    async with Session.begin() as session:
        await session.execute(update(ScanJob).values(
            status="running", attempts=worker.MAX_ATTEMPTS, locked_at=text("now() - interval '6 minutes'"),
        ))
    await worker.run_once()
    link, job, _ = await state()
    assert (link.status, job.status) == ("review", "done")
