# streamList protocol buffers

`stream_list.proto` is vendored from Google's
[Streaming Live Chat guide](https://developers.google.com/youtube/v3/live/streaming-live-chat).
It defines `V3DataLiveChatMessageService.StreamList`, the server-streaming RPC that pushes
live chat messages instead of costing 5 quota units per `liveChatMessages.list` poll.

`stream_list_pb2.py` and `stream_list_pb2_grpc.py` are generated and checked in so the bot
runs without a build step. To regenerate after updating the proto:

```bash
cd couchd/core/clients/proto
uv run python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. stream_list.proto
```

Then re-apply the one manual edit: `stream_list_pb2_grpc.py` is generated with a flat
`import stream_list_pb2`, which must become
`from couchd.core.clients.proto import stream_list_pb2 as stream__list__pb2`.
