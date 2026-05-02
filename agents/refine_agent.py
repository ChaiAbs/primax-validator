import base64
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import anthropic

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


def _nb_post(payload: dict) -> dict:
    api_key = os.environ.get("NANOBANANA_API_KEY", "")
    if not api_key:
        raise RuntimeError("NANOBANANA_API_KEY not set")
    headers = {**_NB_HEADERS, "Authorization": f"Bearer {api_key}"}
    body    = json.dumps(payload).encode("utf-8")
    req     = urllib.request.Request(NB_GENERATE, data=body, headers=headers, method="POST")
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
    client = anthropic.Anthropic()
    fin  = finishes_spec.get("finishes", finishes_spec)
    pres = brand_spec.get("presentation_style", {})

    rooms = geometry_spec.get("rooms", [])
    room_list = ", ".join(
        f"{r['name']} {r['width_m']}×{r['depth_m']}m"
        for r in rooms
    )

    accent_colours = ", ".join(
        f"{c['hex']} ({c.get('where', '')})"
        for c in pres.get("accent_colours", [])
    )
    primary_colours = ", ".join(
        f"{c['name']} {c['hex']}"
        for c in brand_spec.get("brand_identity", {}).get("primary_colours", [])
    )

    response = client.messages.create(
        model=MODEL_FAST,
        max_tokens=500,
        messages=[{"role": "user", "content": f"""Write an image-to-image prompt (max 130 words) for NanoBanana. One reference image is provided:
  Image 1 = 2D floor plan — room layout is FIXED, do not alter room positions or sizes.

The prompt must instruct:

1. LAYOUT: Strictly follow the floor plan. Rooms: {room_list}. Preserve all room boundaries exactly.

2. VIEW: Convert to a 3D isometric dollhouse view — 45-degree angled top-down perspective, visible wall height, depth and shadows.

3. FINISHES: {fin.get("floor", {}).get("description", "")}. {fin.get("walls", {}).get("description", "")}. {fin.get("kitchen_cabinets", {}).get("description", "")}. {fin.get("window_frames", {}).get("description", "")}.

4. BRAND COLOURS: Apply brand palette — {primary_colours}. Accent colours: {accent_colours}. Mood: {pres.get("mood", "")}. Lighting: {pres.get("lighting", "")}.

End with: "photorealistic architectural dollhouse visualization, 4K"

Return ONLY the prompt."""}],
    )
    return response.content[0].text.strip()


def render_from_floor_plan(geometry_spec: dict, finishes_spec: dict, brand_spec: dict) -> str:
    """
    Upload the cached floor_plan.png to imgbb, submit to NanoBanana image-to-image,
    poll for result, save and return base64-encoded PNG.
    """
    clean_path = CACHE_DIR / "floor_plan_clean.png"
    floor_plan_path = clean_path if clean_path.exists() else CACHE_DIR / "floor_plan.png"
    if not floor_plan_path.exists():
        raise FileNotFoundError("floor_plan.png not found in cache")
    print(f"  Using {'clean' if clean_path.exists() else 'original'} floor plan", flush=True)

    print("  Building render prompt from specs...", flush=True)
    prompt = build_render_prompt(geometry_spec, finishes_spec, brand_spec)
    print(f"  Prompt: {prompt[:120]}...", flush=True)

    print("  Uploading floor plan to imgbb...", flush=True)
    floor_plan_url = _upload_imgbb(floor_plan_path)
    print(f"  Floor plan uploaded: {floor_plan_url[:60]}...", flush=True)

    image_urls = [floor_plan_url]

    print("  Submitting to NanoBanana...", flush=True)
    response = _nb_post({
        "prompt":    prompt,
        "type":      "IMAGETOIAMGE",
        "numImages": 1,
        "imageUrls": image_urls,
    })
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
    print(f"  Saved to {out_path}", flush=True)

    return base64.b64encode(img_bytes).decode("utf-8")
