"""
Validator agent.

Takes up to N NanoBanana render candidates and scores each against the
geometry spec using Claude Vision. Returns the index and score of the best.
"""

import anthropic
import base64
import io
import json

from PIL import Image
from pathlib import Path

from config import MODEL_SMART


def _encode_resized(path: Path) -> str:
    img = Image.open(path).convert("RGB")
    img.thumbnail((1500, 1500))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


def score_renders(client: anthropic.Anthropic, paths: list[Path], geometry_spec: dict) -> dict:
    """
    Score a list of render paths against the geometry spec.
    Returns {"scores": [...], "best": <1-indexed int>}
    """
    rooms = geometry_spec.get("rooms", [])
    room_list = ", ".join(f"{r['name']} {r['width_m']}x{r['depth_m']}m" for r in rooms)
    n = len(paths)

    content = []
    for i, path in enumerate(paths, 1):
        content.append({"type": "text", "text": f"Image {i}:"})
        content.append({
            "type": "image",
            "source": {
                "type":       "base64",
                "media_type": "image/jpeg",
                "data":       _encode_resized(path),
            }
        })

    score_template = [
        f'{{"run": {i}, "structural": 0, "hallucinations": 0, "total": 0, "notes": ""}}'
        for i in range(1, n + 1)
    ]

    content.append({"type": "text", "text": f"""You are validating AI-generated floor plan renders.

The correct floor plan contains exactly these rooms: {room_list}

Score each image 0-10 on:
1. structural — all rooms present, correct count, no rooms removed or resized, outer boundary unchanged
2. hallucinations — no extra rooms, terraces, walls or structural elements invented (10 = none)
total = structural + hallucinations

Return JSON only:
{{
  "scores": [{", ".join(score_template)}],
  "best": 1
}}"""})

    response = client.messages.create(
        model=MODEL_SMART,
        max_tokens=1000,
        messages=[{"role": "user", "content": content}]
    )

    text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())
