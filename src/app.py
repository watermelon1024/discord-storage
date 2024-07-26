import json
import os
from contextlib import asynccontextmanager

import aiohttp
import discord
from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.websockets import WebSocketState

from . import utils
from .bot import Bot
from .response import StreamingResponseWithStatusCode
import asyncio
import time
import uuid


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


file_upload_status = {}


@app.websocket("/upload/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            try:
                message = await asyncio.wait_for(ws.receive(), 60)
            except asyncio.TimeoutError:
                await ws.close(1001)
                raise WebSocketDisconnect

            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect
            if message["type"] == "websocket.receive":
                # receive file body here
                if text := message.get("text"):
                    data: dict = json.loads(text)
                    data_type: str = data.get("type")
                    if data_type == "ping":
                        await ws.send_json({"code": 200, "message": "Pong"})
                        continue

                    file_hash: str = data.get("id")
                    if not file_hash:
                        await ws.close(1008)
                        raise WebSocketDisconnect

                    if data_type == "start":
                        filename: str = data.get("filename")
                        total_size: int = data.get("total_size")
                        chunk_size: int = data.get("chunk_size")
                        total_chunks: int = data.get("total_chunks")
                        if not (filename and total_size and chunk_size and total_chunks):
                            await ws.close(1008)
                            raise WebSocketDisconnect
                        status = file_upload_status.get(file_hash)
                        if status is None:
                            status = file_upload_status[file_hash] = {
                                "start": time.time(),
                                "file_id": str(uuid.uuid4()),
                                "filename": filename,
                                "messages": [],
                                "total_size": total_size,
                                "chunk_size": chunk_size,
                                "total_chunks": total_chunks,
                                "current_chunk": 0,
                                "chunk_cache": b"",
                            }
                        await ws.send_json(
                            {
                                "code": 200,
                                "message": "Accept",
                                "id": file_hash,
                                "current_chunk": status["current_chunk"],
                            }
                        )
                    elif data_type == "send_chunk":
                        ...
                    elif data_type == "end":
                        status = file_upload_status.pop(file_hash, None)
                        if status is None:
                            await ws.send_json({"code": 404, "message": "File not found."})
                            continue

                        file_id = status["file_id"]
                        filename = status["filename"]
                        legalized_filename = utils.legalize_filename(filename)
                        await bot.db.add_file(
                            file_id, filename, legalized_filename, status["total_size"], status["messages"]
                        )
                        await ws.send_json(
                            {
                                "code": 200,
                                "message": "Success",
                                "file_id": file_id,
                                "name": legalized_filename,
                            }
                        )
                    else:
                        pass

                elif byte := message.get("bytes"):
                    byte
                else:
                    pass
    except WebSocketDisconnect:
        ws.client_state = WebSocketState.DISCONNECTED


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
