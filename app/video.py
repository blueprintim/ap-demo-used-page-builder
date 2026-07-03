"""
video.py
Concatenate multiple source videos into one MP4 using ffmpeg.

Strategy: two-pass, which is the most robust across heterogeneous phone/camera
clips.
  Pass 1 - normalise each clip independently to a uniform intermediate:
           fixed canvas (scale-to-fit + pad), 30fps, H.264, AND a guaranteed
           AAC audio track (real audio, or synthesised silence via anullsrc
           bounded by -shortest to the video length).
  Pass 2 - concat-demux the uniform intermediates (fast, no re-encode needed,
           but we re-encode lightly to be safe with -c copy fallback avoided).

Videos are concatenated in the order given (caller sorts by filename number).
Single video is still normalised. Empty list -> None.
"""

from __future__ import annotations
import os
import subprocess
import tempfile


class VideoError(Exception):
    pass


def _run(cmd, timeout):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise VideoError(f"ffmpeg timed out after {timeout}s") from e
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-10:])
        raise VideoError(f"ffmpeg failed:\n{tail}")
    return p


def _normalise(src, dst, target_w, target_h, timeout):
    """Normalise one clip to uniform video+audio."""
    vf = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p"
    )
    # Add a silent audio source; -shortest ties its length to the (finite) video.
    cmd = [
        "ffmpeg", "-y",
        "-i", src,
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-vf", vf,
        "-map", "0:v:0",
        "-map", "1:a:0", "-map", "0:a:0?",  # silence, plus real audio if present
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        dst,
    ]
    _run(cmd, timeout)
    if not os.path.exists(dst) or os.path.getsize(dst) == 0:
        raise VideoError(f"Normalisation produced no output for {src}")


def concat_videos(video_paths, out_path, *, target_w=1920, target_h=1080, timeout=1800):
    if not video_paths:
        return None
    for p in video_paths:
        if not os.path.exists(p):
            raise VideoError(f"Video not found: {p}")

    with tempfile.TemporaryDirectory() as tmp:
        norm_paths = []
        for i, src in enumerate(video_paths):
            dst = os.path.join(tmp, f"norm_{i:03d}.mp4")
            _normalise(src, dst, target_w, target_h, timeout)
            norm_paths.append(dst)

        if len(norm_paths) == 1:
            # Single clip: the normalised file IS the result.
            _copy(norm_paths[0], out_path)
            return out_path

        listfile = os.path.join(tmp, "concat.txt")
        with open(listfile, "w") as f:
            for p in norm_paths:
                f.write(f"file '{p}'\n")

        # Intermediates are now uniform, so the concat demuxer + stream copy works.
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
            "-c", "copy", "-movflags", "+faststart", out_path,
        ]
        _run(cmd, timeout)

    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise VideoError("ffmpeg produced no output file.")
    return out_path


def _copy(src, dst):
    import shutil
    shutil.copyfile(src, dst)
