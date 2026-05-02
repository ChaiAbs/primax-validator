import anthropic
import json
from config import MODEL_FAST
from agents.utils import parse_json_response


def synthesise_punch_list(
    client: anthropic.Anthropic,
    geometry_spec: dict,
    finishes_spec: dict,
    brand_spec: dict,
    comparison: dict
) -> dict:
    """
    Computes overall scores and writes a concise cross-dimensional summary.
    Detailed failures come directly from comparison — not repeated here.
    """
    project = brand_spec.get("project", "this project")
    geo_score = comparison["geometry"].get("score", 0)
    fin_score = comparison["finishes"].get("score", 0)
    brd_score = comparison["brand"].get("score", 0)
    overall   = round((geo_score + fin_score + brd_score) / 3)

    prompt = f"""Write a 2-3 sentence quality summary for a 3D artist reviewing {project}.

Geometry score: {geo_score}%
Finishes score: {fin_score}%
Brand score: {brd_score}%

Geometry failures: {[f['element'] for f in comparison['geometry'].get('failures', [])]}
Finishes failures: {[f['element'] for f in comparison['finishes'].get('failures', [])]}
Brand failures: {[f['element'] for f in comparison['brand'].get('failures', [])]}

State what's broadly working, what the most critical fix is, and what dimension needs the most attention.
Be direct. No padding.

Return ONLY valid JSON:
{{"summary": ""}}"""

    response = client.messages.create(
        model=MODEL_FAST,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}]
    )

    result = parse_json_response(response.content[0].text)

    return {
        "scores": {
            "geometry": geo_score,
            "finishes": fin_score,
            "brand":    brd_score,
            "overall":  overall
        },
        "summary": result.get("summary", ""),
        "geometry": comparison["geometry"],
        "finishes": comparison["finishes"],
        "brand":    comparison["brand"]
    }
