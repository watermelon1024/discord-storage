import json
import os
from contextlib import asynccontextmanager

import aiohttp
import discord
from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
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


@app.post("/upload/file", response_class=HTMLResponse)
async def route_upload_file(file: UploadFile):
    id, legalized_filename = await bot.upload_file(file, file.filename, file.size)
    return JSONResponse({"message": "Uploaded successfully.", "id": id, "filename": legalized_filename})


@app.post("/upload/url")
async def route_upload_url(url: str):
    parsed_url = utils.urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        return JSONResponse({"message": "Invalid URL."}, status_code=400)

    async with aiohttp.request("GET", url) as resp:
        if not resp.ok:
            return JSONResponse({"message": "Invalid URL."}, status_code=400)

        filename = (
            (resp.content_disposition and resp.content_disposition.filename)
            or resp.url.path.split("/")[-1]
            or f"file{utils.guess_filename(resp.content_type)}"
        )
        id, legalized_filename = await bot.upload_file(resp.content, filename)

    return JSONResponse({"message": "Uploaded successfully.", "id": id, "filename": legalized_filename})


@app.websocket("/upload/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        # receive file info
        message = await ws.receive_json()
        # file id is equal to file hash
        file_id: str = message["id"]
        # TODO: get chunk number from cache
        chunk_number = 0
        await ws.send_json({"id": file_id, "chunk": chunk_number})
        received_chunk_number = chunk_number
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect
            if message["type"] == "websocket.receive":
                # receive file body here
                text = message.get("text")
                if text:
                    data: dict = json.loads(text)
                    # TODO: identify heartbeat
                    received_chunk_number = data["chunk"]
                else:
                    chunk: bytes = message["bytes"]
                    # TODO: write chunk data to file
    except WebSocketDisconnect:
        pass


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
