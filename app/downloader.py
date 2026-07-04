"""
downloader.py
Fetch Trello attachment URLs safely and sort them into spreadsheet / images /
videos by file extension.

Security posture (locked): the attachment URLs arrive from Make, which got them
from a Trello card -- i.e. EXTERNAL, UNTRUSTED input. So:
  - Only fetch from an allowlist of Trello hosts.
  - Cap per-file size and total file count.
  - Stream to disk with a hard byte ceiling (no unbounded reads).
Type sorting itself is by extension (locked decision), applied AFTER download.
"""

from __future__ import annotations
import os
import re
from urllib.parse import urlparse
import requests

ALLOWED_HOSTS = (
    "trello.com",
    "api.trello.com",
    "trello-attachments.s3.amazonaws.com",
)
# trellousercontent.com subdomains are the current CDN for card attachments.
ALLOWED_HOST_SUFFIXES = (
    ".trellousercontent.com",
    ".trello-attachments.s3.amazonaws.com",
)

MAX_FILE_BYTES = 500 * 1024 * 1024   # 500 MB per file (videos can be large)
MAX_FILES = 40
CHUNK = 1024 * 64

SPREADSHEET_EXTS = (".xls", ".xlsx")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".avi", ".webm")

_LEADING_NUM = re.compile(r"^\s*(\d+)")


class DownloadError(Exception):
    pass


def _host_allowed(host: str) -> bool:
    host = (host or "").lower()
    if host in ALLOWED_HOSTS:
        return True
    return any(host.endswith(suf) for suf in ALLOWED_HOST_SUFFIXES)


def _ext(name: str) -> str:
    return os.path.splitext(name)[1].lower()


def _safe_name(url: str, fallback_idx: int) -> str:
    """Derive a filename from the URL path; sanitise to a bare basename."""
    path = urlparse(url).path
    name = os.path.basename(path) or f"file_{fallback_idx}"
    name = name.replace("\\", "_").replace("/", "_")
    return name


def download_all(attachments, dest_dir, *, trello_key=None, trello_token=None,
                 session=None):
    """
    attachments: list of dicts, each {"url": ..., "name": <optional>}.
      `name` (the Trello attachment filename) is preferred for extension
      sorting and video ordering; falls back to the URL basename.
    Returns dict: {"spreadsheet": path|None, "images": [paths], "videos": [paths]}
      - images sorted by leading number then name
      - videos sorted by leading number in filename (locked ordering rule)
    Raises DownloadError on any policy violation or fetch failure.
    """
    if len(attachments) > MAX_FILES:
        raise DownloadError(f"Too many attachments ({len(attachments)} > {MAX_FILES}).")

    sess = session or requests.Session()
    os.makedirs(dest_dir, exist_ok=True)

    spreadsheet = None
    images = []
    videos = []

    for idx, att in enumerate(attachments):
        url = att.get("url", "")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise DownloadError(f"Rejected non-http(s) URL: {url!r}")
        if not _host_allowed(parsed.hostname or ""):
            raise DownloadError(f"Rejected URL from disallowed host: {parsed.hostname!r}")

        name = att.get("name") or _safe_name(url, idx)
        ext = _ext(name)

        if ext in SPREADSHEET_EXTS:
            bucket = "spreadsheet"
        elif ext in IMAGE_EXTS:
            bucket = "images"
        elif ext in VIDEO_EXTS:
            bucket = "videos"
        else:
            # Unknown type: skip rather than fail the whole build.
            continue

        local_path = os.path.join(dest_dir, f"{idx:02d}_{name}")
        _stream_download(sess, url, local_path, trello_key, trello_token)

        if bucket == "spreadsheet":
            # If several spreadsheets somehow present, first one wins.
            if spreadsheet is None:
                spreadsheet = local_path
        elif bucket == "images":
            images.append((name, local_path))
        else:
            videos.append((name, local_path))

    images.sort(key=lambda t: (_leading_num(t[0]), t[0].lower()))
    videos.sort(key=lambda t: (_leading_num(t[0]), t[0].lower()))

    return {
        "spreadsheet": spreadsheet,
        "images": [p for _, p in images],
        "videos": [p for _, p in videos],
    }


def _leading_num(name: str) -> int:
    m = _LEADING_NUM.match(name)
    return int(m.group(1)) if m else 10**9  # unnumbered sorts last


def _stream_download(sess, url, dest, key, token):
    # Trello attachment *downloads* (unlike the REST API) require the credentials
    # in an Authorization header, not as ?key=&token= query params -- query auth
    # returns 401 for private attachment binaries. See Trello API docs on
    # downloading attachments.
    headers = {}
    if key and token:
        headers["Authorization"] = f'OAuth oauth_consumer_key="{key}", oauth_token="{token}"'
    try:
        with sess.get(url, headers=headers or None, stream=True, timeout=60) as r:
            r.raise_for_status()
            clen = r.headers.get("Content-Length")
            if clen and int(clen) > MAX_FILE_BYTES:
                raise DownloadError(f"File exceeds size cap: {url} ({clen} bytes)")
            total = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(CHUNK):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_FILE_BYTES:
                        raise DownloadError(f"File exceeded size cap mid-stream: {url}")
                    f.write(chunk)
    except requests.RequestException as e:
        raise DownloadError(f"Failed to download {url}: {e}") from e
