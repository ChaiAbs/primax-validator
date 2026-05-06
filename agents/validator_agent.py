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

    # Build exact counts for each room name
    room_counts: dict[str, int] = {}
    for r in rooms:
        room_counts[r['name']] = room_counts.get(r['name'], 0) + 1
    exact_counts = ", ".join(f"{cnt}x {name}" for name, cnt in room_counts.items())

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

    content.append({"type": "text", "text": f"""You are validating AI-generated floor plan renders.

The CORRECT floor plan contains EXACTLY these rooms — no more, no less:
{exact_counts}
(with dimensions: {room_list})

Score each image on two criteria (each 0-10):

1. structural (0-10)
   - All rooms from the list above are visible, separate and correctly laid out
   - No room is missing, merged with another, duplicated, resized, or repositioned
   - Every listed room must exist as a distinct, separate space
   - Deduct 2 points per missing, merged, or significantly altered room

2. hallucinations (0-10)
   - No structural elements exist that are NOT in the list above
   - This includes any extra room, space, wall, or enclosed area of any kind
   - Merged rooms count as both a structural error AND a hallucination (the merged space is a new invented shape)
   - 10 = nothing invented. Deduct 3 points per extra or merged element. Score 0 if a large new area is invented.

total = structural + hallucinations (max 20)
"best" = run number (1-{n}) with the highest total. Tiebreak: higher hallucinations score wins.

Return JSON only:
{{
  "scores": [
    {chr(10).join(f'{{"run": {i}, "structural": 0, "hallucinations": 0, "total": 0, "notes": ""}},' for i in range(1, n+1))}
  ],
  "best": <winning run number>
}}"""})

    response = client.messages.create(
        model=MODEL_SMART,
        max_tokens=1000,
        messages=[{"role": "user", "content": content}]
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    result = json.loads(text.strip())

    # Safety: recompute best from scores in case Claude got it wrong
    scores = result.get("scores", [])
    if scores:
        best = max(scores, key=lambda s: (s.get("total", 0), s.get("hallucinations", 0)))
        result["best"] = best["run"]

    return result
