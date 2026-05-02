import anthropic
import base64
import hashlib
import json
import os
import shutil
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fal_client
import fitz  # pymupdf

from config import MODEL_FAST, PLAN_2D, RENDER_FILES, CACHE_DIR, RENDERS_OUTPUT_DIR


IMGBB_UPLOAD   = "https://api.imgbb.com/1/upload"
FAL_MODEL      = "fal-ai/flux/dev/image-to-image"
NUM_CANDIDATES = 1


# ── PDF → PNG ──────────────────────────────────────────────────────────────────

def _floor_plan_as_png() -> Path:
    out = CACHE_DIR / "floor_plan.png"
    if out.exists():
        return out
    doc  = fitz.open(str(PLAN_2D))
    page = doc[0]
    # crop to just the floor plan drawing — left ~60% of page, exclude branding panel
    rect = page.rect
    crop = fitz.Rect(rect.x0, rect.y0, rect.x1 * 0.62, rect.y1)
    clip = page.get_pixmap(dpi=150, colorspace=fitz.csRGB, alpha=False, clip=crop)
    clip.save(str(out))
    doc.close()
    return out


# ── image hosting ──────────────────────────────────────────────────────────────

def _upload_imgbb(path: Path) -> str:
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


# ── prompt builder ─────────────────────────────────────────────────────────────

def build_generation_prompt(geometry_spec: dict, finishes_spec: dict, brand_spec: dict) -> str:
    client = anthropic.Anthropic()
    spec_summary = json.dumps({
        "finishes": finishes_spec.get("finishes", finishes_spec),
        "brand":    brand_spec.get("presentation_style", {}),
        "project":  brand_spec.get("project", ""),
    }, indent=2)

    response = client.messages.create(
        model=MODEL_FAST,
        max_tokens=300,
        messages=[{"role": "user", "content": f"""Write a ControlNet image-to-image prompt (max 120 words).

The input image is a 2D architectural floor plan. The output must be an isometric 3D render of the SAME floor plan — preserve every room, wall, hallway and opening exactly. Only add materials and style.

Describe:
- Isometric 45-degree aerial view, roof removed, all rooms visible
- Floor: exact material and tone from finishes spec
- Walls: exact colour from finishes spec
- Kitchen: cabinets, benchtop, island from finishes spec
- Lighting and staging mood from brand spec

End with: "isometric 3D architectural render, photorealistic, white background, 4K"

SPECS:
{spec_summary}

Return ONLY the prompt."""}]
    )
    return response.content[0].text.strip()


# ── fal.ai ControlNet generation ───────────────────────────────────────────────

def _generate_one(prompt: str, control_image_url: str, dest: Path) -> str:
    """Run one fal.ai SDXL ControlNet Canny generation. Returns remote image URL."""
    result = fal_client.subscribe(
        FAL_MODEL,
        arguments={
            "prompt":              prompt,
            "image_url":           control_image_url,
            "strength":            0.85,
            "num_inference_steps": 28,
            "guidance_scale":      3.5,
            "num_images":          1,
        },
        client_timeout=300,
        on_queue_update=lambda u: print(f"    Queue: {u}"),
    )
    img_url = result["images"][0]["url"]
    req = urllib.request.Request(
        img_url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        dest.write_bytes(resp.read())
    return img_url


# ── spec hash ──────────────────────────────────────────────────────────────────

def _spec_hash(geometry_spec: dict, finishes_spec: dict, brand_spec: dict) -> str:
    combined = json.dumps([geometry_spec, finishes_spec, brand_spec], sort_keys=True)
    return hashlib.md5(combined.encode()).hexdigest()[:12]


# ── public API ─────────────────────────────────────────────────────────────────

def generate_candidates(
    geometry_spec: dict,
    finishes_spec: dict,
    brand_spec: dict,
) -> dict:
    """
    1. Build prompt from specs (Claude)
    2. Upload floor plan to imgbb
    3. Run NUM_CANDIDATES generations via fal.ai ControlNet (parallel if >1)
    4. Cache results against spec hash

    Returns {prompt, candidates: [{index, path, filename}], hash, cached}.
    """
    current_hash  = _spec_hash(geometry_spec, finishes_spec, brand_spec)
    candidate_dir = RENDERS_OUTPUT_DIR / "candidates"
    hash_file     = candidate_dir / "hash.txt"

    if hash_file.exists() and hash_file.read_text().strip() == current_hash:
        existing = sorted(candidate_dir.glob("candidate_*.png"))
        if len(existing) == NUM_CANDIDATES:
            print("  Candidate cache hit")
            prompt = (candidate_dir / "prompt.txt").read_text() if (candidate_dir / "prompt.txt").exists() else ""
            return {
                "prompt":     prompt,
                "candidates": [{"index": i, "path": str(p), "filename": p.name} for i, p in enumerate(existing)],
                "hash":       current_hash,
                "cached":     True,
            }

    candidate_dir.mkdir(parents=True, exist_ok=True)

    print("  Building generation prompt...")
    prompt = build_generation_prompt(geometry_spec, finishes_spec, brand_spec)
    print(f"  Prompt: {prompt[:100]}...")

    print("  Uploading floor plan to fal.ai...")
    control_url = fal_client.upload_file(str(_floor_plan_as_png()))
    print(f"  Control image URL: {control_url[:60]}...")

    print(f"  Generating {NUM_CANDIDATES} candidate(s) via fal.ai ControlNet...")
    paths = [candidate_dir / f"candidate_{i}.png" for i in range(NUM_CANDIDATES)]

    if NUM_CANDIDATES == 1:
        _generate_one(prompt, control_url, paths[0])
        print("  Done")
    else:
        with ThreadPoolExecutor(max_workers=NUM_CANDIDATES) as executor:
            futures = [executor.submit(_generate_one, prompt, control_url, paths[i]) for i in range(NUM_CANDIDATES)]
            for i, f in enumerate(futures):
                f.result()
                print(f"  Candidate {i} done")

    hash_file.write_text(current_hash)
    (candidate_dir / "prompt.txt").write_text(prompt)

    return {
        "prompt":     prompt,
        "candidates": [{"index": i, "path": str(p), "filename": p.name} for i, p in enumerate(paths)],
        "hash":       current_hash,
        "cached":     False,
    }


def select_candidate(index: int, geometry_spec: dict, finishes_spec: dict, brand_spec: dict):
    candidate_dir = RENDERS_OUTPUT_DIR / "candidates"
    src  = candidate_dir / f"candidate_{index}.png"
    dest = RENDERS_OUTPUT_DIR / "generated_isometric.png"
    if not src.exists():
        raise FileNotFoundError(f"Candidate {index} not found")
    shutil.copy2(src, dest)
    current_hash = _spec_hash(geometry_spec, finishes_spec, brand_spec)
    (RENDERS_OUTPUT_DIR / "generation_hash.txt").write_text(current_hash)
    prompt = (candidate_dir / "prompt.txt").read_text() if (candidate_dir / "prompt.txt").exists() else ""
    (RENDERS_OUTPUT_DIR / "generation_prompt.txt").write_text(prompt)
    print(f"  Candidate {index} selected as canonical output")
