# couchd/core/clients/youtube_chat_stream.py
import asyncio
import logging
from typing import AsyncIterator

import grpc

from couchd.core.clients.youtube_chat import YouTubeChatClient
from couchd.core.clients.proto import stream_list_pb2, stream_list_pb2_grpc
from couchd.core.constants import YouTubeChatConfig

log = logging.getLogger(__name__)

_MESSAGE_TYPE = stream_list_pb2.LiveChatMessageSnippet.TypeWrapper.Type

# The stream is gone for good on these — a retry would only fail the same way.
FATAL_CODES = frozenset({
    grpc.StatusCode.FAILED_PRECONDITION,  # chat disabled or ended
    grpc.StatusCode.NOT_FOUND,            # bad live chat id
})

# Streaming is unavailable to this client; the caller should fall back to polling.
UNSUPPORTED_CODES = frozenset({
    grpc.StatusCode.UNIMPLEMENTED,
    grpc.StatusCode.PERMISSION_DENIED,
})


class StreamEnded(Exception):
    """The live chat itself ended — stop consuming."""


class StreamUnsupported(Exception):
    """streamList is not available to this client — fall back to polling."""


def _event_type(value: int) -> str:
    """TEXT_MESSAGE_EVENT -> textMessageEvent, matching the REST API's casing."""
    head, *rest = _MESSAGE_TYPE.Name(value).lower().split("_")
    return head + "".join(word.capitalize() for word in rest)


def _as_rest_item(message) -> dict:
    """Reshape a proto LiveChatMessage into the REST JSON shape the bot already parses."""
    snippet, author = message.snippet, message.author_details
    return {
        "id": message.id,
        "snippet": {
            "type": _event_type(snippet.type),
            "publishedAt": snippet.published_at,
            "displayMessage": snippet.display_message,
            "textMessageDetails": {
                "messageText": snippet.text_message_details.message_text
            },
        },
        "authorDetails": {
            "channelId": author.channel_id,
            "displayName": author.display_name,
            "isChatModerator": author.is_chat_moderator,
            "isChatOwner": author.is_chat_owner,
        },
    }


class YouTubeChatStream:
    """
    Live chat over liveChatMessages.streamList — one long-lived gRPC stream instead of
    polling liveChatMessages.list every few seconds (5 quota units per call).

    Reconnects resume from next_page_token, so a dropped stream replays nothing already
    seen. Auth reuses the OAuth credentials held by YouTubeChatClient.
    """

    def __init__(self, chat_client: YouTubeChatClient):
        self._chat = chat_client
        self._page_token: str | None = None

    def reset(self) -> None:
        """Drop the resume token — a new broadcast starts its own history."""
        self._page_token = None

    async def messages(self, live_chat_id: str) -> AsyncIterator[dict]:
        """Yield chat messages in REST shape until the chat ends."""
        credentials = grpc.ssl_channel_credentials()
        async with grpc.aio.secure_channel(
            YouTubeChatConfig.GRPC_TARGET, credentials
        ) as channel:
            stub = stream_list_pb2_grpc.V3DataLiveChatMessageServiceStub(channel)
            while True:
                request = stream_list_pb2.LiveChatMessageListRequest(
                    part=list(YouTubeChatConfig.STREAM_PARTS),
                    live_chat_id=live_chat_id,
                    page_token=self._page_token,
                )
                metadata = (("authorization", f"Bearer {await self._chat.access_token()}"),)
                try:
                    async for response in stub.StreamList(request, metadata=metadata):
                        if response.next_page_token:
                            self._page_token = response.next_page_token
                        if response.offline_at:
                            raise StreamEnded(response.offline_at)
                        for item in response.items:
                            yield _as_rest_item(item)
                except grpc.aio.AioRpcError as err:
                    if err.code() in UNSUPPORTED_CODES:
                        raise StreamUnsupported(err.details()) from err
                    if err.code() in FATAL_CODES:
                        raise StreamEnded(err.details()) from err
                    log.warning("Chat stream dropped (%s) — reconnecting.", err.code())
                    await asyncio.sleep(YouTubeChatConfig.STREAM_RETRY_SECONDS)
                    continue
                log.debug("Chat stream closed by server — reopening from page token.")
