# couchd/platforms/discord/components/problems_forum.py
import logging
import discord
from sqlalchemy import select, func

from couchd.core.db import get_session
from couchd.core.models import ProblemPost, ProblemAttempt, SolutionPost, StreamEvent
from couchd.core.constants import BrandColors, ProblemsConfig

log = logging.getLogger(__name__)


async def build_problem_embed(slug: str):
    async with get_session() as db:
        attempts = (
            (
                await db.execute(
                    select(ProblemAttempt)
                    .join(StreamEvent)
                    .where(ProblemAttempt.slug == slug)
                    .order_by(StreamEvent.timestamp.asc())
                )
            )
            .scalars()
            .all()
        )

    if not attempts:
        return None, None, []

    first = attempts[0]
    embed = discord.Embed(
        title=first.title,
        url=first.url,
        color=BrandColors.PRIMARY,
    )
    embed.add_field(name="Difficulty", value=first.difficulty or "Unknown", inline=True)
    if first.rating:
        embed.add_field(name="Rating", value=str(first.rating), inline=True)

    appearances = "\n".join(
        f"Stream attempt · [{a.vod_timestamp}]({a.url})" for a in attempts
    )
    embed.add_field(
        name=f"Appearances ({len(attempts)})", value=appearances, inline=False
    )

    async with get_session() as db:
        sol_count = (
            await db.execute(
                select(func.count()).where(SolutionPost.problem_slug == slug)
            )
        ).scalar_one()

    if sol_count == 0:
        embed.add_field(
            name="Status", value="Attempted — no solution linked yet", inline=False
        )

    thread_name = first.title[: ProblemsConfig.TITLE_MAX_LEN]
    return thread_name, embed, attempts


def resolve_tags(forum: discord.ForumChannel, difficulty: str | None):
    if not difficulty:
        return []
    return [t for t in forum.available_tags if t.name == difficulty]


async def create_problem_thread(forum: discord.ForumChannel, slug: str):
    thread_name, embed, attempts = await build_problem_embed(slug)
    if not embed:
        return None, None

    tags = resolve_tags(forum, attempts[0].difficulty if attempts else None)
    try:
        thread = await forum.create_thread(
            name=thread_name,
            embed=embed,
            applied_tags=tags,
            auto_archive_duration=discord.ThreadArchiveDuration.one_week,
        )
        async with get_session() as db:
            post = ProblemPost(platform_id=slug, forum_thread_id=thread.id)
            db.add(post)
            await db.commit()
            await db.refresh(post)
        log.info("Created forum thread for %s (thread_id=%d)", slug, thread.id)
        return thread, post
    except Exception:
        log.error("Failed to create forum thread for %s", slug, exc_info=True)
        return None, None


async def update_problem_thread(
    forum: discord.ForumChannel, slug: str, post: ProblemPost, bot
):
    thread_name, embed, attempts = await build_problem_embed(slug)
    if not embed:
        return None

    tags = resolve_tags(forum, attempts[0].difficulty if attempts else None)
    try:
        thread = forum.get_thread(post.forum_thread_id)
        if not thread:
            thread = await bot.fetch_channel(post.forum_thread_id)

        if thread.archived:
            await thread.edit(archived=False)

        starter_msg = await thread.fetch_message(thread.id)
        await starter_msg.edit(embed=embed)
        await thread.edit(applied_tags=tags, name=thread_name)
        log.info("Updated forum thread for %s", slug)
        return thread
    except Exception:
        log.error("Failed to update forum thread for %s", slug, exc_info=True)
        return None


async def sync_problem(forum: discord.ForumChannel, slug: str, bot):
    async with get_session() as db:
        post = (
            await db.execute(
                select(ProblemPost).where(ProblemPost.platform_id == slug)
            )
        ).scalar_one_or_none()

    if post:
        thread = await update_problem_thread(forum, slug, post, bot)
    else:
        thread, post = await create_problem_thread(forum, slug)

    if thread and post:
        await sync_solution_comments(thread, slug)


async def sync_solution_comments(thread: discord.Thread, slug: str):
    async with get_session() as db:
        rows = (
            (
                await db.execute(
                    select(SolutionPost).where(SolutionPost.problem_slug == slug)
                )
            )
            .scalars()
            .all()
        )

    for sol in rows:
        content = (
            f"**{sol.username}** solved this (via {sol.platform})!\n"
            f"[View Submission]({sol.url})"
        )
        if sol.discord_message_id:
            try:
                msg = await thread.fetch_message(sol.discord_message_id)
                await msg.edit(content=content)
                continue
            except discord.NotFound:
                pass  # message deleted — fall through to post new

        msg = await thread.send(content)
        async with get_session() as db:
            row = await db.get(SolutionPost, sol.id)
            row.discord_message_id = msg.id
            await db.commit()


async def flush_pending_solutions(forum: discord.ForumChannel, bot):
    async with get_session() as db:
        slugs = (
            (
                await db.execute(
                    select(SolutionPost.problem_slug)
                    .distinct()
                    .where(SolutionPost.discord_message_id.is_(None))
                )
            )
            .scalars()
            .all()
        )

    for slug in slugs:
        async with get_session() as db:
            post = (
                await db.execute(
                    select(ProblemPost).where(ProblemPost.platform_id == slug)
                )
            ).scalar_one_or_none()
        if not post:
            continue
        thread = forum.get_thread(post.forum_thread_id)
        if not thread:
            try:
                thread = await bot.fetch_channel(post.forum_thread_id)
            except Exception:
                log.warning("Could not fetch thread for slug %s", slug)
                continue
        await sync_solution_comments(thread, slug)
