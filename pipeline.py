import json
import time
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv("/Users/chai/Documents/primax_validator/.env", override=True)

import anthropic
from agents.geometry_agent import extract_geometry_spec
from agents.spec_agent import extract_project_spec
from agents.brand_agent import extract_brand_spec
from agents.generation_agent import generate_candidates, select_candidate
from agents.layout_agent import extract_layout
from config import CACHE_DIR, RENDERS_OUTPUT_DIR


def _load_cache(name: str) -> dict | None:
    path = CACHE_DIR / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def _save_cache(name: str, data: dict):
    (CACHE_DIR / f"{name}.json").write_text(json.dumps(data, indent=2))


def extract_specs(use_cache: bool = True) -> tuple[dict, dict, dict]:
    """
    Extract geometry, finishes and brand specs in parallel.
    Results are cached — subsequent calls return instantly.
    """
    geo_cached = _load_cache("geometry") if use_cache else None
    fin_cached = _load_cache("finishes") if use_cache else None
    brd_cached = _load_cache("brand")    if use_cache else None

    if geo_cached and fin_cached and brd_cached:
        print("Specs loaded from cache")
        return geo_cached, fin_cached, brd_cached

    client = anthropic.Anthropic()
    print("Extracting specs in parallel (geometry · finishes · brand)...")
    t0 = time.time()
    tasks = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        if not geo_cached:
            tasks["geometry"] = executor.submit(extract_geometry_spec, client)
        if not fin_cached:
            tasks["finishes"] = executor.submit(extract_project_spec,  client)
        if not brd_cached:
            tasks["brand"]    = executor.submit(extract_brand_spec,    client)

        geometry_spec = tasks["geometry"].result() if "geometry" in tasks else geo_cached
        finishes_spec = tasks["finishes"].result() if "finishes" in tasks else fin_cached
        brand_spec    = tasks["brand"].result()    if "brand"    in tasks else brd_cached

    _save_cache("geometry", geometry_spec)
    _save_cache("finishes", finishes_spec)
    _save_cache("brand",    brand_spec)
    print(f"  Specs extracted in {time.time() - t0:.1f}s")
    return geometry_spec, finishes_spec, brand_spec


def run_generation(use_cache: bool = True) -> dict:
    """
    Step 1 — extract specs (parallel, cached)
    Step 2 — build prompt + generate isometric render via NanoBanana
    Returns {prompt, task_id, image_url, path, filename}.
    """
    t0 = time.time()
    geometry_spec, finishes_spec, brand_spec = extract_specs(use_cache)

    print(f"Generating {3} candidates in parallel via NanoBanana...")
    t1 = time.time()
    result = generate_candidates(geometry_spec, finishes_spec, brand_spec)
    print(f"  Generation done in {time.time() - t1:.1f}s")
    print(f"Total: {time.time() - t0:.1f}s")
    result["specs"] = {"geometry": geometry_spec, "finishes": finishes_spec, "brand": brand_spec}
    return result


def run_select(index: int) -> dict:
    """Lock in the user's chosen candidate as the canonical output."""
    from agents.generation_agent import select_candidate
    geo = json.loads((CACHE_DIR / "geometry.json").read_text())
    fin = json.loads((CACHE_DIR / "finishes.json").read_text())
    brd = json.loads((CACHE_DIR / "brand.json").read_text())
    select_candidate(index, geo, fin, brd)
    return {"selected": index}


def _room_type(name: str) -> str:
    n = name.lower()
    if any(x in n for x in ["bath", "ensuite", "laundry", "wc", "toilet"]):
        return "wet"
    if "kitchen" in n:
        return "kitchen"
    if any(x in n for x in ["bed", "master"]):
        return "bedroom"
    if "living" in n or "lounge" in n:
        return "living"
    if "dining" in n:
        return "dining"
    if any(x in n for x in ["terrace", "balcony", "deck"]):
        return "external"
    if "store" in n or "storage" in n:
        return "storage"
    return "generic"


def build_scene(use_cache: bool = True) -> dict:
    """
    Extract specs + layout, merge into a Three.js-ready scene description.
    Returns {rooms, finishes, bounds, specs}.
    """
    geometry_spec, finishes_spec, brand_spec = extract_specs(use_cache)

    print("Extracting room layout from floor plan...")
    layout = extract_layout(geometry_spec)

    # Normalise names for matching (strip spaces, lowercase)
    def _norm(s): return s.lower().replace(" ", "")
    pos_map = {_norm(r["name"]): r for r in layout["rooms"]}
    rooms = []
    for room in geometry_spec["rooms"]:
        name = room["name"]
        pos  = pos_map.get(_norm(name), {})
        rooms.append({
            "name":       name,
            "x_m":        pos.get("x_m", pos.get("x", 0.0)),
            "y_m":        pos.get("y_m", pos.get("y", 0.0)),
            "width_m":    room["width_m"],
            "depth_m":    room["depth_m"],
            "is_external": room.get("type") == "external",
            "type":       _room_type(name),
        })

    max_x = max(r["x_m"] + r["width_m"] for r in rooms)
    max_y = max(r["y_m"] + r["depth_m"] for r in rooms)

    return {
        "rooms":    rooms,
        "finishes": finishes_spec.get("finishes", finishes_spec),
        "bounds":   {"width_m": max_x, "depth_m": max_y},
        "specs": {
            "geometry": geometry_spec,
            "finishes": finishes_spec,
            "brand":    brand_spec,
        },
    }


def run_render() -> dict:
    """Extract specs (cached) then render floor plan via NanoBanana image-to-image."""
    from agents.refine_agent import render_from_floor_plan
    geometry_spec, finishes_spec, brand_spec = extract_specs()
    print("Sending floor plan to NanoBanana...", flush=True)
    t0 = time.time()
    result_b64 = render_from_floor_plan(geometry_spec, finishes_spec, brand_spec)
    print(f"  NanoBanana done in {time.time() - t0:.1f}s", flush=True)
    return {
        "image": f"data:image/png;base64,{result_b64}",
        "specs": {"geometry": geometry_spec, "finishes": finishes_spec, "brand": brand_spec},
    }
