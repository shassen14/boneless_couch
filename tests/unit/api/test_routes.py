# tests/unit/api/test_routes.py
"""End-to-end tests of the content_os read API through the ASGI app.

Drives the Starlette app directly via scope/receive/send (no httpx needed), so a
single request exercises auth middleware + routing + the route handler together.
Query results are mocked — the query layer has its own integration tests.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from couchd.api import routes
from couchd.api.main import create_app

_PREFIX = "/api/v1"
_SECRET = "test-secret"
_AUTH = {"Authorization": f"Bearer {_SECRET}"}


async def _call(app, path, headers=None, query=""):
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ],
        "client": ("test", 0),
        "server": ("test", 80),
        "scheme": "http",
        "root_path": "",
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    status = next(
        m["status"] for m in messages if m["type"] == "http.response.start"
    )
    body = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    return status, (json.loads(body) if body else None)


@pytest.fixture
def app(mock_settings):
    with patch.object(mock_settings, "API_SECRET", _SECRET):
        yield create_app()


# ── auth middleware ───────────────────────────────────────────────────────────

async def test_health_needs_no_auth(app):
    status, body = await _call(app, f"{_PREFIX}/health")
    assert status == 200
    assert body == {"status": "ok"}


async def test_missing_auth_header_is_401(app):
    status, body = await _call(app, f"{_PREFIX}/sessions")
    assert status == 401
    assert body == {"detail": "Unauthorized"}


@pytest.mark.parametrize(
    "header",
    [
        {"Authorization": "Bearer wrong-secret"},
        {"Authorization": f"Basic {_SECRET}"},       # wrong scheme
        {"Authorization": "Bearer"},                  # no token
        {"Authorization": _SECRET},                   # no scheme
    ],
)
async def test_bad_auth_is_401(app, header):
    status, _ = await _call(app, f"{_PREFIX}/sessions", headers=header)
    assert status == 401


# ── list_sessions: query-param parsing ────────────────────────────────────────

async def test_list_sessions_passes_parsed_params(app):
    with patch.object(routes.queries, "list_sessions", AsyncMock(return_value=[{"id": 1}])) as q:
        status, body = await _call(
            app, f"{_PREFIX}/sessions", headers=_AUTH, query="since=2026-01-02T00:00:00Z&limit=5"
        )
    assert status == 200
    assert body == [{"id": 1}]
    since, limit = q.await_args.args
    assert since.year == 2026 and since.month == 1 and since.day == 2
    assert limit == 5


async def test_list_sessions_defaults_when_params_absent(app):
    with patch.object(routes.queries, "list_sessions", AsyncMock(return_value=[])) as q:
        await _call(app, f"{_PREFIX}/sessions", headers=_AUTH)
    since, limit = q.await_args.args
    assert since is None
    assert limit == 50  # ApiConfig.DEFAULT_SESSION_LIMIT


async def test_list_sessions_garbage_params_fall_back_to_defaults(app):
    with patch.object(routes.queries, "list_sessions", AsyncMock(return_value=[])) as q:
        await _call(app, f"{_PREFIX}/sessions", headers=_AUTH, query="since=notadate&limit=abc")
    since, limit = q.await_args.args
    assert since is None
    assert limit == 50


async def test_list_sessions_limit_is_clamped(app):
    with patch.object(routes.queries, "list_sessions", AsyncMock(return_value=[])) as q:
        await _call(app, f"{_PREFIX}/sessions", headers=_AUTH, query="limit=99999")
    assert q.await_args.args[1] == 200  # MAX_SESSION_LIMIT


async def test_list_sessions_limit_floor_is_one(app):
    with patch.object(routes.queries, "list_sessions", AsyncMock(return_value=[])) as q:
        await _call(app, f"{_PREFIX}/sessions", headers=_AUTH, query="limit=0")
    assert q.await_args.args[1] == 1


# ── active_session ────────────────────────────────────────────────────────────

async def test_active_session_found(app):
    with patch.object(routes.queries, "get_active_session", AsyncMock(return_value={"id": 7})):
        status, body = await _call(app, f"{_PREFIX}/sessions/active", headers=_AUTH)
    assert status == 200
    assert body == {"id": 7}


async def test_active_session_none_is_404(app):
    with patch.object(routes.queries, "get_active_session", AsyncMock(return_value=None)):
        status, body = await _call(app, f"{_PREFIX}/sessions/active", headers=_AUTH)
    assert status == 404
    assert body == {"detail": "No active session"}


# ── session_detail / markers / recap: path-param + 404 handling ───────────────

async def test_session_detail_found(app):
    with patch.object(routes.queries, "get_session_detail", AsyncMock(return_value={"id": 3})) as q:
        status, body = await _call(app, f"{_PREFIX}/sessions/3", headers=_AUTH)
    assert status == 200
    assert body == {"id": 3}
    assert q.await_args.args == (3,)


async def test_session_detail_not_found_is_404(app):
    with patch.object(routes.queries, "get_session_detail", AsyncMock(return_value=None)):
        status, body = await _call(app, f"{_PREFIX}/sessions/3", headers=_AUTH)
    assert status == 404
    assert body == {"detail": "Session not found"}


async def test_session_detail_non_int_id_short_circuits_to_404(app):
    q = AsyncMock(return_value={"id": 1})
    with patch.object(routes.queries, "get_session_detail", q):
        status, _ = await _call(app, f"{_PREFIX}/sessions/notanint", headers=_AUTH)
    assert status == 404
    q.assert_not_awaited()  # never hit the DB for an unparseable id


async def test_session_markers_found(app):
    with patch.object(routes.queries, "get_markers", AsyncMock(return_value=[{"id": 1}])) as q:
        status, body = await _call(app, f"{_PREFIX}/sessions/9/markers", headers=_AUTH)
    assert status == 200
    assert body == [{"id": 1}]
    assert q.await_args.args == (9,)


async def test_session_markers_unknown_is_404(app):
    with patch.object(routes.queries, "get_markers", AsyncMock(return_value=None)):
        status, _ = await _call(app, f"{_PREFIX}/sessions/9/markers", headers=_AUTH)
    assert status == 404


async def test_session_recap_found(app):
    with patch.object(routes.queries, "get_recap", AsyncMock(return_value={"session_id": 4})) as q:
        status, body = await _call(app, f"{_PREFIX}/sessions/4/recap", headers=_AUTH)
    assert status == 200
    assert body == {"session_id": 4}
    assert q.await_args.args == (4,)


async def test_session_recap_unknown_is_404(app):
    with patch.object(routes.queries, "get_recap", AsyncMock(return_value=None)):
        status, _ = await _call(app, f"{_PREFIX}/sessions/4/recap", headers=_AUTH)
    assert status == 404
