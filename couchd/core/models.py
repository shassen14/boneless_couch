# couchd/core/models.py

from datetime import datetime, timezone
from sqlalchemy import BigInteger, String, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from couchd.core.db import Base


class GuildConfig(Base):
    __tablename__ = "guild_configs"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    welcome_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    role_select_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    stream_updates_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    video_updates_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    video_updates_role_id: Mapped[int] = mapped_column(BigInteger, nullable=True)


class StreamSession(Base):
    __tablename__ = "stream_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=True)

    category: Mapped[str] = mapped_column(String, nullable=True)
    vod_url: Mapped[str] = mapped_column(String, nullable=True)
    peak_viewers: Mapped[int] = mapped_column(Integer, nullable=True)

    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    events: Mapped[list["StreamEvent"]] = relationship(
        "StreamEvent", back_populates="session", cascade="all, delete-orphan"
    )


class StreamEvent(Base):
    __tablename__ = "stream_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("stream_sessions.id"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)

    title: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=True)

    platform_id: Mapped[str] = mapped_column(String, nullable=True)  # e.g., 'two-sum'
    status: Mapped[str] = mapped_column(String, nullable=True)  # e.g., 'solved'
    vod_timestamp: Mapped[str] = mapped_column(
        String, nullable=True
    )  # e.g., '01h25m30s'

    session: Mapped["StreamSession"] = relationship(
        "StreamSession", back_populates="events"
    )
