import io
import mimetypes
import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import aiohttp
import discord
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response, StreamingResponse
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
        except Exception:
            self.status_code = 500
            await self.complete(send)

    async def complete(self, send: Send) -> None:
        await send({"type": "http.response.body", "body": b"", "more_body": False})


@app.exception_handler(404)
async def not_found_handler(request, exc):
    return Response("Content not found.", 404, media_type="text/plain")


@app.exception_handler(405)
async def method_not_allow_handler(request, exc):
    return Response("Method not allowed.", 405, media_type="text/plain")


@app.exception_handler(HTTPException)
async def exception_handler(request, exc):
    return Response("Oops! Something went wrong.", 500, media_type="text/plain")


@app.post("/upload/file")
async def upload_file_route(file: UploadFile = File(...)):
    id = await bot.upload_file(file.file, file.filename)
    return Response(
        f"File '{file.filename}' with ID {id} uploaded successfully.", 200, media_type="text/plain"
    )


def _guess_filename(content_type: str):
    mime_type = mimetypes.guess_extension(content_type)
    return mime_type or ""


@app.post("/upload/url")
async def upload_url_route(url: str):
    parsed_url = urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        return Response("Invalid URL.", 400, media_type="text/plain")

    async with aiohttp.request("GET", url) as resp:
        if not 200 <= resp.status < 300:
            return Response("Invalid URL.", 400, media_type="text/plain")

        data = await resp.read()
        filename = parsed_url.path.split("/")[-1] or f"file{_guess_filename(resp.content_type)}"

    id = await bot.upload_file(io.BytesIO(data), filename)
    return Response(
        f"File '{filename}' with ID {id} uploaded successfully.", 200, media_type="text/plain"
    )


def _guess_media_type(file_name: str):
    mime_type, _ = mimetypes.guess_type(file_name)
    return mime_type or "application/octet-stream"


async def _get_attachment(id: str, file_name: str, auto_media_type=True):
    try:
        file_name, file = await bot.get_file(id, file_name)
    except (FileNotFoundError, discord.NotFound):
        return Response("This content is no longer available.", 410, media_type="text/plain")
    except Exception:
        return HTTPException

    if isinstance(file, str):
        return RedirectResponse(file)
    media_type = _guess_media_type(file_name) if auto_media_type else "application/octet-stream"
    return StreamingResponseWithStatusCode(file, media_type=media_type)


@app.get("/attachments/{id}/{file_name}")
async def attachments_route(id: str, file_name: str):
    return await _get_attachment(id, file_name, auto_media_type=False)


@app.get("/view/{id}/{file_name}")
async def view_route(id: str, file_name: str):
    return await _get_attachment(id, file_name)


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
