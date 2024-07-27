import os
from contextlib import asynccontextmanager

import aiohttp
import discord
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

from . import utils
from .bot import Bot
from .response import StreamingResponseWithStatusCode


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot
    bot = Bot()
    await bot.run(os.environ.get("TOKEN"))

    yield  # wait until shutdown

    await bot.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory="templates")


@app.exception_handler(404)
async def not_found_handler(request, exc):
    return Response("Content not found.", 404, media_type="text/plain")


@app.exception_handler(405)
async def method_not_allow_handler(request, exc):
    return Response("Method not allowed.", 405, media_type="text/plain")


@app.exception_handler(HTTPException)
async def exception_handler(request, exc):
    return Response("Oops! Something went wrong.", 500, media_type="text/plain")


@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse(request=request, name="upload.html")


@app.post("/upload/file")
async def route_upload_file(request: Request):
    print(request.headers)
    filename = (
        utils.get_filename(request.headers.get("content-disposition", ""))
        or f"file.{utils.guess_extension(request.headers.get('content-type', ''))}"
    )
    id, legalized_filename = await bot.upload_file(request.stream(), filename)
    return JSONResponse({"message": "Uploaded successfully.", "id": id, "filename": legalized_filename})


@app.post("/upload/url")
async def route_upload_url(request: Request, url: str):
    parsed_url = utils.urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        return JSONResponse({"message": "Invalid URL."}, status_code=400)

    async with aiohttp.request("GET", url) as resp:
        if not resp.ok:
            return JSONResponse({"message": "Invalid URL."}, status_code=400)

        filename = (
            (resp.content_disposition and resp.content_disposition.filename)
            or resp.url.path.split("/")[-1]
            or f"file{utils.guess_extension(resp.content_type)}"
        )
        id, legalized_filename = await bot.upload_file(
            resp.content.iter_chunked(bot.DEFAULT_MAX_SIZE), filename
        )

    return JSONResponse({"message": "Uploaded successfully.", "id": id, "filename": legalized_filename})


@app.get("/attachments/{id}/{filename}")
async def route_attachments(request: Request, id: str, filename: str):
    # get range
    _range = request.headers.get("Range")
    if _range:
        start, end = utils.parse_request_range(_range)
        if end is not None:
            interval = int(end) - int(start) + 1
        else:
            interval = None
    else:
        start, end, interval = 0, None, None
    # fetch data
    try:
        filename, size, file = await bot.get_file(id, filename, start, interval)
    except (FileNotFoundError, discord.NotFound):
        return Response("This content is no longer available.", 404, media_type="text/plain")
    except Exception:
        return Response(status_code=500)

    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{utils.quote(filename)}"}
    if _range:
        headers["Content-Length"] = size
        headers["Content-Range"] = f"bytes {start}-{end or (int(size) - 1)}/{size}"

    return StreamingResponseWithStatusCode(file, headers=headers, media_type=utils.guess_mime_type(filename))


@app.get("/view/{id}/{filename}")
async def view_route(request: Request, id: str, filename: str):
    try:
        real_filename, legalized_filename, size, message_ids = await bot.check_file(id, filename)
    except FileNotFoundError:
        return Response("This content is no longer available.", 404, media_type="text/plain")

    return templates.TemplateResponse(
        request=request,
        name="view.html",
        context={"real_filename": real_filename, "file_size": utils.size_to_str(int(size))},
    )
