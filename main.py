import base64
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv

load_dotenv("/Users/chai/Documents/primax_validator/.env", override=True)

from pipeline import run_generation, run_select, build_scene, run_render
from config import RENDER_FILES, RENDERS_OUTPUT_DIR

app = FastAPI(title="PRiMAX 3D Generator")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html") as f:
        return f.read()


@app.get("/api/scene")
async def get_scene():
    try:
        return JSONResponse(content=build_scene())
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/api/render")
async def render():
    try:
        result = run_render()
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/api/generate")
async def generate():
    try:
        result = run_generation()
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/api/select/{index}")
async def select(index: int):
    try:
        result = run_select(index)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/api/images/candidates")
async def get_candidates():
    candidate_dir = RENDERS_OUTPUT_DIR / "candidates"
    images = []
    for path in sorted(candidate_dir.glob("candidate_*.png")):
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        images.append({"index": int(path.stem.split("_")[1]), "image": f"data:image/png;base64,{data}"})
    return {"candidates": images}


@app.post("/api/save_canvas")
async def save_canvas(request: Request):
    body = await request.json()
    import base64
    raw = body["image"].split(",")[-1]
    path = RENDERS_OUTPUT_DIR / "threejs_render.png"
    path.write_bytes(base64.b64decode(raw))
    return {"saved": str(path)}


@app.get("/api/images/renders")
async def get_renders():
    renders = []
    for path in RENDER_FILES:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        ext  = path.suffix.lower().replace(".", "")
        mime = "jpeg" if ext in ("jpg", "jpeg") else ext
        renders.append({"name": path.name, "image": f"data:image/{mime};base64,{data}"})
    return {"renders": renders}
