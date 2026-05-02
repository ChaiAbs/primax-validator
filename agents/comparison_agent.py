import anthropic
import base64
import json
from pathlib import Path
from config import PLAN_3D, MODEL_FAST
from agents.utils import parse_json_response


def _encode_3d() -> tuple[str, str]:
    with open(PLAN_3D, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8"), "image/png"


def _compare(client: anthropic.Anthropic, dimension: str, spec: dict, prompt_detail: str) -> dict:
    data, media_type = _encode_3d()
    prompt = f"""You are validating a generated 3D floor plan on one dimension only: {dimension.upper()}.

SPEC:
{json.dumps(spec, indent=2)}

{prompt_detail}

Be concise. Return ONLY valid JSON:
{{
  "failures": [{{"element": "", "expected": "", "found": "", "severity": "high|medium|low"}}],
  "observations": [{{"element": "", "spec_hex": "", "observed_hex": "", "note": ""}}],
  "passing": [],
  "score": 0
}}"""

    response = client.messages.create(
        model=MODEL_FAST,
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                {"type": "text", "text": prompt}
            ]
        }]
    )
    return parse_json_response(response.content[0].text)


def compare_geometry(client: anthropic.Anthropic, geometry_spec: dict) -> dict:
    return _compare(
        client, "geometry", geometry_spec,
        "Check: correct rooms visible, spatial relationships, proportions match labeled dimensions. "
        "For observations: note layout deviations without hex values."
    )


def compare_finishes(client: anthropic.Anthropic, finishes_spec: dict) -> dict:
    spec = finishes_spec.get("finishes", finishes_spec)
    return _compare(
        client, "finishes", spec,
        "Check: floor material and tone, wall colour, kitchen cabinets, benchtop, window/door frames, "
        "skirting, ceiling, architectural details. "
        "For tonal observations include spec_hex and observed_hex."
    )


def compare_brand(client: anthropic.Anthropic, brand_spec: dict) -> dict:
    return _compare(
        client, "brand", brand_spec,
        "Check: mood and atmosphere, accent colour palette, lighting feel, staging approach, "
        "overall premium positioning. "
        "For observations: describe the gap in plain language, no hex values needed."
    )


def compare_against_specs(
    client: anthropic.Anthropic,
    geometry_spec: dict,
    finishes_spec: dict,
    brand_spec: dict
) -> dict:
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as executor:
        geo_f = executor.submit(compare_geometry, client, geometry_spec)
        fin_f = executor.submit(compare_finishes, client, finishes_spec)
        brd_f = executor.submit(compare_brand,    client, brand_spec)
        return {
            "geometry": geo_f.result(),
            "finishes": fin_f.result(),
            "brand":    brd_f.result()
        }
