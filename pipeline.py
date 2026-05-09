import json
import time
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv(override=True)

import anthropic
from agents.geometry_agent import extract_geometry_spec
from agents.spec_agent import extract_project_spec
from agents.brand_agent import extract_brand_spec
from config import CACHE_DIR, RENDERS_OUTPUT_DIR


def _load_cache(name: str) -> dict | None:
    path = CACHE_DIR / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def _save_cache(name: str, data: dict):
    (CACHE_DIR / f"{name}.json").write_text(json.dumps(data, indent=2))


def extract_specs(use_cache: bool = True, cache_brand: bool = False) -> tuple[dict, dict, dict]:
    """
    Extract geometry, finishes and brand specs in parallel.
    Results are cached — subsequent calls return instantly.
    cache_brand=True keeps brand from cache even when use_cache=False.
    """
    geo_cached = _load_cache("geometry") if use_cache else None
    fin_cached = _load_cache("finishes") if use_cache else None
    brd_cached = _load_cache("brand")    if (use_cache or cache_brand) else None

    if geo_cached and fin_cached and brd_cached:
        print("Specs loaded from cache")
        return geo_cached, fin_cached, brd_cached

    client = anthropic.Anthropic()

    def _run_with_retry(fn, name):
        for attempt in range(1, 3):
            try:
                return fn(client)
            except Exception as e:
                print(f"  {name} extraction attempt {attempt} failed: {e} — retrying...", flush=True)
        raise RuntimeError(f"{name} extraction failed after 2 attempts")

    print("Extracting specs in parallel (geometry · finishes · brand)...")
    t0 = time.time()
    tasks = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        if not geo_cached:
            tasks["geometry"] = executor.submit(_run_with_retry, extract_geometry_spec, "geometry")
        if not fin_cached:
            tasks["finishes"] = executor.submit(_run_with_retry, extract_project_spec,  "finishes")
        if not brd_cached:
            tasks["brand"]    = executor.submit(_run_with_retry, extract_brand_spec,    "brand")

        geometry_spec = tasks["geometry"].result() if "geometry" in tasks else geo_cached
        finishes_spec = tasks["finishes"].result() if "finishes" in tasks else fin_cached
        brand_spec    = tasks["brand"].result()    if "brand"    in tasks else brd_cached

    _save_cache("geometry", geometry_spec)
    _save_cache("finishes", finishes_spec)
    _save_cache("brand",    brand_spec)
    print(f"  Specs extracted in {time.time() - t0:.1f}s")
    return geometry_spec, finishes_spec, brand_spec



def run_nb_stage(max_attempts: int = 3) -> dict:
    """
    Stage 1: Extract specs + run NanoBanana x3 in parallel + validate.
    Saves best render to nb_render_enhanced.png and returns it as base64.
    """
    import base64 as _b64
    import shutil
    from services.nanobanana import render_from_floor_plan, _upload_imgbb
    from agents.validator_agent import score_renders
    from main import _stop_flag
    from config import CACHE_DIR

    geometry_spec, finishes_spec, brand_spec = extract_specs(use_cache=False, cache_brand=True)

    if _stop_flag.is_set():
        raise StopIteration("Pipeline stopped by user")

    client = anthropic.Anthropic()

    clean_path = CACHE_DIR / "floor_plan_clean.png"
    fp_path    = clean_path if clean_path.exists() else CACHE_DIR / "floor_plan.png"
    print(f"Uploading floor plan once for {max_attempts} parallel runs...", flush=True)
    floor_plan_url = _upload_imgbb(fp_path)
    print(f"  Floor plan hosted: {floor_plan_url[:60]}...", flush=True)

    _parallel_start = time.time()

    def _run_attempt(attempt):
        t_start = time.time() - _parallel_start
        print(f"[+{t_start:.1f}s] NanoBanana run {attempt} started", flush=True)
        t0 = time.time()
        result_b64, nb_image_url = render_from_floor_plan(
            geometry_spec, finishes_spec, brand_spec,
            floor_plan_url=floor_plan_url
        )
        t_end = time.time() - _parallel_start
        print(f"[+{t_end:.1f}s] NanoBanana run {attempt} done ({time.time() - t0:.1f}s)", flush=True)
        candidate_path = RENDERS_OUTPUT_DIR / f"nb_candidate_{attempt}.png"
        candidate_path.write_bytes(_b64.b64decode(result_b64))
        return (candidate_path, nb_image_url, result_b64)

    print(f"Firing {max_attempts} NanoBanana runs in parallel...", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max_attempts) as executor:
        futures = [executor.submit(_run_attempt, i) for i in range(1, max_attempts + 1)]
        candidates = [f.result() for f in futures]
    print(f"All {max_attempts} runs done in {time.time() - t0:.1f}s total", flush=True)

    if _stop_flag.is_set():
        raise StopIteration("Pipeline stopped by user")

    print(f"Validating {len(candidates)} candidates...", flush=True)
    paths = [c[0] for c in candidates]
    result = score_renders(client, paths, geometry_spec)
    print(f"  Scores: {result}", flush=True)

    best_idx   = result["best"] - 1
    best_path, _, best_b64 = candidates[best_idx]
    print(f"  Best candidate: run {best_idx + 1} (score {result['scores'][best_idx]['total']})", flush=True)

    shutil.copy(best_path, RENDERS_OUTPUT_DIR / "nb_render_enhanced.png")

    return {
        "image": f"data:image/png;base64,{best_b64}",
        "specs": {"geometry": geometry_spec, "finishes": finishes_spec, "brand": brand_spec},
    }


def run_hh_stage() -> dict:
    """
    Stage 2: Send existing nb_render_enhanced.png to Happy Horse → video + snapshot.
    """
    import io as _io
    from services.nanobanana import _upload_imgbb
    from services.happyhorse import generate_video_frame
    from PIL import Image as _Image

    nb_path = RENDERS_OUTPUT_DIR / "nb_render_enhanced.png"
    if not nb_path.exists():
        raise RuntimeError("No NanoBanana render found — run Stage 1 first")

    print("Re-uploading best render for Happy Horse...", flush=True)
    _img = _Image.open(nb_path).convert("RGB")
    _jpg_buf = _io.BytesIO()
    _img.save(_jpg_buf, format="JPEG", quality=95)
    _jpg_path = RENDERS_OUTPUT_DIR / "nb_render_enhanced.jpg"
    _jpg_path.write_bytes(_jpg_buf.getvalue())
    fresh_url = _upload_imgbb(_jpg_path)
    print(f"  Fresh URL: {fresh_url[:60]}...", flush=True)

    print("Sending to Happy Horse...", flush=True)
    frame_path = generate_video_frame(fresh_url, frame_time=3.9)
    video_path = RENDERS_OUTPUT_DIR / "happyhorse.mp4"
    print(f"  Video ready, snapshot saved: {frame_path}", flush=True)

    return {
        "video_path": str(video_path),
        "frame_path": str(frame_path),
    }
