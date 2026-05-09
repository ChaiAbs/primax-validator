import anthropic
import base64
from config import BRAND_GUIDE, MODEL
from agents.utils import parse_json_response


def extract_brand_spec(client: anthropic.Anthropic) -> dict:
    """
    Reads the brand guide PDF and extracts the project's visual identity spec —
    colour palette, tone, mood, staging style, and design language.
    """
    with open(BRAND_GUIDE, "rb") as f:
        pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")

    response = client.messages.create(
        model=MODEL,
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
                    "text": """You are extracting the visual identity specification from this real estate project brand guide.

Extract two distinct layers:

1. BRAND IDENTITY — how the project presents itself (colours, typography, tone of voice)
2. PRESENTATION STYLE — how interiors should be rendered and staged (mood, lighting feel, accent colours, styling approach)

Return ONLY valid JSON:
{
  "project": "",
  "brand_identity": {
    "primary_colours": [{"name": "", "hex": "", "usage": ""}],
    "typography": {"heading": "", "body": ""},
    "tone_of_voice": "",
    "positioning": ""
  },
  "presentation_style": {
    "mood": "",
    "lighting": "",
    "accent_colours": [{"hex": "", "where": ""}],
    "staging_approach": "",
    "key_descriptors": []
  },
  "design_principles": []
}"""
                }
            ]
        }]
    )

    return parse_json_response(response.content[0].text)
