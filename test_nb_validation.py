"""
Test: crop → NanoBanana x3 → validate → print scores + save images
"""
import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=True)

import anthropic
from services.nanobanana import render_from_floor_plan, _upload_imgbb
from agents.validator_agent import score_renders
from config import CACHE_DIR, RENDERS_OUTPUT_DIR

RENDERS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Load specs ────────────────────────────────────────────────────────────────
print("Loading cached specs...")
geometry_spec = json.loads((CACHE_DIR / "geometry.json").read_text())
finishes_spec = json.loads((CACHE_DIR / "finishes.json").read_text())
brand_spec    = json.loads((CACHE_DIR / "brand.json").read_text())

# ── Upload floor plan once ────────────────────────────────────────────────────
clean_path = CACHE_DIR / "floor_plan_clean.png"
fp_path    = clean_path if clean_path.exists() else CACHE_DIR / "floor_plan.png"
print(f"Uploading floor plan: {fp_path.name}")
floor_plan_url = _upload_imgbb(fp_path)
print(f"  Hosted: {floor_plan_url[:70]}...")

# ── 3x NanoBanana in parallel ─────────────────────────────────────────────────
def _run(attempt):
    print(f"  NanoBanana run {attempt} started", flush=True)
    t0 = time.time()
    result_b64, _ = render_from_floor_plan(
        geometry_spec, finishes_spec, brand_spec,
        floor_plan_url=floor_plan_url,
    )
    out_path = RENDERS_OUTPUT_DIR / f"test_candidate_{attempt}.png"
    out_path.write_bytes(base64.b64decode(result_b64))
    print(f"  NanoBanana run {attempt} done in {time.time()-t0:.1f}s → {out_path.name}", flush=True)
    return out_path

print("\nFiring 3 NanoBanana runs in parallel...")
t0 = time.time()
with ThreadPoolExecutor(max_workers=3) as ex:
    futures = [ex.submit(_run, i) for i in range(1, 4)]
    paths   = [f.result() for f in futures]
print(f"All done in {time.time()-t0:.1f}s\n")

# ── Validate ──────────────────────────────────────────────────────────────────
client = anthropic.Anthropic()
print("Validating candidates with Claude Vision...")
result = score_renders(client, paths, geometry_spec)

print("\n── SCORES ─────────────────────────────────────────────")
for i, s in enumerate(result["scores"], 1):
    print(f"  Run {i}: structural={s['structural']}  hallucinations={s['hallucinations']}  total={s['total']}")
print(f"\n  ★ Best: Run {result['best']}")
print("───────────────────────────────────────────────────────")
print(f"\nImages saved to: {RENDERS_OUTPUT_DIR}")
for p in paths:
    print(f"  {p}")
