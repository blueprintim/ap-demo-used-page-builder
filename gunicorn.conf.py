"""
gunicorn.conf.py
Run with:  gunicorn -c gunicorn.conf.py app.server:app

Why this file exists: a real build downloads/concatenates video (ffmpeg two-pass)
and uploads ~100-200MB to Sirv, which easily exceeds gunicorn's DEFAULT 30s
worker timeout -- the worker gets killed mid-build and the client sees a bare
HTML 500 (the same failure mode that made every run look "successful" in Make
while nothing published). Give a build real headroom.

Override any value via env (e.g. WEB_CONCURRENCY, GUNICORN_TIMEOUT) on Render.
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
# One long-running build holds a worker for its whole duration; a couple of
# workers lets a health check / second card proceed. Keep low -- ffmpeg is heavy.
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
# Big video builds are slow; 300s is generous but bounded.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "300"))
graceful_timeout = 30
# Recycle workers periodically so a leaked ffmpeg tmp file / fd can't accumulate.
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "100"))
max_requests_jitter = 20
accesslog = "-"
errorlog = "-"
