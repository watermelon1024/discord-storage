import mimetypes
import os
from contextlib import asynccontextmanager

import discord
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from starlette.types import Send

from bot import Bot

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot
    bot = Bot()
    await bot.run(os.environ.get("TOKEN"))

    yield  # wait until shutdown

    await bot.close()


app = FastAPI(lifespan=lifespan)


class StreamingResponseWithStatusCode(StreamingResponse):
    async def stream_response(self, send: Send) -> None:
        try:
            return await super().stream_response(send)
        except discord.NotFound:
            self.status_code = 410
            await self.complete(send)
        except Exception as e:
            print(e)
            self.status_code = 500
            await self.complete(send)

    async def complete(self, send: Send) -> None:
        await send({"type": "http.response.body", "body": b"", "more_body": False})


@app.exception_handler(404)
async def not_found_handler(request, exc):
    return Response("This content is no longer available.", 404, media_type="text/plain")


@app.exception_handler(HTTPException)
async def exception_handler(request, exc):
    return Response("Oops! Something went wrong.", 500, media_type="text/plain")


@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    id = await bot.upload_file(file.file, file.filename)
    return Response(
        f"File '{file.filename}' with ID {id} uploaded successfully.", 200, media_type="text/plain"
    )


def get_media_type(file_name: str):
    mime_type, _ = mimetypes.guess_type(file_name)
    return mime_type or "application/octet-stream"


@app.get("/download/{id}/{file_name}")
async def download_file(id: str, file_name: str):
    try:
        file_name, file = await bot.get_file(id, file_name)
    except FileNotFoundError:
        return Response("Content not found.", 404, media_type="text/plain")
    except discord.NotFound:
        return Response("This content is no longer available.", 410, media_type="text/plain")

    return StreamingResponseWithStatusCode(file, media_type="application/octet-stream")


if __name__ == "__main__":
    import uvicorn

    try:
        uvicorn.run(
            app,
            host=os.getenv("SERVER_HOST") or "127.0.0.1",
            port=int(os.getenv("SERVER_PORT") or 8000),
        )
    except KeyboardInterrupt:
        pass
