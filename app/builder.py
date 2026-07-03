"""
builder.py
The end-to-end build pipeline, independent of Flask so it can be unit-tested.

build_product_page(payload, publisher, sirv, workdir) -> result dict

Steps:
  1. Download & sort attachments (secure).            [downloader]
  2. Parse the spreadsheet -> spec (hard-fail if bad). [spec_parser]
  3. Concat videos -> Sirv -> video URL (if any).      [video + sirv]
  4. Resolve a collision-free slug; derive paths.      [naming]
  5. Render the .php page.                              [renderer]
  6. Publish images (1.jpg..N.jpg) + the .php file.     [publisher]
Returns the published URL, slug, filename, and counts.
"""

from __future__ import annotations
import os
import tempfile

from .downloader import download_all, DownloadError
from .spec_parser import parse_spec, SpecParseError
from .video import concat_videos, VideoError
from .naming import build_title, build_heading, resolve_slug, derive_paths, base_slug
from .renderer import render_page


class BuildError(Exception):
    def __init__(self, message, stage=None):
        super().__init__(message)
        self.stage = stage


def _page_rel(filename):
    """Canonical publish path for the .php page (single source of truth)."""
    return f"demo-used-equipment/{filename}"


def _image_ext(path):
    e = os.path.splitext(path)[1].lower()
    return ".jpg" if e in (".jpeg", ".jpg") else e


def build_product_page(payload, *, publisher, sirv_publisher=None,
                       sirv_public_base="https://blueprint.sirv.com",
                       product_group_dir_map=None, workdir=None, publish=True):
    """
    payload: {
       "card_name": str (optional; used only for logging/fallback),
       "attachments": [ {"url":..., "name":...}, ... ],
       "trello_key": str (optional), "trello_token": str (optional),
       "product_group_dir": str (optional override of media sub-folder),
    }
    publisher:       FTP/SFTP publisher for the web server (page + images).
    sirv_publisher:  FTP publisher pointed at ftp.sirv.com for the video, or
                     None to skip video upload (video still concatenated).
    sirv_public_base: public URL base for Sirv (default https://blueprint.sirv.com).
    """
    attachments = payload.get("attachments") or []
    if not attachments:
        raise BuildError("No attachments provided.", stage="input")

    tmp = workdir or tempfile.mkdtemp(prefix="cpb_")
    dl_dir = os.path.join(tmp, "downloads")

    # 1. Download & sort ------------------------------------------------------
    try:
        sorted_files = download_all(
            attachments, dl_dir,
            trello_key=payload.get("trello_key"),
            trello_token=payload.get("trello_token"),
        )
    except DownloadError as e:
        raise BuildError(str(e), stage="download") from e

    if not sorted_files["spreadsheet"]:
        raise BuildError("No spreadsheet (.xls/.xlsx) attachment found.", stage="download")

    # 2. Parse spec (hard fail) ----------------------------------------------
    try:
        spec = parse_spec(sorted_files["spreadsheet"])
    except SpecParseError as e:
        raise BuildError(str(e), stage="parse") from e

    # 3. Video -> Sirv (via FTP) ---------------------------------------------
    # Sirv is reached as a plain FTP target (ftp.sirv.com). The builder uploads
    # the concatenated clip into /atlas-polar and derives the public URL
    # deterministically ( https://<sirv_account>.sirv.com/atlas-polar/<file> ).
    sirv_url = ""
    videos = sorted_files["videos"]
    if videos:
        joined = os.path.join(tmp, "joined.mp4")
        try:
            concat_videos(videos, joined)
        except VideoError as e:
            raise BuildError(str(e), stage="video") from e
        if sirv_publisher is not None:
            video_name = f"{base_slug(spec)}.mp4"
            sirv_rel = f"atlas-polar/{video_name}"
            try:
                sirv_publisher.put_file(joined, sirv_rel)
            except Exception as e:  # noqa: BLE001
                raise BuildError(f"Sirv FTP upload failed: {e}", stage="sirv") from e
            sirv_url = f"{sirv_public_base.rstrip('/')}/atlas-polar/{video_name}"

    # 4. Slug + paths ---------------------------------------------------------
    pg_dir = payload.get("product_group_dir")
    if not pg_dir and product_group_dir_map:
        pg_dir = product_group_dir_map.get(spec["logo_key"], spec["logo_key"] or "equipment")
    pg_dir = pg_dir or (spec["logo_key"] or "equipment")

    slug = resolve_slug(spec, lambda s: publisher.exists(
        _page_rel(derive_paths(s, pg_dir)['filename'])
    ))
    paths = derive_paths(slug, pg_dir)
    title = build_title(spec)
    heading = build_heading(spec)

    # 5. Render ---------------------------------------------------------------
    image_names = [f"{i}{_image_ext(p)}" for i, p in enumerate(sorted_files["images"], 1)]
    page = render_page(
        spec,
        title=title,
        heading=heading,
        menu_url=paths["menu_url"],
        media_path=paths["media_path"],
        sirv_video_url=sirv_url,
        image_names=image_names,
    )

    # 6. Publish --------------------------------------------------------------
    published = []
    if publish:
        # images into the media_path folder
        for local, name in zip(sorted_files["images"], image_names):
            rel = os.path.join(paths["media_path"], name)
            publisher.put_file(local, rel)
            published.append(rel)
        # the php page at the web root demo-used-equipment folder
        page_rel = _page_rel(paths['filename'])
        publisher.put_bytes(page, page_rel)
        published.append(page_rel)

    return {
        "ok": True,
        "slug": slug,
        "title": title,
        "filename": paths["filename"],
        "menu_url": paths["menu_url"],
        "media_path": paths["media_path"],
        "video_url": sirv_url,
        "image_count": len(image_names),
        "video_count": len(videos),
        "published": published,
        "page_html": page,  # returned for inspection; Make can ignore
    }
