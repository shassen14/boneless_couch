# couchd/api/auth.py
"""Bearer-token auth middleware for the content_os read API.

Single shared secret (``settings.API_SECRET``) between boneless_couch and
content_os — no per-route scoping for an internal two-service API. Every path
except the unauthenticated liveness probe requires a valid token; failures
return 401 and the presented token is never logged.
"""
import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from couchd.core.config import settings
from couchd.api.constants import ApiConfig

log = logging.getLogger(__name__)

_HEALTH_PATH = f"{ApiConfig.ROUTE_PREFIX}/health"


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Reject any request lacking ``Authorization: Bearer <API_SECRET>``."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path == _HEALTH_PATH:
            return await call_next(request)

        header = request.headers.get(ApiConfig.AUTH_HEADER, "")
        scheme, _, token = header.partition(" ")
        if scheme != ApiConfig.AUTH_SCHEME or not token or token != settings.API_SECRET:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)
