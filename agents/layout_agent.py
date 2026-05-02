import anthropic
import base64
import json
from config import MODEL_SMART, CACHE_DIR
from agents.utils import parse_json_response


def extract_layout(geometry_spec: dict) -> dict:
    """Use Claude vision to extract room (x_m, y_m) positions from the cached floor plan PNG."""
    cache_path = CACHE_DIR / "layout.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    floor_plan_path = CACHE_DIR / "floor_plan.png"
    if not floor_plan_path.exists():
        raise FileNotFoundError("floor_plan.png not in cache — run spec extraction first")

    client = anthropic.Anthropic()

    with open(floor_plan_path, "rb") as f:
        img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    rooms_info = "\n".join(
        f"- {r['name']}: {r['width_m']}m wide x {r['depth_m']}m deep"
        for r in geometry_spec["rooms"]
    )

    rooms_dims = {r["name"]: r for r in geometry_spec["rooms"]}

    # Pass 1 — verbal adjacency description
    pass1 = client.messages.create(
        model=MODEL_SMART,
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
                },
                {
                    "type": "text",
                    "text": f"""This is a 2D architectural floor plan. Study it carefully.

Known rooms: {', '.join(r['name'] for r in geometry_spec['rooms'])}

For EACH room describe:
1. Which edge of the apartment it sits on (top / bottom / left / right / interior)
2. Which room is directly above it (sharing a wall, no gap)
3. Which room is directly below it (sharing a wall, no gap)
4. Which room is directly to its left (sharing a wall, no gap)
5. Which room is directly to its right (sharing a wall, no gap)

Be precise — "directly above" means they share an edge with no corridor gap.
Write one line per room: "RoomName: above=X, below=Y, left=Z, right=W, edge=E"
If no neighbour in a direction write "none".""",
                },
            ],
        }],
    )
    adjacency_description = pass1.content[0].text.strip()

    # Pass 2 — derive coordinates from adjacency + known dimensions, then extract JSON
    p2_user_content = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
        },
        {
            "type": "text",
            "text": f"""This is a 2D architectural floor plan.

COORDINATE SYSTEM:
- Origin (0, 0) = bottom-left corner of the apartment's outer boundary
- x increases going RIGHT, y increases going UP
- Apartment is approximately 11.5m wide × 11.5m tall

Room dimensions (width × depth in metres):
{rooms_info}

Adjacency relationships identified from the floor plan:
{adjacency_description}

Derive the bottom-left corner (x_m, y_m) for each room:
- Start from Dining as anchor
- Use adjacency + exact dimensions to calculate each neighbour
- Show working: "RoomName: y = anchor_y - depth = result" """,
        },
    ]

    p2_working = client.messages.create(
        model=MODEL_SMART,
        max_tokens=1000,
        messages=[{"role": "user", "content": p2_user_content}],
    )
    working_text = p2_working.content[0].text.strip()

    # Pass 2b — turn the working into clean JSON
    response = client.messages.create(
        model=MODEL_SMART,
        max_tokens=800,
        messages=[
            {"role": "user",    "content": p2_user_content},
            {"role": "assistant","content": working_text},
            {"role": "user",    "content": f"Now output ONLY valid JSON for ALL {len(geometry_spec['rooms'])} rooms. Use exactly these fields per room: name, x_m, y_m. No extra fields, no markdown, no explanation."},
        ],
    )

    layout = parse_json_response(response.content[0].text)
    cache_path.write_text(json.dumps(layout, indent=2))
    return layout
