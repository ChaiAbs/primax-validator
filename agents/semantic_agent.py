"""
Claude Vision semantic agent.

Asks Claude to identify room labels, dimensions, pixel centroids, and
the adjacency graph (which room shares which wall with which neighbor).
The adjacency graph is consumed by constraint_agent to derive globally-
consistent metre positions — fixing the case where labeled widths sum
to more than the plan's actual width.
"""

import anthropic
import base64
from pathlib import Path
from agents.utils import parse_json_response
from config import MODEL_SMART


def extract_semantics(image_path: Path, plan_bounds: dict) -> dict:
    """
    plan_bounds: output of cv_geometry_agent.get_plan_bounds()
      { x1, y1, x2, y2, img_w, img_h }

    Returns:
    {
      "plan_width_m": float,
      "plan_depth_m": float,
      "rooms": [
        { "name", "width_m", "depth_m", "area_m2", "type",
          "label_px": int,   # pixel X of label center in original image
          "label_py": int    # pixel Y of label center in original image
        }
      ],
      "adjacency": [
        { "room_a": str, "room_b": str, "shared_edge": "right"|"left"|"top"|"bottom" }
      ]
    }
    shared_edge is from room_a's perspective:
      "right"  → room_a's right wall = room_b's left wall
      "left"   → room_a's left wall  = room_b's right wall
      "top"    → room_a's top wall   = room_b's bottom wall  (room_b is above)
      "bottom" → room_a's bottom wall = room_b's top wall   (room_b is below)
    Each pair appears once only.
    """
    client = anthropic.Anthropic()

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    ext        = image_path.suffix.lstrip(".").lower()
    media_type = "image/png" if ext == "png" else "image/jpeg"

    x1, y1 = plan_bounds["x1"], plan_bounds["y1"]
    x2, y2 = plan_bounds["x2"], plan_bounds["y2"]
    iw, ih  = plan_bounds["img_w"], plan_bounds["img_h"]

    response = client.messages.create(
        model=MODEL_SMART,
        max_tokens=2500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64}
                },
                {
                    "type": "text",
                    "text": f"""This floor plan image is {iw}×{ih} pixels.
The apartment drawing occupies pixels x=[{x1}..{x2}], y=[{y1}..{y2}].

For EVERY labeled room, return:
1. name — exact label text. If two rooms share the same label, append a numeric
   suffix to make every name unique (e.g. "TERRACE 01", "TERRACE 02").
   Use these unique names consistently in both the rooms list and the adjacency list.
2. width_m and depth_m — the two labeled dimensions in metres
3. area_m2 — labeled area if shown, else width_m × depth_m
4. type — "external" for terraces/balconies, "internal" for all others
5. label_px, label_py — pixel coordinates (integers) of the CENTER of the room label text
   in the full {iw}×{ih} image. Be as precise as possible.

Also return:
- plan_width_m: total apartment width from the plan (metres)
- plan_depth_m: total apartment depth from the plan (metres)
- adjacency: shared-wall relationships between rooms.
  For each pair of rooms that share a wall, record:
    room_a, room_b, shared_edge
  where shared_edge is which edge of room_a contacts room_b:
    "right"  → room_a's right wall = room_b's left wall
    "left"   → room_a's left wall  = room_b's right wall
    "top"    → room_a's top wall   = room_b's bottom wall  (room_b is above)
    "bottom" → room_a's bottom wall = room_b's top wall   (room_b is below)
  List each pair once only (do not duplicate with swapped roles).

The image coordinate origin (0,0) is TOP-LEFT.
Estimate label_px/label_py carefully by looking at where each label text sits.

Return ONLY valid JSON, no markdown:
{{
  "plan_width_m": 9.8,
  "plan_depth_m": 11.55,
  "rooms": [
    {{
      "name": "DINING",
      "width_m": 3.8, "depth_m": 3.0, "area_m2": 11.4,
      "type": "internal",
      "label_px": 412,
      "label_py": 580
    }}
  ],
  "adjacency": [
    {{"room_a": "DINING", "room_b": "LIVING", "shared_edge": "right"}},
    {{"room_a": "LIVING", "room_b": "BED 01", "shared_edge": "top"}}
  ]
}}"""
                }
            ]
        }]
    )

    return parse_json_response(response.content[0].text)
