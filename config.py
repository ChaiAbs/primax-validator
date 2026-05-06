import os
from pathlib import Path

# Project root — works both locally and on Render
BASE_DIR = Path(__file__).parent

DATA_DIR = BASE_DIR / "data"

RENDERS_DIR = DATA_DIR / "Renders"
PLAN_3D = DATA_DIR / "3d Plan.png"
PLAN_2D = DATA_DIR / "2D Plan.pdf"

RENDER_FILES = sorted(RENDERS_DIR.glob("*.jpg")) + sorted(RENDERS_DIR.glob("*.jpeg")) if RENDERS_DIR.exists() else []
BRAND_GUIDE = DATA_DIR / "250902_Ascent_Brand Overview_V1.pdf"

MODEL_FAST = "claude-sonnet-4-6"
MODEL_SMART = "claude-sonnet-4-6"

CACHE_DIR = BASE_DIR / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

RENDERS_OUTPUT_DIR = BASE_DIR / ".generated_renders"
RENDERS_OUTPUT_DIR.mkdir(exist_ok=True)
