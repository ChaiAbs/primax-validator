"""
Furniture agent — Meshy API.

For each room in the enriched geometry, generates an appropriate
3D furniture model via Meshy text-to-3D and records its placement
coordinates for the Three.js scene.
"""

import json
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path

MESHY_BASE = "https://api.meshy.ai/openapi/v2"


# ── Room type → furniture prompt ──────────────────────────────────────────
FURNITURE_PROMPTS = {
    "bedroom": "minimalist Scandinavian double bed with linen bedding, oak frame, bedside tables",
    "living":  "modern L-shaped sofa, light grey fabric, low coffee table, indoor plant",
    "dining":  "round dining table, oak wood, four minimalist chairs, pendant light above",
    "kitchen": "kitchen island bench, light ash timber, integrated sink, two bar stools",
    "wet":     "freestanding bathtub, white oval, chrome fixtures",
    "external":"outdoor lounge chair, white aluminium frame, cushion",
    "storage": None,   # skip
    "generic": None,   # skip
}


def _meshy_post(endpoint: str, payload: dict) -> dict:
    api_key = os.environ.get("MESHY_API_KEY", "")
    if not api_key:
        raise RuntimeError("MESHY_API_KEY not set")
    body = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{MESHY_BASE}/{endpoint}",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _meshy_get(endpoint: str) -> dict:
    api_key = os.environ.get("MESHY_API_KEY", "")
    req = urllib.request.Request(
        f"{MESHY_BASE}/{endpoint}",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _poll_task(task_id: str, timeout: int = 300) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = _meshy_get(f"text-to-3d/{task_id}")
        status = result.get("status", "")
        print(f"    Meshy status={status}", flush=True)
        if status == "SUCCEEDED":
            return result
        if status in ("FAILED", "EXPIRED"):
            raise RuntimeError(f"Meshy task failed: {result}")
        time.sleep(5)
    raise RuntimeError(f"Meshy timed out after {timeout}s")


def generate_furniture(scene: dict) -> dict:
    """
    For each room in scene['rooms'], submit a Meshy text-to-3D job.
    Appends 'furniture' key to each room with model_url + placement.

    Returns updated scene dict.
    """
    rooms = scene.get("rooms", [])

    for room in rooms:
        rtype  = room.get("type", "generic")
        prompt = FURNITURE_PROMPTS.get(rtype)

        if not prompt:
            room["furniture"] = None
            continue

        print(f"  Generating furniture for {room['name']} ({rtype})...", flush=True)

        try:
            # Submit text-to-3D (preview quality for speed)
            resp = _meshy_post("text-to-3d", {
                "mode":      "preview",
                "prompt":    prompt,
                "art_style": "realistic",
            })
            task_id = resp.get("result") or resp.get("id")
            if not task_id:
                raise RuntimeError(f"No task id: {resp}")

            print(f"    Task {task_id}", flush=True)
            result = _poll_task(task_id)

            model_urls = result.get("model_urls", {})
            room["furniture"] = {
                "prompt":    prompt,
                "task_id":   task_id,
                "model_url": model_urls.get("glb") or model_urls.get("obj", ""),
                # Place furniture at room centre
                "x_m":  room["x_m"] + room["width_m"] / 2,
                "y_m":  0,
                "z_m":  room["y_m"] + room["depth_m"] / 2,
            }
            print(f"    Model: {room['furniture']['model_url'][:60]}", flush=True)

        except Exception as e:
            print(f"  WARNING: furniture generation failed for {room['name']}: {e}", flush=True)
            room["furniture"] = None

    return scene
