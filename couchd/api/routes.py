# couchd/api/routes.py
"""Route handlers for the content_os read API. Thin: parse -> query -> JSON."""
import logging
from datetime import datetime

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from couchd.api import queries
from couchd.api.constants import ApiConfig

log = logging.getLogger(__name__)


def _parse_since(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_limit(raw: str | None) -> int:
    if not raw:
        return ApiConfig.DEFAULT_SESSION_LIMIT
    try:
        value = int(raw)
    except ValueError:
        return ApiConfig.DEFAULT_SESSION_LIMIT
    return max(1, min(value, ApiConfig.MAX_SESSION_LIMIT))


def _session_id(request: Request) -> int | None:
    try:
        return int(request.path_params["session_id"])
    except (KeyError, ValueError):
        return None


async def list_sessions(request: Request) -> Response:
    since = _parse_since(request.query_params.get("since"))
    limit = _parse_limit(request.query_params.get("limit"))
    return JSONResponse(await queries.list_sessions(since, limit))


async def active_session(request: Request) -> Response:
    data = await queries.get_active_session()
    if data is None:
        return JSONResponse({"detail": "No active session"}, status_code=404)
    return JSONResponse(data)


async def session_detail(request: Request) -> Response:
    sid = _session_id(request)
    data = await queries.get_session_detail(sid) if sid is not None else None
    if data is None:
        return JSONResponse({"detail": "Session not found"}, status_code=404)
    return JSONResponse(data)


async def session_markers(request: Request) -> Response:
    sid = _session_id(request)
    data = await queries.get_markers(sid) if sid is not None else None
    if data is None:
        return JSONResponse({"detail": "Session not found"}, status_code=404)
    return JSONResponse(data)


async def session_recap(request: Request) -> Response:
    sid = _session_id(request)
    data = await queries.get_recap(sid) if sid is not None else None
    if data is None:
        return JSONResponse({"detail": "Session not found"}, status_code=404)
    return JSONResponse(data)


async def health(request: Request) -> Response:
    return JSONResponse({"status": "ok"})
