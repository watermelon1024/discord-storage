import io
import os
from contextlib import asynccontextmanager

import aiohttp
import discord
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from starlette.types import Send

import utils
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


@app.post("/upload/url")
async def upload_url_route(url: str):
    parsed_url = utils.urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        return Response("Invalid URL.", 400, media_type="text/plain")

    async with aiohttp.request("GET", url) as resp:
        if not 200 <= resp.status < 300:
            return Response("Invalid URL.", 400, media_type="text/plain")

        data = await resp.read()

    filename = parsed_url.path.split("/")[-1] or f"file{utils.guess_filename(resp.content_type)}"
    id = await bot.upload_file(io.BytesIO(data), filename)
    return Response(
        f"File '{filename}' with ID {id} uploaded successfully.", 200, media_type="text/plain"
    )


async def _get_attachment(id: str, filename: str, auto_media_type: bool = True):
    try:
        filename, file = await bot.get_file(id, filename)
    except (FileNotFoundError, discord.NotFound):
        return Response("This content is no longer available.", 410, media_type="text/plain")
    except Exception:
        return HTTPException

    if isinstance(file, str):
        return RedirectResponse(file)
    media_type = (
        utils.guess_media_type(filename) if auto_media_type else "application/octet-stream"
    )
    return StreamingResponseWithStatusCode(file, media_type=media_type)


@app.get("/attachments/{id}/{filename}")
async def attachments_route(id: str, filename: str):
    return await _get_attachment(id, filename, auto_media_type=False)


@app.get("/view/{id}/{filename}")
async def view_route(id: str, filename: str):
    return await _get_attachment(id, filename)


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
