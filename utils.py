import mimetypes
from urllib.parse import urlparse  # noqa: F401


def guess_filename(content_type: str):
    extension = mimetypes.guess_extension(content_type)
    return extension or ""


def guess_media_type(file_name: str):
    mime_type, _ = mimetypes.guess_type(file_name)
    return mime_type or "application/octet-stream"
