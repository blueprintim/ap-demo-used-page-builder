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

# Map logo_key -> media sub-folder used in media_path. Adjust to your taxonomy.
PRODUCT_GROUP_DIR_MAP = {
    "hiab": "hiab-boom-trucks",
    "moffett": "moffett-forklifts",
    "palfinger": "palfinger",
    "multilift": "multilift-hooklifts",
}


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


@bp.route("/build_product_page", methods=["POST"])
def build_endpoint():
    if not _check_auth(request):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    publisher, is_mock = _make_publisher()
    sirv_publisher = _make_sirv_publisher()
    sirv_base = os.environ.get("SIRV_PUBLIC_BASE", "https://blueprint.sirv.com")

    # Two intake modes:
    #  (a) multipart/form-data with uploaded files (Make "Download an Attachment")
    #  (b) JSON body with attachment URLs (endpoint downloads them itself)
    uploaded = request.files.getlist("files") or list(request.files.values())

    try:
        if uploaded:
            # Save uploads to a temp dir and hand the builder local file paths.
            import tempfile
            workdir = tempfile.mkdtemp(prefix="cpb_up_")
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
            payload = request.get_json(silent=True) or {}
            publish = payload.get("publish", True)
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
