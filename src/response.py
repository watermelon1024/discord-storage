import discord
from fastapi.responses import StreamingResponse
from starlette.types import Send


class StreamingResponseWithStatusCode(StreamingResponse):
    async def stream_response(self, send: Send) -> None:
        try:
            return await super().stream_response(send)
        except (discord.NotFound, FileNotFoundError):
            self.status_code = 410
            await self.complete(send)
        except Exception:
            self.status_code = 500
            await self.complete(send)

    async def complete(self, send: Send) -> None:
        await send({"type": "http.response.body", "body": b"", "more_body": False})
