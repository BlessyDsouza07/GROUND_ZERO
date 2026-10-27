from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Boolean, Float, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now():
    return datetime.now(timezone.utc)

class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300), unique=True)
    base_url: Mapped[str] = mapped_column(String(1000))
    source_type: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_count: Mapped[int] = mapped_column(Integer, default=0)

class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer)
    source_event_key: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(1000))
    description: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    venue: Mapped[str | None] = mapped_column(String(1000))
    address: Mapped[str | None] = mapped_column(String(1500))
    city: Mapped[str | None] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    audience: Mapped[str] = mapped_column(String(100))
    itinerary_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="ACTIVE")
    source_url: Mapped[str] = mapped_column(String(2000))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    raw_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("source_id", "source_event_key", name="uq_source_event"),)

class EventUpdate(Base):
    __tablename__ = "event_updates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(Integer)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    change_type: Mapped[str] = mapped_column(String(50))
    details: Mapped[str | None] = mapped_column(Text)

class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    url: Mapped[str] = mapped_column(String(2000))
    http_status: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64))
    event_count: Mapped[int] = mapped_column(Integer, default=0)
