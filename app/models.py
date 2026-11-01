import datetime as dt
from typing import Any, Optional

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def primary_key() -> Mapped[int]:
    return mapped_column(BigInteger, primary_key=True, autoincrement=True)


def created_at() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = primary_key()
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[dt.datetime] = created_at()


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'active', 'review', 'blocked', 'disabled')", name="links_status"),
        Index("ix_links_owner_id", "owner_id", "id"),
    )

    id: Mapped[int] = primary_key()
    slug: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    created_at: Mapped[dt.datetime] = created_at()
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ScanJob(Base):
    __tablename__ = "scan_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done')", name="scan_jobs_status"),
        Index("ix_scan_jobs_open", "id", postgresql_where=text("status <> 'done'")),
    )

    id: Mapped[int] = primary_key()
    link_id: Mapped[int] = mapped_column(ForeignKey("links.id"), nullable=False)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)  # what to scan, fixed when the job is queued
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    run_after: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    locked_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = created_at()


class Scan(Base):
    __tablename__ = "scans"
    __table_args__ = (
        CheckConstraint("verdict IN ('allow', 'review', 'block')", name="scans_verdict"),
        Index("ix_scans_link_id", "link_id", "id"),
    )

    id: Mapped[int] = primary_key()
    link_id: Mapped[int] = mapped_column(ForeignKey("links.id"), nullable=False)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    signals: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    model: Mapped[Optional[str]] = mapped_column(String(100))
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = created_at()
