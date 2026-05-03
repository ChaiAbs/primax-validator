"""
Hunyuan 3D agent.

Takes the NanoBanana output URL (already hosted), sends it directly to
fal-ai/hunyuan-3d/v3.1/pro/image-to-3d, and downloads the resulting GLB.
"""

import urllib.request
from pathlib import Path

import fal_client


def generate_3d(image_url: str, output_path: Path) -> Path:
    print(f"Submitting to Hunyuan 3D: {image_url[:60]}...", flush=True)
    result = fal_client.subscribe(
        "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
        arguments={
            "input_image_url": image_url,
            "generate_type":   "Normal",
            "face_count":      500000,
            "enable_pbr":      True,
        },
        with_logs=True,
    )

    glb_url = result["model_glb"]["url"]
    print(f"  GLB ready: {glb_url[:60]}...", flush=True)
    urllib.request.urlretrieve(glb_url, str(output_path))
    return output_path
