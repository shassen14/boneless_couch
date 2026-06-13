# couchd/api/
"""Read-only HTTP API exposing stream session/marker/recap data to content_os.

Runs as its own process (``python -m couchd.api.main``), separate from the bots,
so it fails and restarts independently. Built on Starlette (already a dependency
via ``twitchio[starlette]``) — no new web framework is introduced.
"""
