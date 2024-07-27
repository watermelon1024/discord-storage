import mimetypes
import re
from urllib.parse import quote, unquote, urlparse  # noqa: F401

RE_ILLEGAL_FILENAME_CHARS = re.compile(r"[^a-zA-Z0-9\-\.\_]")
RE_REQUEST_RANGE = re.compile(r"bytes=(\d+)-(\d+)?")
RE_FILENAME = re.compile(r"filename\*=UTF-8''(.+)")


def guess_extension(content_type: str):
    extension = mimetypes.guess_extension(content_type)
    return extension or ""


def guess_mime_type(filename: str):
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


def get_filename(conetent_description: str):
    match_ = RE_FILENAME.search(conetent_description)
    if match_ is None:
        return None
    return unquote(match_.group(1))


def legalize_filename(filename: str):
    return RE_ILLEGAL_FILENAME_CHARS.sub("", filename)


def parse_request_range(range_str: str):
    match = RE_REQUEST_RANGE.match(range_str)
    if match:
        start, end = match.groups()
        return start, end
    return None, None


def size_to_str(size: int):
    """
    Give the file size in bytes, convert it to a human-readable value.
    """
    for unit in [" bytes", "KB", "MB", "GB", "TB", "PB"]:
        if size < 1024:
            break
        size /= 1024
    return f"{size:.2f} {unit}"
