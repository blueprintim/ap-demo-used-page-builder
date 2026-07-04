"""
server.py
Flask app exposing POST /build_product_page.

This is written so it can either run standalone (python -m app.server) or have
its blueprint registered inside the existing crane_render app:

    from app.server import bp as build_product_page_bp
    existing_app.register_blueprint(build_product_page_bp)

Auth: a shared secret in the X-Build-Token header (env BUILD_API_TOKEN), so only
your Make scenario can invoke it. Publishing to the live server only happens when
the request is authenticated AND payload publish is not explicitly false.
"""

from __future__ import annotations
import os
from flask import Flask, Blueprint, request, jsonify

from .builder import build_product_page, BuildError
from .publisher import SFTPPublisher, FTPPublisher, LocalMockPublisher, PublishError

bp = Blueprint("build_product_page", __name__)

# Where per-job uploaded pieces are stored between /upload_piece and /build.
JOBS_ROOT = os.environ.get("JOBS_ROOT", "/tmp/cpb_jobs")

# Map logo_key -> media sub-folder used in media_path. Adjust to your taxonomy.
PRODUCT_GROUP_DIR_MAP = {
    "hiab": "hiab-boom-trucks",
    "moffett": "moffett-forklifts",
    "palfinger": "palfinger",
    "multilift": "multilift-hooklifts",
}


def _safe_job_id(job_id):
    """Sanitise a job id to a safe folder name."""
    import re
    jid = re.sub(r"[^A-Za-z0-9_-]", "", str(job_id or ""))
    return jid[:64]


def _job_dir(job_id):
    jid = _safe_job_id(job_id)
    if not jid:
        return None
    d = os.path.join(JOBS_ROOT, jid, "uploads")
    os.makedirs(d, exist_ok=True)
    return d


def _check_auth(req):
    expected = os.environ.get("BUILD_API_TOKEN")
    if not expected:
        return True  # no token configured -> allow (dev). Set one in prod.
    return req.headers.get("X-Build-Token") == expected


def _make_publisher():
    """Web-server publisher. Prefer SFTP, then plain FTP (WEB_FTP_*), else mock."""
    if os.environ.get("SFTP_HOST"):
        return SFTPPublisher(), False
    if os.environ.get("WEB_FTP_HOST"):
        return FTPPublisher(env_prefix="WEB_FTP"), False
    mock_root = os.environ.get("MOCK_PUBLISH_DIR", "/tmp/cpb_publish")
    return LocalMockPublisher(mock_root), True


def _make_sirv_publisher():
    """FTP publisher pointed at Sirv (ftp.sirv.com). None if not configured."""
    if os.environ.get("SIRV_FTP_HOST"):
        try:
            return FTPPublisher(env_prefix="SIRV_FTP")
        except PublishError:
            return None
    return None


@bp.route("/", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "crane-page-builder"})


@bp.route("/upload_piece", methods=["POST"])
def upload_piece():
    """
    Phase 1 of the two-phase flow. Save ONE uploaded file into a job folder
    keyed by job_id (the Trello card id). Called once per attachment by Make.
    multipart form: job_id (text), file (file). Optional reset=true to clear
    the job folder first (use on the first piece).
    """
    if not _check_auth(request):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    job_id = request.form.get("job_id")
    d = _job_dir(job_id)
    if not d:
        return jsonify({"ok": False, "error": "missing or invalid job_id"}), 400

    if _as_bool(request.form.get("reset", "false")):
        # Clear any previous pieces for a fresh build.
        import shutil
        parent = os.path.dirname(d)
        shutil.rmtree(parent, ignore_errors=True)
        d = _job_dir(job_id)

    f = (request.files.get("file")
         or (request.files.getlist("files") or [None])[0])
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "no file provided"}), 400

    name = os.path.basename(f.filename)
    f.save(os.path.join(d, name))
    count = len([n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n))])
    return jsonify({"ok": True, "job_id": _safe_job_id(job_id),
                    "saved": name, "pieces": count}), 200


@bp.route("/build_product_page", methods=["POST"])
def build_endpoint():
    if not _check_auth(request):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    publisher, is_mock = _make_publisher()
    sirv_publisher = _make_sirv_publisher()
    sirv_base = os.environ.get("SIRV_PUBLIC_BASE", "https://blueprint.sirv.com")

    # Phase-2 job build: job_id may arrive as a multipart/form field, a query
    # arg, or in a JSON body. Check all three.
    _jb = request.get_json(silent=True) or {}
    job_id = (request.form.get("job_id")
              or request.args.get("job_id")
              or _jb.get("job_id"))

    # Intake modes:
    #  (0) job_id -> build from previously uploaded pieces
    #  (a) multipart/form-data with uploaded files (or a single zip)
    #  (b) JSON body with a "files" array of {fileName, data(base64)}
    #  (c) JSON body with attachment URLs (endpoint downloads them itself)
    uploaded = request.files.getlist("files") or list(request.files.values())
    json_body = None if uploaded else _jb

    try:
        if job_id and not uploaded:
            d = _job_dir(job_id)
            src = request.form if request.form else (json_body or {})
            local = [(n, os.path.join(d, n)) for n in sorted(os.listdir(d))
                     if os.path.isfile(os.path.join(d, n))]
            if not local:
                return jsonify({"ok": False, "stage": "input",
                                "error": f"no uploaded pieces for job {_safe_job_id(job_id)}"}), 422
            payload = {
                "publish": _as_bool(src.get("publish", True)),
                "product_group_dir": src.get("product_group_dir"),
                "card_name": src.get("card_name"),
                "local_files": local,
            }
            publish = payload["publish"]
            workdir = os.path.dirname(d)
            result = build_product_page(
                payload, publisher=publisher, sirv_publisher=sirv_publisher,
                sirv_public_base=sirv_base, product_group_dir_map=PRODUCT_GROUP_DIR_MAP,
                publish=publish, workdir=workdir,
            )
            # Clean up the job folder after a successful build.
            import shutil
            shutil.rmtree(workdir, ignore_errors=True)
        elif uploaded:
            import tempfile
            workdir = tempfile.mkdtemp(prefix="cpb_up_")
            # If a single zip was uploaded, extract it; else save files as-is.
            if len(uploaded) == 1 and (uploaded[0].filename or "").lower().endswith(".zip"):
                saved = _extract_zip(uploaded[0], workdir)
            else:
                saved = _save_uploads(uploaded, workdir)
            form = request.form
            payload = {
                "publish": _as_bool(form.get("publish", "true")),
                "product_group_dir": form.get("product_group_dir"),
                "card_name": form.get("card_name"),
                "local_files": saved,  # builder uses these instead of downloading
            }
            publish = payload["publish"]
            result = build_product_page(
                payload,
                publisher=publisher,
                sirv_publisher=sirv_publisher,
                sirv_public_base=sirv_base,
                product_group_dir_map=PRODUCT_GROUP_DIR_MAP,
                publish=publish,
                workdir=workdir,
            )
        else:
            payload = json_body or {}
            publish = payload.get("publish", True)
            # Mode (b): JSON "files" array of {fileName, data} where data is
            # base64 (or a Make IMTBuffer hex string). Decode to local files.
            files_arr = payload.get("files")
            if files_arr:
                import tempfile
                workdir = tempfile.mkdtemp(prefix="cpb_js_")
                saved = _decode_files(files_arr, workdir)
                payload = {
                    "publish": _as_bool(payload.get("publish", True)),
                    "product_group_dir": payload.get("product_group_dir"),
                    "card_name": payload.get("card_name"),
                    "local_files": saved,
                }
                publish = payload["publish"]
                result = build_product_page(
                    payload,
                    publisher=publisher,
                    sirv_publisher=sirv_publisher,
                    sirv_public_base=sirv_base,
                    product_group_dir_map=PRODUCT_GROUP_DIR_MAP,
                    publish=publish,
                    workdir=workdir,
                )
            else:
                if not payload.get("attachments"):
                    # Nothing usable arrived. Report what we saw to aid debugging.
                    return jsonify({
                        "ok": False, "stage": "input",
                        "error": "No job_id, uploaded files, files array, or attachments found.",
                        "debug": {
                            "form_keys": list(request.form.keys()),
                            "files_keys": list(request.files.keys()),
                            "json_keys": list((_jb or {}).keys()),
                            "content_type": request.content_type,
                        },
                    }), 422
                result = build_product_page(
                    payload,
                    publisher=publisher,
                    sirv_publisher=sirv_publisher,
                    sirv_public_base=sirv_base,
                    product_group_dir_map=PRODUCT_GROUP_DIR_MAP,
                    publish=publish,
                )
    except BuildError as e:
        return jsonify({"ok": False, "stage": e.stage, "error": str(e)}), 422
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "stage": "unexpected", "error": str(e)}), 500
    finally:
        for p in (publisher, sirv_publisher):
            if p is not None and hasattr(p, "close"):
                try:
                    p.close()
                except Exception:  # noqa: BLE001
                    pass

    result["dry_run"] = is_mock or not publish
    result.pop("page_html", None)
    return jsonify(result), 200


def _extract_zip(file_storage, workdir):
    """
    Extract an uploaded zip into workdir/uploads; return [(name, path), ...].
    Flat extraction (basename only), skips directories and junk.
    """
    import zipfile
    up = os.path.join(workdir, "uploads")
    os.makedirs(up, exist_ok=True)
    tmp_zip = os.path.join(workdir, "incoming.zip")
    file_storage.save(tmp_zip)
    saved = []
    with zipfile.ZipFile(tmp_zip) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = os.path.basename(info.filename)
            if not name or name.startswith("."):
                continue
            dest = os.path.join(up, name)
            with zf.open(info) as src, open(dest, "wb") as out:
                out.write(src.read())
            saved.append((name, dest))
    return saved


def _decode_files(files_arr, workdir):
    """
    Decode a JSON files array [{fileName, data}, ...] to local files.
    `data` may be base64 or a hex string (Make IMTBuffer often serializes to
    hex). Returns [(name, path), ...].
    """
    import base64
    import binascii
    up = os.path.join(workdir, "uploads")
    os.makedirs(up, exist_ok=True)
    saved = []
    for item in files_arr:
        if not isinstance(item, dict):
            continue
        name = os.path.basename(item.get("fileName") or item.get("name") or "")
        data = item.get("data")
        if not name or data is None:
            continue
        raw = _decode_blob(data)
        dest = os.path.join(up, name)
        with open(dest, "wb") as f:
            f.write(raw)
        saved.append((name, dest))
    return saved


def _decode_blob(data):
    """Decode a file blob that may be base64 or hex."""
    import base64
    import binascii
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    s = str(data).strip()
    # Try hex first if it looks like hex (Make IMTBuffer hex dumps).
    is_hexish = len(s) % 2 == 0 and all(c in "0123456789abcdefABCDEF" for c in s[:64])
    if is_hexish:
        try:
            return binascii.unhexlify(s)
        except (binascii.Error, ValueError):
            pass
    try:
        return base64.b64decode(s, validate=False)
    except (binascii.Error, ValueError):
        return s.encode("utf-8", "ignore")


def _save_uploads(files, workdir):
    """Save Werkzeug FileStorage uploads into workdir/uploads; return [(name, path)]."""
    import os as _os
    up = _os.path.join(workdir, "uploads")
    _os.makedirs(up, exist_ok=True)
    saved = []
    for f in files:
        if not f or not f.filename:
            continue
        name = _os.path.basename(f.filename)
        dest = _os.path.join(up, name)
        f.save(dest)
        saved.append((name, dest))
    return saved


def _as_bool(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def create_app():
    app = Flask(__name__)
    app.register_blueprint(bp)
    return app


# Module-level WSGI app for gunicorn:  gunicorn app.server:app
app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
