import mimetypes
from urllib.parse import quote, urlparse  # noqa: F401
import re

RE_ILLEGAL_FILENAME_CHARS = re.compile(r"[^a-zA-Z0-9\-\.\_]")


def guess_filename(content_type: str):
    extension = mimetypes.guess_extension(content_type)
    return extension or ""


def guess_media_type(file_name: str):
    mime_type, _ = mimetypes.guess_type(file_name)
    return mime_type or "application/octet-stream"


def legalize_filename(filename: str):
    return RE_ILLEGAL_FILENAME_CHARS.sub("", filename)
