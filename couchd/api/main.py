# couchd/api/main.py
"""content_os read API entrypoint.

Run as its own process:  ``python -m couchd.api.main``

Binds only when ``API_SECRET`` is set (the feature flag). Built on Starlette so
no web framework is added beyond what ``twitchio[starlette]`` already provides.
"""
import logging

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Route

from couchd.core.config import settings
from couchd.api import routes
from couchd.api.auth import BearerTokenMiddleware
from couchd.api.constants import ApiConfig

log = logging.getLogger(__name__)

_P = ApiConfig.ROUTE_PREFIX

_ROUTES = [
    Route(f"{_P}/health", routes.health, methods=["GET"]),
    Route(f"{_P}/sessions", routes.list_sessions, methods=["GET"]),
    Route(f"{_P}/sessions/active", routes.active_session, methods=["GET"]),
    Route(f"{_P}/sessions/{{session_id}}", routes.session_detail, methods=["GET"]),
    Route(
        f"{_P}/sessions/{{session_id}}/markers",
        routes.session_markers,
        methods=["GET"],
    ),
    Route(
        f"{_P}/sessions/{{session_id}}/recap",
        routes.session_recap,
        methods=["GET"],
    ),
]


def create_app() -> Starlette:
    """Build the ASGI app. Importable by tests without binding a port."""
    return Starlette(
        routes=_ROUTES,
        middleware=[Middleware(BearerTokenMiddleware)],
    )


app = create_app()


def main() -> None:
    if not settings.API_SECRET:
        log.warning(
            "API_SECRET is not set; content_os read API will not start. "
            "Set API_SECRET in .env to enable it."
        )
        return
    log.info("Starting content_os read API on %s:%s", settings.API_HOST, settings.API_PORT)
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)


if __name__ == "__main__":
    main()
