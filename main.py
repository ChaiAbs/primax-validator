import base64
import io
import json
import queue
import threading
import zipfile
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv(override=True)

from config import DATA_DIR, CACHE_DIR, RENDERS_OUTPUT_DIR, RENDER_FILES, RENDERS_DIR

app = FastAPI(title="PRiMAX Visualiser")


def _crop_to_floor_plan(png_bytes: bytes) -> bytes:
    """
    Auto-crop a floor plan PNG to remove any brand/info panel on the right.
    Strategy: scan columns right→left; find the rightmost block of pure-white
    columns (the margin between floor plan and brand panel) — crop just before
    the brand panel content starts to the right of that white gap.
    Falls back to the original if no clear boundary is found.
    """
    import numpy as np
    from PIL import Image

    img  = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    arr  = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]

    gray    = arr.mean(axis=2)      # h x w
    col_std = gray.std(axis=0)      # per-column std

    # "White column" = std < 5 (essentially uniform white margin)
    # Scan right half only; find the rightmost run of white columns followed
    # by non-white content (the brand panel)
    white_threshold = 5.0
    min_gap         = int(w * 0.05)   # gap must be at least 5% of width

    crop_x = w
    in_white = False
    white_start = w

    for x in range(w - 1, w // 3, -1):
        is_white = col_std[x] < white_threshold
        if is_white and not in_white:
            white_start = x
            in_white = True
        elif not is_white and in_white:
            # End of a white run — check it's wide enough to be the margin
            gap_width = white_start - x
            if gap_width >= min_gap:
                crop_x = white_start + 1
                break
            in_white = False

    if crop_x >= w - 10:
        return png_bytes  # no clear boundary found

    cropped = img.crop((0, 0, crop_x, h))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()
app.mount("/static",    StaticFiles(directory="static"),          name="static")
app.mount("/generated", StaticFiles(directory=str(RENDERS_OUTPUT_DIR)), name="generated")
app.mount("/cache",     StaticFiles(directory=str(CACHE_DIR)),    name="cache")


# ── SSE progress queue ────────────────────────────────────────────────────────
_progress_q: queue.Queue = queue.Queue()
_pipeline_running = False
_stop_flag = threading.Event()


@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("static/index.html").read_text()


@app.head("/")
async def index_head():
    return HTMLResponse(content="", status_code=200)


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Upload zip ────────────────────────────────────────────────────────────────
@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = z.namelist()
            found = {"floor_plan": False, "renders": 0, "brand": False}

            errors = []
            for name in names:
                if "__MACOSX" in name or name.startswith("."):
                    continue
                lower = name.lower()
                stem  = Path(name).name
                if not stem:
                    continue

                try:
                    if lower.endswith(".pdf") and any(k in lower for k in ("2d", "floor", "plan")):
                        DATA_DIR.mkdir(parents=True, exist_ok=True)
                        (DATA_DIR / "2D Plan.pdf").write_bytes(z.read(name))
                        found["floor_plan"] = True

                    elif lower.endswith(".pdf"):
                        DATA_DIR.mkdir(parents=True, exist_ok=True)
                        (DATA_DIR / "250902_Ascent_Brand Overview_V1.pdf").write_bytes(z.read(name))
                        found["brand"] = True

                    elif lower.endswith(".png") and "3d" in lower:
                        DATA_DIR.mkdir(parents=True, exist_ok=True)
                        (DATA_DIR / "3d Plan.png").write_bytes(z.read(name))

                    elif lower.endswith((".jpg", ".jpeg")):
                        RENDERS_DIR.mkdir(parents=True, exist_ok=True)
                        (RENDERS_DIR / stem).write_bytes(z.read(name))
                        found["renders"] += 1

                    elif lower.endswith(".zip") and "render" in lower:
                        RENDERS_DIR.mkdir(parents=True, exist_ok=True)
                        with zipfile.ZipFile(io.BytesIO(z.read(name))) as nz:
                            for nname in nz.namelist():
                                if "__MACOSX" in nname:
                                    continue
                                nstem = Path(nname).name
                                if nstem and nname.lower().endswith((".jpg", ".jpeg")):
                                    (RENDERS_DIR / nstem).write_bytes(nz.read(nname))
                                    found["renders"] += 1

                except Exception as e:
                    errors.append(f"{name}: {e}")

        # Convert floor plan PDF → PNG for preview + NanoBanana
        import fitz
        import numpy as np
        from PIL import Image

        pdf_path = DATA_DIR / "2D Plan.pdf"
        if pdf_path.exists():
            doc  = fitz.open(str(pdf_path))
            page = doc[0]
            pix  = page.get_pixmap(matrix=fitz.Matrix(3, 3))
            png  = pix.tobytes("png")
            # Save full version for preview
            (CACHE_DIR / "floor_plan.png").write_bytes(png)
            preview_b64 = base64.b64encode(png).decode()
            # Save cropped version for NanoBanana
            cropped = _crop_to_floor_plan(png)
            (CACHE_DIR / "floor_plan_clean.png").write_bytes(cropped)
        else:
            preview_b64 = None

        # Clear stale spec cache
        for f in CACHE_DIR.glob("*.json"):
            f.unlink()

        # Kick off brand extraction in background
        def _extract_brand():
            try:
                import anthropic
                from agents.brand_agent import extract_brand_spec
                client = anthropic.Anthropic()
                brand  = extract_brand_spec(client)
                (CACHE_DIR / "brand.json").write_text(json.dumps(brand))
            except Exception as e:
                print(f"Brand extraction error: {e}", flush=True)
                # Write error state so UI stops polling
                (CACHE_DIR / "brand.json").write_text(json.dumps({"error": str(e)}))
        threading.Thread(target=_extract_brand, daemon=True).start()

        return {
            "ok":      True,
            "found":   found,
            "errors":  errors,
            "preview": f"data:image/png;base64,{preview_b64}" if preview_b64 else None,
        }

    except zipfile.BadZipFile:
        return JSONResponse({"error": "Invalid zip file"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Generate (SSE stream) ─────────────────────────────────────────────────────
def _run_pipeline():
    global _pipeline_running
    import builtins
    _orig_print = builtins.print

    def _p(*args, **kwargs):
        msg = " ".join(str(a) for a in args)
        _progress_q.put({"type": "log", "msg": msg})
        _orig_print(*args, **kwargs)

    builtins.print = _p
    try:
        from pipeline import run_render
        result = run_render()
        _progress_q.put({
            "type":       "done",
            "video_url":  "/generated/happyhorse.mp4",
            "frame_url":  "/generated/happyhorse_frame.png",
        })
    except StopIteration:
        _progress_q.put({"type": "stopped"})
    except Exception as e:
        _progress_q.put({"type": "error", "msg": str(e)})
    finally:
        builtins.print = _orig_print
        _pipeline_running = False


@app.post("/api/generate/start")
async def generate_start():
    global _pipeline_running
    if _pipeline_running:
        return JSONResponse({"error": "Already running"}, status_code=409)
    _pipeline_running = True
    _stop_flag.clear()
    # drain old messages
    while not _progress_q.empty():
        _progress_q.get_nowait()
    threading.Thread(target=_run_pipeline, daemon=True).start()
    return {"started": True}


@app.post("/api/generate/stop")
async def generate_stop():
    _stop_flag.set()
    return {"stopping": True}


@app.get("/api/generate/stream")
async def generate_stream(request: Request):
    async def events():
        while True:
            if await request.is_disconnected():
                break
            try:
                item = _progress_q.get(timeout=1)
                try:
                    yield f"data: {json.dumps(item)}\n\n"
                except Exception:
                    break
                if item["type"] in ("done", "error", "stopped"):
                    break
            except queue.Empty:
                try:
                    yield "data: {\"type\":\"ping\"}\n\n"
                except Exception:
                    break
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Results ───────────────────────────────────────────────────────────────────
@app.get("/api/renders")
async def get_renders():
    images = []
    if RENDERS_DIR.exists():
        for path in sorted(RENDERS_DIR.glob("*.jpg")) + sorted(RENDERS_DIR.glob("*.jpeg")):
            images.append(f"data:image/jpeg;base64,{base64.b64encode(path.read_bytes()).decode()}")
    return {"images": images}


@app.get("/api/brand")
async def get_brand():
    p = CACHE_DIR / "brand.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


@app.get("/api/results")
async def get_results():
    img_path   = RENDERS_OUTPUT_DIR / "nb_render_enhanced.png"
    video_path = RENDERS_OUTPUT_DIR / "happyhorse.mp4"
    frame_path = RENDERS_OUTPUT_DIR / "happyhorse_frame.png"
    plan_path  = CACHE_DIR / "floor_plan.png"

    result = {"image": None, "video_url": None, "frame_url": None, "plan": None}

    if img_path.exists():
        result["image"] = f"data:image/png;base64,{base64.b64encode(img_path.read_bytes()).decode()}"
    if video_path.exists():
        result["video_url"] = "/generated/happyhorse.mp4"
    if frame_path.exists():
        result["frame_url"] = "/generated/happyhorse_frame.png"
    if plan_path.exists():
        result["plan"] = f"data:image/png;base64,{base64.b64encode(plan_path.read_bytes()).decode()}"

    return result


@app.get("/api/download/snapshot")
async def download_snapshot(count: int = 1):
    frame_path = RENDERS_OUTPUT_DIR / "happyhorse_frame.png"
    if not frame_path.exists():
        return JSONResponse({"error": "No snapshot available"}, status_code=404)

    img_bytes = frame_path.read_bytes()

    if count <= 1:
        return StreamingResponse(
            io.BytesIO(img_bytes),
            media_type="image/png",
            headers={"Content-Disposition": "attachment; filename=3d_render.png"}
        )

    # Zip N copies
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(1, count + 1):
            zf.writestr(f"3d_render_{i:02d}.png", img_bytes)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=3d_renders_{count}x.zip"}
    )
