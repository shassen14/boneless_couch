# tests/unit/platforms/discord/test_cf_problems_cog.py
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord.ext import tasks

from couchd.platforms.discord.cogs.cf_problems import CFProblemsWatcherCog

_COG_PATCH = "couchd.platforms.discord.cogs.cf_problems.get_session"


@pytest.fixture
def cog():
    with patch.object(tasks.Loop, "start"):
        return CFProblemsWatcherCog(MagicMock())


def _make_watermark_db(max_id):
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=max_id))
    )

    @asynccontextmanager
    async def _gs():
        yield db

    return _gs, db


async def test_watermark_seeds_from_max_attempt_id(cog):
    gs, _ = _make_watermark_db(7)
    with patch(_COG_PATCH, gs):
        await cog._seed_watermark()
    assert cog.last_processed_attempt_id == 7


async def test_watermark_defaults_to_zero_on_empty_table(cog):
    gs, _ = _make_watermark_db(None)
    with patch(_COG_PATCH, gs):
        await cog._seed_watermark()
    assert cog.last_processed_attempt_id == 0


async def test_watermark_is_not_reseeded_on_reconnect(cog):
    """on_ready fires again after a reconnect; re-seeding would skip unposted attempts."""
    gs, _ = _make_watermark_db(7)
    with patch(_COG_PATCH, gs):
        await cog._seed_watermark()
    cog.last_processed_attempt_id = 7  # nothing new processed yet

    gs_later, db_later = _make_watermark_db(12)  # attempt 12 logged, not yet posted
    with patch(_COG_PATCH, gs_later):
        await cog._seed_watermark()

    db_later.execute.assert_not_called()
    assert cog.last_processed_attempt_id == 7
