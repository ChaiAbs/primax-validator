"""
Happy Horse agent — alibaba/happy-horse/image-to-video via fal.ai.

Takes a hosted image URL (e.g. the best NanoBanana render),
generates a short orbit/cinematic video, then extracts a frame
at `frame_time` seconds as a PNG.

Returns the Path to the extracted PNG.
"""

import subprocess
import urllib.request
from pathlib import Path

import fal_client

from config import RENDERS_OUTPUT_DIR


def generate_video_frame(image_url: str, frame_time: float = 3.9) -> Path:
    """
    1. Submit image_url to Happy Horse → get MP4 URL
    2. Download MP4
    3. Extract frame at `frame_time` seconds with ffmpeg
    4. Return Path to PNG
    """
    print(f"Submitting to Happy Horse: {image_url[:60]}...", flush=True)

    result = fal_client.subscribe(
        "alibaba/happy-horse/image-to-video",
        arguments={
            "image_url":  image_url,
            "prompt":     "Zoom out and Tilt camera to a 45-degree isometric angle, walls rising into view, revealing the apartment in three dimensions.",
            "duration":   4,
            "resolution": "720p",
        },
        with_logs=True,
    )
    print(f"  Happy Horse result keys: {list(result.keys())}", flush=True)

    # Extract video URL — fal.ai typically puts it in result["video"]["url"]
    video_url = None
    if isinstance(result.get("video"), dict):
        video_url = result["video"].get("url")
    if not video_url:
        for key in ("video_url", "url", "output"):
            if result.get(key):
                video_url = result[key] if isinstance(result[key], str) else result[key].get("url")
                break
    if not video_url:
        raise RuntimeError(f"No video URL in Happy Horse result: {result}")

    print(f"  Video ready: {video_url[:80]}...", flush=True)

    # Download MP4
    video_path = RENDERS_OUTPUT_DIR / "happyhorse.mp4"
    print(f"  Downloading video...", flush=True)
    req = urllib.request.Request(video_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        video_path.write_bytes(resp.read())
    print(f"  Video saved: {video_path}", flush=True)

    # Extract frame with ffmpeg
    frame_path = RENDERS_OUTPUT_DIR / "happyhorse_frame.png"
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(frame_time),
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "2",
        str(frame_path),
    ]
    print(f"  Extracting frame at {frame_time}s...", flush=True)
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"  Frame saved: {frame_path}", flush=True)

    return frame_path
