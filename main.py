import base64
import io
import json
import queue
import threading
import zipfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv("/Users/chai/Documents/primax_validator/.env", override=True)

from config import DATA_DIR, CACHE_DIR, RENDERS_OUTPUT_DIR, RENDER_FILES, RENDERS_DIR

app = FastAPI(title="PRiMAX Visualiser")
app.mount("/static",    StaticFiles(directory="static"),          name="static")
app.mount("/generated", StaticFiles(directory=str(RENDERS_OUTPUT_DIR)), name="generated")


# ── SSE progress queue ────────────────────────────────────────────────────────
_progress_q: queue.Queue = queue.Queue()
_pipeline_running = False


@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("static/index.html").read_text()


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
        pdf_path = DATA_DIR / "2D Plan.pdf"
        if pdf_path.exists():
            doc  = fitz.open(str(pdf_path))
            page = doc[0]
            pix  = page.get_pixmap(matrix=fitz.Matrix(3, 3))
            png  = pix.tobytes("png")
            (CACHE_DIR / "floor_plan.png").write_bytes(png)
            preview_b64 = base64.b64encode(png).decode()
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
                print(f"Brand extraction error: {e}")
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
        _progress_q.put({"type": "done", "glb_url": "/generated/model.glb"})
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
    # drain old messages
    while not _progress_q.empty():
        _progress_q.get_nowait()
    threading.Thread(target=_run_pipeline, daemon=True).start()
    return {"started": True}


@app.get("/api/generate/stream")
async def generate_stream():
    async def events():
        while True:
            try:
                item = _progress_q.get(timeout=1)
                yield f"data: {json.dumps(item)}\n\n"
                if item["type"] in ("done", "error"):
                    break
            except queue.Empty:
                yield "data: {\"type\":\"ping\"}\n\n"
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
    img_path = RENDERS_OUTPUT_DIR / "nb_render_enhanced.png"
    glb_path = RENDERS_OUTPUT_DIR / "model.glb"
    plan_path = CACHE_DIR / "floor_plan.png"

    result = {"image": None, "glb_url": None, "plan": None}

    if img_path.exists():
        result["image"] = f"data:image/png;base64,{base64.b64encode(img_path.read_bytes()).decode()}"
    if glb_path.exists():
        result["glb_url"] = "/generated/model.glb"
    if plan_path.exists():
        result["plan"] = f"data:image/png;base64,{base64.b64encode(plan_path.read_bytes()).decode()}"

    return result
