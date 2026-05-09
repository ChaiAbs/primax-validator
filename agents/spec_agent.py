import anthropic
import base64
from pathlib import Path
from config import RENDERS_DIR, MODEL
from agents.utils import parse_json_response


def encode_image(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    media_type = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8"), media_type


def extract_project_spec(client: anthropic.Anthropic) -> dict:
    """
    Reads all project renders and extracts a canonical finishes specification.
    Separates permanent finishes (floor, walls, cabinets) from staged elements (furniture, art).
    """
    render_files = sorted(RENDERS_DIR.glob("*.jpg")) + sorted(RENDERS_DIR.glob("*.jpeg")) if RENDERS_DIR.exists() else []
    image_blocks = []
    for i, render_path in enumerate(render_files):
        data, media_type = encode_image(render_path)
        image_blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data}
        })
        image_blocks.append({
            "type": "text",
            "text": f"Render {i + 1}: {render_path.name}"
        })

    image_blocks.append({
        "type": "text",
        "text": """You are extracting the permanent finishes specification for a real estate project called Sanctuary Quarter, Rouse Hill.

These renders are photos of the show suite (Apartment 1.01). Your job is to extract only the PERMANENT FINISHES — materials and finishes that are fixed and identical across every apartment in the building.

INCLUDE (permanent finishes):
- Floor material, colour, finish
- Wall paint colour and finish
- Kitchen cabinet material, colour, finish
- Kitchen benchtop material and colour
- Window and door frame colour and material
- Skirting board colour
- Ceiling colour
- Any fixed architectural details (e.g. fluted panels)

EXCLUDE (staged/movable):
- Furniture (sofas, beds, tables, chairs)
- Art, mirrors, decorative objects
- Plants and greenery
- Rugs, cushions, linen
- Appliances visible on benchtops

For each finish, estimate the dominant hex colour from what you observe across the renders.

Return ONLY valid JSON in this exact format:
{
  "project": "Sanctuary Quarter",
  "finishes": {
    "floor": {"material": "", "description": "", "hex": ""},
    "walls": {"material": "", "description": "", "hex": ""},
    "ceiling": {"material": "", "description": "", "hex": ""},
    "kitchen_cabinets": {"material": "", "description": "", "hex": ""},
    "kitchen_benchtop": {"material": "", "description": "", "hex": ""},
    "window_frames": {"material": "", "description": "", "hex": ""},
    "door_frames": {"material": "", "description": "", "hex": ""},
    "skirting": {"material": "", "description": "", "hex": ""},
    "island_panel": {"material": "", "description": "", "hex": ""}
  },
  "confidence_notes": ""
}"""
    })

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": image_blocks}]
    )

    return parse_json_response(response.content[0].text)
