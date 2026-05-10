import anthropic
import base64
from config import PLAN_2D, MODEL
from agents.utils import parse_json_response


def extract_geometry_spec(client: anthropic.Anthropic) -> dict:
    with open(PLAN_2D, "rb") as f:
        pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
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
                    "text": """Study this 2D architectural floor plan and output ONLY valid JSON. No markdown, no explanation.

Include ALL rooms — do not omit any (typically 10-12 rooms including Store, Laundry, Ensuite, all Terraces).
Use the exact room name as labeled on the plan. Use the exact labeled dimensions.

{
  "rooms": [
    {"name": "", "width_m": 0, "depth_m": 0}
  ]
}"""
                }
            ]
        }]
    )

    return parse_json_response(response.content[0].text)
