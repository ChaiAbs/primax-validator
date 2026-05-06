"""
Quick test: run 3 NanoBanana renders in parallel, validate with Claude Vision,
print scores and show which was picked as best.
"""
import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dotenv import load_dotenv

load_dotenv("/Users/chai/Documents/primax_validator/.env", override=True)

import anthropic
from agents.refine_agent import _upload_imgbb, render_from_floor_plan, build_render_prompt
from agents.validator_agent import score_renders
from config import CACHE_DIR, RENDERS_OUTPUT_DIR

# Load cached specs
geometry_spec = json.loads((CACHE_DIR / "geometry.json").read_text())
finishes_spec = json.loads((CACHE_DIR / "finishes.json").read_text())
brand_spec    = json.loads((CACHE_DIR / "brand.json").read_text())

print("=== PROMPT BEING SENT TO NANOBANANA ===")
prompt = build_render_prompt(geometry_spec, finishes_spec, brand_spec)
print(prompt)
print()

# Upload floor plan once
clean_path = CACHE_DIR / "floor_plan_clean.png"
fp_path    = clean_path if clean_path.exists() else CACHE_DIR / "floor_plan.png"
print("Uploading floor plan once...")
floor_plan_url = _upload_imgbb(fp_path)
print(f"  Hosted: {floor_plan_url[:60]}...")
print()

_start = time.time()

def _run(attempt):
    t0 = time.time() - _start
    print(f"[+{t0:.1f}s] Run {attempt} started")
    result_b64, nb_url = render_from_floor_plan(
        geometry_spec, finishes_spec, brand_spec,
        floor_plan_url=floor_plan_url
    )
    t1 = time.time() - _start
    print(f"[+{t1:.1f}s] Run {attempt} done")
    path = RENDERS_OUTPUT_DIR / f"test_candidate_{attempt}.png"
    path.write_bytes(base64.b64decode(result_b64))
    return path, nb_url

print("Firing 3 runs in parallel...")
with ThreadPoolExecutor(max_workers=3) as ex:
    futures = [ex.submit(_run, i) for i in range(1, 4)]
    results = [f.result() for f in futures]

paths = [r[0] for r in results]
print(f"\nAll done in {time.time() - _start:.1f}s")
print()

print("=== VALIDATOR SCORES ===")
client = anthropic.Anthropic()
scores = score_renders(client, paths, geometry_spec)
print(json.dumps(scores, indent=2))
print()
print(f">>> BEST: Run {scores['best']}")
print()
for i, s in enumerate(scores['scores'], 1):
    marker = " <<<" if i == scores['best'] else ""
    print(f"  Run {i}: structural={s['structural']}/10  hallucinations={s['hallucinations']}/10  total={s['total']}/20  | {s.get('notes','')}{marker}")

print()
print(f"Outputs saved to: {RENDERS_OUTPUT_DIR}/test_candidate_1.png / _2.png / _3.png")
