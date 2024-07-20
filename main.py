import io
import os
from contextlib import asynccontextmanager

import aiohttp
import discord
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

load_dotenv()

import utils
from bot import Bot
from response import StreamingResponseWithStatusCode


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
    id, legalized_filename = await bot.upload_file(file.file, file.filename, file.size)
    return JSONResponse({"message": "Uploaded successfully.", "id": id, "filename": legalized_filename})


@app.post("/upload/url")
async def route_upload_url(url: str):
    parsed_url = utils.urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        return JSONResponse({"message": "Invalid URL."}, status_code=400)

    async with aiohttp.request("GET", url) as resp:
        if not resp.ok:
            return JSONResponse({"message": "Invalid URL."}, status_code=400)

        data = await resp.read()

    filename = (
        resp.content_disposition.filename
        or resp.url.path.split("/")[-1]
        or f"file{utils.guess_filename(resp.content_type)}"
    )
    id, legalized_filename = await bot.upload_file(io.BytesIO(data), filename, len(data))
    return JSONResponse({"message": "Uploaded successfully.", "id": id, "filename": legalized_filename})


@app.get("/attachments/{id}/{filename}")
async def route_attachments(id: str, filename: str):
    try:
        filename, size, file = await bot.get_file(id, filename)
    except (FileNotFoundError, discord.NotFound):
        return Response("This content is no longer available.", 404, media_type="text/plain")
    except Exception:
        return Response(status_code=500)

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{utils.quote(filename)}",
        "Content-Length": size,
    }
    return StreamingResponseWithStatusCode(file, headers=headers, media_type=utils.guess_mime_type(filename))


@app.get("/view/{id}/{filename}")
async def view_route(request: Request, id: str, filename: str):
    try:
        await bot.check_file(id, filename)
    except (FileNotFoundError, discord.NotFound):
        return Response("This content is no longer available.", 404, media_type="text/plain")
    except Exception:
        return Response(status_code=500)
    return templates.TemplateResponse(request=request, name="view.html")


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
