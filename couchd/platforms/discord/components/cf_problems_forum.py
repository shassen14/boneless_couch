# couchd/platforms/discord/components/cf_problems_forum.py
import logging
import discord
from sqlalchemy import select

from couchd.core.db import get_session
from couchd.core.models import CFProblemAttempt, CFProblemPost, StreamEvent
from couchd.core.constants import BrandColors, CFProblemsConfig

log = logging.getLogger(__name__)


async def build_cf_embed(problem_id: str):
    """Build the embed and thread name for a CF problem. Returns (thread_name, embed, attempts)."""
    async with get_session() as db:
        attempts = (
            await db.execute(
                select(CFProblemAttempt)
                .join(StreamEvent)
                .where(CFProblemAttempt.problem_id == problem_id)
                .order_by(StreamEvent.timestamp.asc())
            )
        ).scalars().all()

    if not attempts:
        return None, None, []

    first = attempts[0]
    embed = discord.Embed(title=first.title, url=first.url, color=BrandColors.PRIMARY)
    if first.rating:
        embed.add_field(name="Rating", value=str(first.rating), inline=True)
    if first.tags:
        embed.add_field(name="Tags", value=first.tags, inline=True)

    appearances = "\n".join(
        f"Stream attempt · [{a.vod_timestamp}]({a.url})" for a in attempts
    )
    embed.add_field(
        name=f"Appearances ({len(attempts)})", value=appearances, inline=False
    )

    thread_name = first.title[: CFProblemsConfig.TITLE_MAX_LEN]
    return thread_name, embed, attempts


async def sync_cf_problem(forum: discord.ForumChannel, problem_id: str, bot) -> None:
    async with get_session() as db:
        post = (
            await db.execute(
                select(CFProblemPost).where(CFProblemPost.problem_id == problem_id)
            )
        ).scalar_one_or_none()

    if post:
        await _update_cf_thread(forum, problem_id, post, bot)
    else:
        await _create_cf_thread(forum, problem_id)


async def _create_cf_thread(forum: discord.ForumChannel, problem_id: str) -> None:
    thread_name, embed, _ = await build_cf_embed(problem_id)
    if not embed:
        return

    try:
        thread = await forum.create_thread(
            name=thread_name,
            embed=embed,
            auto_archive_duration=discord.ThreadArchiveDuration.one_week,
        )
        async with get_session() as db:
            db.add(CFProblemPost(problem_id=problem_id, forum_thread_id=thread.id))
            await db.commit()
        log.info("Created CF forum thread for %s (thread_id=%d)", problem_id, thread.id)
    except Exception:
        log.error("Failed to create CF forum thread for %s", problem_id, exc_info=True)


async def _update_cf_thread(
    forum: discord.ForumChannel, problem_id: str, post: CFProblemPost, bot
) -> None:
    thread_name, embed, _ = await build_cf_embed(problem_id)
    if not embed:
        return

    try:
        thread = forum.get_thread(post.forum_thread_id)
        if not thread:
            thread = await bot.fetch_channel(post.forum_thread_id)

        if thread.archived:
            await thread.edit(archived=False)

        starter_msg = await thread.fetch_message(thread.id)
        await starter_msg.edit(embed=embed)
        await thread.edit(name=thread_name)
        log.info("Updated CF forum thread for %s", problem_id)
    except Exception:
        log.error("Failed to update CF forum thread for %s", problem_id, exc_info=True)
