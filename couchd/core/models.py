# couchd/core/models.py

from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
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
    problems_forum_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    clip_showcase_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    ideas_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=True)


class StreamSession(Base):
    __tablename__ = "stream_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=True)
    category: Mapped[str] = mapped_column(String, nullable=True)
    vod_url: Mapped[str] = mapped_column(String, nullable=True)
    peak_viewers: Mapped[int] = mapped_column(Integer, nullable=True)
    discord_notification_message_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
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
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    session: Mapped["StreamSession"] = relationship(
        "StreamSession", back_populates="events"
    )
    problem_attempt: Mapped["ProblemAttempt | None"] = relationship(
        "ProblemAttempt",
        back_populates="event",
        uselist=False,
        cascade="all, delete-orphan",
    )
    project_log: Mapped["ProjectLog | None"] = relationship(
        "ProjectLog",
        back_populates="event",
        uselist=False,
        cascade="all, delete-orphan",
    )
    clip_log: Mapped["ClipLog | None"] = relationship(
        "ClipLog",
        back_populates="event",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ProblemAttempt(Base):
    __tablename__ = "problem_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    stream_event_id: Mapped[int] = mapped_column(
        ForeignKey("stream_events.id"), nullable=False, unique=True
    )
    slug: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=True)
    difficulty: Mapped[str] = mapped_column(String, nullable=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=True)
    vod_timestamp: Mapped[str] = mapped_column(String, nullable=True)

    event: Mapped["StreamEvent"] = relationship(
        "StreamEvent", back_populates="problem_attempt"
    )


class ProjectLog(Base):
    __tablename__ = "project_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    stream_event_id: Mapped[int] = mapped_column(
        ForeignKey("stream_events.id"), nullable=False, unique=True
    )
    url: Mapped[str] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=True)
    vod_timestamp: Mapped[str] = mapped_column(String, nullable=True)

    event: Mapped["StreamEvent"] = relationship(
        "StreamEvent", back_populates="project_log"
    )


class ClipLog(Base):
    __tablename__ = "clip_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    stream_event_id: Mapped[int] = mapped_column(
        ForeignKey("stream_events.id"), nullable=False, unique=True
    )
    clip_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    vod_timestamp: Mapped[str] = mapped_column(String, nullable=True)
    discord_message_id: Mapped[int] = mapped_column(BigInteger, nullable=True)

    event: Mapped["StreamEvent"] = relationship(
        "StreamEvent", back_populates="clip_log"
    )


class ProblemPost(Base):
    __tablename__ = "problem_posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    forum_thread_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class SolutionPost(Base):
    __tablename__ = "solution_posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    problem_slug: Mapped[str] = mapped_column(
        String, nullable=False
    )  # matches ProblemPost.platform_id
    platform: Mapped[str] = mapped_column(
        String, nullable=False
    )  # 'twitch', 'youtube', etc.
    username: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    vod_timestamp: Mapped[str] = mapped_column(String, nullable=True)
    discord_message_id: Mapped[int] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (UniqueConstraint("problem_slug", "platform", "username"),)


class IdeaPost(Base):
    __tablename__ = "idea_posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(String, nullable=False)
    submitted_by: Mapped[str] = mapped_column(String, nullable=False)
    platform: Mapped[str] = mapped_column(String, nullable=False)  # "twitch" | "discord"
    discord_message_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    removed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
