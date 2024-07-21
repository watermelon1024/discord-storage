import mimetypes
import re
from urllib.parse import quote, urlparse  # noqa: F401

RE_ILLEGAL_FILENAME_CHARS = re.compile(r"[^a-zA-Z0-9\-\.\_]")
RE_REQUEST_RANGE = re.compile(r"bytes=(\d+)-(\d+)?")


def guess_filename(content_type: str):
    extension = mimetypes.guess_extension(content_type)
    return extension or ""


def guess_mime_type(filename: str):
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


def legalize_filename(filename: str):
    return RE_ILLEGAL_FILENAME_CHARS.sub("", filename)


def parse_request_range(range_str: str):
    match = RE_REQUEST_RANGE.match(range_str)
    if match:
        start, end = match.groups()
        return start, end
    return None, None
