import base64
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import anthropic
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance

from config import MODEL_FAST, CACHE_DIR, RENDERS_OUTPUT_DIR


NB_GENERATE  = "https://api.nanobananaapi.ai/api/v1/nanobanana/generate"
NB_POLL      = "https://api.nanobananaapi.ai/api/v1/nanobanana/record-info"
IMGBB_UPLOAD = "https://api.imgbb.com/1/upload"

_NB_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin":          "https://nanobananaapi.ai",
    "Referer":         "https://nanobananaapi.ai/",
    "Content-Type":    "application/json",
}


def _upload_imgbb(path) -> str:
    api_key = os.environ.get("IMGBB_API_KEY", "")
    if not api_key:
        raise RuntimeError("IMGBB_API_KEY not set")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    data = urllib.parse.urlencode({"key": api_key, "image": b64}).encode("utf-8")
    req  = urllib.request.Request(IMGBB_UPLOAD, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    if not result.get("success"):
        raise RuntimeError(f"imgbb upload failed: {result}")
    return result["data"]["url"]


def _nb_post(payload: dict, endpoint: str = "generate") -> dict:
    api_key = os.environ.get("NANOBANANA_API_KEY", "")
    if not api_key:
        raise RuntimeError("NANOBANANA_API_KEY not set")
    url     = f"https://api.nanobananaapi.ai/api/v1/nanobanana/{endpoint}"
    headers = {**_NB_HEADERS, "Authorization": f"Bearer {api_key}"}
    body    = json.dumps(payload).encode("utf-8")
    req     = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _nb_poll(task_id: str, timeout: int = 300) -> dict:
    api_key = os.environ.get("NANOBANANA_API_KEY", "")
    headers = {**_NB_HEADERS, "Authorization": f"Bearer {api_key}"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        url = f"{NB_POLL}?taskId={task_id}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        data   = (result.get("data") or {})
        status = data.get("successFlag", data.get("flag", data.get("status", -1)))
        print(f"    Poll status={status}", flush=True)
        if status == 1:
            return data
        if status in (2, 3):
            raise RuntimeError(f"NanoBanana failed (flag={status}): {result}")
        time.sleep(3)
    raise RuntimeError(f"NanoBanana timed out after {timeout}s")


def _extract_image_url(data: dict) -> str:
    # NanoBanana nests the URL under data.response.resultImageUrl
    nested = (data.get("response") or {})
    if nested.get("resultImageUrl"):
        return nested["resultImageUrl"]
    for key in ("imageUrl", "image_url", "url", "output"):
        if data.get(key):
            return data[key]
    if data.get("images"):
        imgs = data["images"]
        return imgs[0] if isinstance(imgs, list) else imgs
    raise RuntimeError(f"No image URL in result: {data}")


def _download_image(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def build_render_prompt(geometry_spec: dict, finishes_spec: dict, brand_spec: dict) -> str:
    fin  = finishes_spec.get("finishes", finishes_spec)
    pres = brand_spec.get("presentation_style", {})

    rooms = geometry_spec.get("rooms", [])
    room_list = ", ".join(
        f"{r['name']} {r['width_m']}x{r['depth_m']}m"
        for r in rooms
    )

    primary_colours = ", ".join(
        f"{c['name']} {c['hex']}"
        for c in brand_spec.get("brand_identity", {}).get("primary_colours", [])
    )

    floor_desc   = fin.get("floor",            {}).get("description", "timber flooring")
    wall_desc    = fin.get("walls",            {}).get("description", "white walls")
    kitchen_desc = fin.get("kitchen_cabinets", {}).get("description", "timber cabinetry")
    window_desc  = fin.get("window_frames",    {}).get("description", "aluminium frames")
    mood         = pres.get("mood", "")

    # Build exact room counts dynamically from the spec — works for any floor plan
    room_counts = {}
    for r in rooms:
        name = r['name']
        room_counts[name] = room_counts.get(name, 0) + 1

    exact_counts = ", ".join(
        f"{count}x {name}" for name, count in room_counts.items()
    )

    return (
        f"STRICT RULES — DO NOT VIOLATE: "
        f"(1) Do NOT add any new rooms, walls, partitions, or structural elements that are not in the reference image. "
        f"(2) Do NOT remove or resize any existing room. "
        f"(3) Do NOT change the viewing angle — keep the exact overhead top-down perspective. "
        f"CRITICAL: This floor plan contains EXACTLY these rooms and no others: {exact_counts}. "
        f"Adding, removing, merging, splitting, or duplicating ANY room or space is a DISQUALIFYING ERROR. "
        f"Every room listed must remain as a separate, distinct, visible space in the output. "
        f"ONLY these three things may change: furniture placed inside rooms, material finishes applied to surfaces, brand colours applied to soft furnishings. "
        f"Apply finishes: {floor_desc} — but terraces and outdoor areas must use light stone or porcelain tile, NOT timber. {wall_desc}. {kitchen_desc}. {window_desc}. "
        f"Brand colours: {primary_colours}. Mood: {mood}. "
        f"Photorealistic top-down floor plan visualization, 4K."
    )


def render_from_floor_plan(geometry_spec: dict, finishes_spec: dict, brand_spec: dict,
                           floor_plan_url: str = None) -> str:
    """
    Submit to NanoBanana image-to-image, poll for result, save and return base64-encoded PNG.
    Accepts an optional pre-uploaded floor_plan_url to skip the imgbb upload (for parallel runs).
    """
    print("  Building render prompt from specs...", flush=True)
    prompt = build_render_prompt(geometry_spec, finishes_spec, brand_spec)
    print(f"  Prompt: {prompt[:120]}...", flush=True)

    if floor_plan_url is None:
        clean_path = CACHE_DIR / "floor_plan_clean.png"
        floor_plan_path = clean_path if clean_path.exists() else CACHE_DIR / "floor_plan.png"
        if not floor_plan_path.exists():
            raise FileNotFoundError("floor_plan.png not found in cache")
        print("  Uploading floor plan to imgbb...", flush=True)
        floor_plan_url = _upload_imgbb(floor_plan_path)
        print(f"  Floor plan uploaded: {floor_plan_url[:60]}...", flush=True)

    image_urls = [floor_plan_url]

    print("  Submitting to NanoBanana (generate-2)...", flush=True)
    response = _nb_post({
        "prompt":      prompt,
        "imageUrls":   image_urls,
        "aspectRatio": "auto",
        "resolution":  "2K",
        "outputFormat": "jpg",
    }, endpoint="generate-2")
    print(f"  NanoBanana response: {response}", flush=True)

    if response.get("code") != 200:
        raise RuntimeError(f"NanoBanana submission failed: {response}")

    resp_data = response.get("data") or {}

    # Check if result came back immediately
    try:
        img_url = _extract_image_url(resp_data)
        print("  Result returned immediately", flush=True)
        data = resp_data
    except RuntimeError:
        task_id = resp_data.get("taskId")
        if not task_id:
            raise RuntimeError(f"No taskId in response: {response}")
        print(f"  Polling taskId={task_id}...", flush=True)
        data = _nb_poll(task_id)

    img_url = _extract_image_url(data)
    print(f"  Downloading result from {img_url[:60]}...", flush=True)
    img_bytes = _download_image(img_url)

    out_path = RENDERS_OUTPUT_DIR / "nb_render.png"
    out_path.write_bytes(img_bytes)
    print(f"  Saved raw render to {out_path}", flush=True)

    print("  Applying depth cues...", flush=True)
    enhanced = _apply_depth_cues(out_path)

    enhanced_path = RENDERS_OUTPUT_DIR / "nb_render_enhanced.png"
    enhanced.save(enhanced_path)
    print(f"  Saved enhanced render to {enhanced_path}", flush=True)

    buf = base64.b64encode(enhanced_path.read_bytes()).decode("utf-8")
    return buf, img_url


def _apply_depth_cues(img_path: Path) -> Image.Image:
    """
    Post-process a flat NanoBanana render with two cheap depth cues:
    1. Directional gradient  — lighter top-right, darker bottom-left (aerial light)
    2. Ambient occlusion     — darken pixels near wall edges to simulate corners
    """
    img = Image.open(img_path).convert("RGB")
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]

    # Directional gradient (light from top-right)
    xs = np.linspace(0, 1, w)
    ys = np.linspace(0, 1, h)
    xg, yg = np.meshgrid(xs, ys)
    gradient = 1.0 - 0.15 * (yg * 0.6 + (1 - xg) * 0.4)
    arr = arr * gradient[:, :, np.newaxis]

    # Ambient occlusion: darken near dark wall edges
    gray = np.mean(arr, axis=2)
    wall_mask = Image.fromarray((gray < 80).astype(np.uint8) * 255)
    ao = np.array(wall_mask.filter(ImageFilter.GaussianBlur(radius=8)), dtype=np.float32) / 255.0
    arr = arr * (1.0 - 0.20 * ao)[:, :, np.newaxis]

    result = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    result = ImageEnhance.Contrast(result).enhance(1.10)
    return result
