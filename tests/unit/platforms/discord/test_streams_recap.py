# tests/unit/platforms/discord/test_streams_recap.py
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from couchd.core.constants import EventType, TASK_DONE
from couchd.core.models import CFProblemAttempt, ProblemAttempt, ProjectLog, StreamEvent
from couchd.platforms.discord.components import streams_recap as sr

_UTC = timezone.utc
_START = datetime(2024, 1, 1, 12, 0, 0, tzinfo=_UTC)


# ── _duration_str ─────────────────────────────────────────────────────────────

def test_duration_str_hours_and_minutes():
    s = SimpleNamespace(start_time=_START, end_time=_START + timedelta(hours=2, minutes=15))
    assert sr._duration_str(s) == "2h 15m"


def test_duration_str_minutes_only():
    s = SimpleNamespace(start_time=_START, end_time=_START + timedelta(minutes=42))
    assert sr._duration_str(s) == "42m"


def test_duration_str_unknown_without_start():
    s = SimpleNamespace(start_time=None, end_time=None)
    assert sr._duration_str(s) == "Unknown"


def test_duration_str_uses_now_when_no_end():
    s = SimpleNamespace(start_time=datetime.now(_UTC) - timedelta(minutes=30), end_time=None)
    assert sr._duration_str(s) == "30m"


def test_duration_str_naive_start_does_not_crash():
    # Some DB drivers return naive datetimes; mixing with aware now() must not raise.
    naive_start = (datetime.now(_UTC) - timedelta(minutes=20)).replace(tzinfo=None)
    s = SimpleNamespace(start_time=naive_start, end_time=None)
    assert sr._duration_str(s) == "20m"


def test_format_elapsed_naive_inputs():
    assert sr._format_elapsed(
        (_START + timedelta(minutes=3)).replace(tzinfo=None),
        _START.replace(tzinfo=None),
    ) == "3:00"


# ── _format_elapsed ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("delta,expected", [
    (timedelta(seconds=5), "0:05"),
    (timedelta(minutes=3, seconds=7), "3:07"),
    (timedelta(hours=1, minutes=2, seconds=3), "1:02:03"),
    (timedelta(seconds=-50), "0:00"),  # negative clamps to zero
])
def test_format_elapsed(delta, expected):
    assert sr._format_elapsed(_START + delta, _START) == expected


# ── _task_lines ───────────────────────────────────────────────────────────────

def test_task_lines_empty():
    assert sr._task_lines([]) == ""


def test_task_lines_with_and_without_timestamp():
    out = sr._task_lines([("first", "0:30"), ("second", None)])
    assert "→ first `0:30`" in out
    assert "→ second" in out
    assert "second `" not in out  # no stray timestamp


# ── renderers ─────────────────────────────────────────────────────────────────

def _seg(event_type, **kw):
    detail = kw.pop("detail", None)
    return sr._Segment(
        event_type=event_type,
        notes=kw.pop("notes", None),
        detail=detail,
        time_str=kw.pop("time_str", None),
        tasks=kw.pop("tasks", []),
    )


def test_render_lc_full():
    detail = SimpleNamespace(title="Two Sum", url="http://lc/two-sum", difficulty="Easy",
                             rating=1200, vod_timestamp="00h05m00s")
    out = sr._render_lc(_seg(EventType.PROBLEM_ATTEMPT, detail=detail))
    assert out == "- [Two Sum](http://lc/two-sum) · Easy · 1200 · `00h05m00s`"


def test_render_lc_none_detail():
    assert sr._render_lc(_seg(EventType.PROBLEM_ATTEMPT)) == "- Unknown problem"


def test_render_lc_no_url_falls_back_to_time_str():
    detail = SimpleNamespace(title="P", url=None, difficulty=None, rating=None, vod_timestamp=None)
    out = sr._render_lc(_seg(EventType.PROBLEM_ATTEMPT, detail=detail, time_str="1:00"))
    assert out == "- P · `1:00`"


def test_render_cf_with_rating():
    detail = SimpleNamespace(title="Watermelon", url="http://cf/4A", rating=800, vod_timestamp=None)
    out = sr._render_cf(_seg(EventType.CF_PROBLEM, detail=detail, time_str="2:00"))
    assert out == "- [Watermelon](http://cf/4A) · 800 · `2:00`"


def test_render_project_with_tasks():
    detail = SimpleNamespace(title="couchd", url="http://gh/couchd", description="bots")
    out = sr._render_project(_seg(EventType.PROJECT, detail=detail, time_str="0:10",
                                  tasks=[("add tests", "0:20")]))
    assert out.startswith("- [couchd](http://gh/couchd) · bots · `0:10`")
    assert "→ add tests `0:20`" in out


def test_render_simple_dash_when_no_notes():
    assert sr._render_simple(_seg(EventType.GAME)) == "- —"


# ── _add_field truncation ─────────────────────────────────────────────────────

def test_add_field_truncates_long_value():
    import discord
    embed = discord.Embed()
    segs = [_seg(EventType.GAME, notes="x" * 200) for _ in range(20)]
    sr._add_field(embed, "Gaming", segs, sr._render_simple)
    assert len(embed.fields[0].value) == 1024
    assert embed.fields[0].value.endswith("...")


# ── build_stream_embed integration ────────────────────────────────────────────

async def test_build_stream_embed_groups_events_into_fields(
    get_session_fn, db_session, stream_session
):
    # one LeetCode attempt + a project + a task attached to the project
    lc_event = StreamEvent(session_id=stream_session.id, event_type=EventType.PROBLEM_ATTEMPT,
                           timestamp=_START)
    db_session.add(lc_event)
    await db_session.flush()
    db_session.add(ProblemAttempt(stream_event_id=lc_event.id, slug="two-sum", title="Two Sum",
                                  url="http://lc", difficulty="Easy", rating=1200))

    proj_event = StreamEvent(session_id=stream_session.id, event_type=EventType.PROJECT,
                             timestamp=_START + timedelta(minutes=5))
    db_session.add(proj_event)
    await db_session.flush()
    db_session.add(ProjectLog(stream_event_id=proj_event.id, title="couchd", url="http://gh",
                              description=None))

    db_session.add(StreamEvent(session_id=stream_session.id, event_type=EventType.TASK,
                               notes="write tests", timestamp=_START + timedelta(minutes=6)))
    # a 'done' task must not appear
    db_session.add(StreamEvent(session_id=stream_session.id, event_type=EventType.TASK,
                               notes=TASK_DONE, timestamp=_START + timedelta(minutes=7)))
    await db_session.commit()

    with patch("couchd.platforms.discord.components.streams_recap.get_session", get_session_fn):
        embed = await sr.build_stream_embed(stream_session, "Recap")

    names = [f.name for f in embed.fields]
    assert any(n.startswith("LeetCode (1 attempted)") for n in names)
    assert "Projects" in names
    project_field = next(f for f in embed.fields if f.name == "Projects")
    assert "write tests" in project_field.value
    assert TASK_DONE not in project_field.value
