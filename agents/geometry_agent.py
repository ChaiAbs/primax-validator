import anthropic
import base64
from pathlib import Path
from config import PLAN_2D, MODEL_SMART
from agents.utils import parse_json_response


def extract_geometry_spec(client: anthropic.Anthropic) -> dict:
    """
    Reads the 2D floor plan PDF and extracts:
    - Room names, labeled dimensions, areas
    - Spatial layout: x_m/y_m position of each room's bottom-left corner
    - Column/row grid structure
    - Adjacency relationships
    """
    with open(PLAN_2D, "rb") as f:
        pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")

    # Pass 1 — extract dimensions and describe the grid layout in plain English
    pass1 = client.messages.create(
        model=MODEL_SMART,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_data
                    }
                },
                {
                    "type": "text",
                    "text": """Study this 2D architectural floor plan carefully.

1. List every labeled room with its EXACT labeled dimensions (e.g. "DINING 3.8 x 3.0").

2. Describe the grid layout — identify columns (left to right) and rows (top to bottom).
   For example:
   - Column 0 (leftmost): Dining, Kitchen, Bath stacked top to bottom
   - Column 1 (middle): Living, Bed 01, Bed 02, Ensuite stacked top to bottom
   - Column 2 (right): Terrace 1, Terrace 2, Bed 03 stacked top to bottom

3. For each room identify:
   - Which column it belongs to (0=left, 1=middle, 2=right)
   - Which row it belongs to (0=top, 1, 2, 3=bottom)
   - Which rooms share a wall directly to its: left, right, above, below

Be precise. Use the labeled dimensions exactly as written on the plan."""
                }
            ]
        }]
    )
    layout_description = pass1.content[0].text.strip()

    # Pass 2 — derive x_m/y_m coordinates from column/row structure + known dimensions
    pass2 = client.messages.create(
        model=MODEL_SMART,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_data
                        }
                    },
                    {
                        "type": "text",
                        "text": f"""Floor plan layout analysis:
{layout_description}

Now derive the exact (x_m, y_m) bottom-left corner position for every room.

COORDINATE RULES:
- Origin (0,0) = bottom-left corner of the apartment's outer boundary
- x increases going RIGHT
- y increases going UP
- Use each room's labeled dimensions to calculate neighbour positions

Work column by column, from the bottom up. Show arithmetic:
e.g. "Dining: x = 0, y = total_height - Dining.depth = 11.5 - 3.0 = 8.5"

Calculate ALL rooms."""
                    }
                ]
            }
        ]
    )
    working_text = pass2.content[0].text.strip()

    # Pass 3 — emit clean JSON with dimensions + positions + structure
    pass3 = client.messages.create(
        model=MODEL_SMART,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_data
                        }
                    },
                    {
                        "type": "text",
                        "text": f"""Floor plan layout analysis:
{layout_description}

Coordinate derivation:
{working_text}"""
                    }
                ]
            },
            {
                "role": "assistant",
                "content": "Based on the analysis above, here is the complete JSON:"
            },
            {
                "role": "user",
                "content": """Output ONLY valid JSON with this exact structure. No markdown, no explanation.

IMPORTANT:
- Include ALL rooms from the floor plan — do not omit any (typically 10-12 rooms including Store, Laundry, Ensuite, all Terraces)
- Use the EXACT room name as labeled on the plan (e.g. "Terrace 1" not "TERRACE_UPPER", "Ensuite" not "ENS")
- Every room must have x_m and y_m coordinates

{
  "apartment": "",
  "level": "",
  "total_area_m2": 0,
  "internal_area_m2": 0,
  "external_area_m2": 0,
  "bounding_box": {"width_m": 0, "depth_m": 0},
  "rooms": [
    {
      "name": "",
      "width_m": 0,
      "depth_m": 0,
      "area_m2": 0,
      "x_m": 0,
      "y_m": 0,
      "column": 0,
      "row": 0,
      "type": "internal|external",
      "adjacent": {"above": "", "below": "", "left": "", "right": ""}
    }
  ],
  "spatial_relationships": [],
  "bedrooms": 0,
  "bathrooms": 0,
  "car_spaces": 0
}"""
            }
        ]
    )

    return parse_json_response(pass3.content[0].text)
