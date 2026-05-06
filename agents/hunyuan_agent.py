"""
3D generation agent — Trellis 2 (fal-ai/trellis-2).

Takes the NanoBanana output URL (already hosted), sends it to Trellis 2,
and downloads the resulting GLB.
"""

import urllib.request
from pathlib import Path

import fal_client


def generate_3d(image_url: str, output_path: Path) -> Path:
    print(f"Submitting to Trellis 2: {image_url[:60]}...", flush=True)
    result = fal_client.subscribe(
        "fal-ai/trellis-2",
        arguments={
            "image_url": image_url,
        },
        with_logs=True,
    )

    print(f"  Trellis result keys: {list(result.keys())}", flush=True)

    # Trellis returns model_glb
    if result.get("model_glb"):
        glb_url = result["model_glb"]["url"]
    elif result.get("model_mesh"):
        glb_url = result["model_mesh"]["url"]
    else:
        raise RuntimeError(f"No GLB in Trellis result: {result}")

    print(f"  GLB ready: {glb_url[:60]}...", flush=True)
    urllib.request.urlretrieve(glb_url, str(output_path))
    return output_path
