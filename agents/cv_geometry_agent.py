"""
OpenCV geometry agent.

Two functions:
  get_plan_bounds  — pixel bounding box of the floor plan in the image
  extract_outline  — apartment outer boundary polygon in metres,
                     extracted by flood-filling from a known interior seed
                     point and tracing the contour of the filled region.
"""

import cv2
import numpy as np
from pathlib import Path


def get_plan_bounds(image_path: Path) -> dict:
    """
    Returns pixel bounding box of the floor plan within the image.
    {
      "x1": int, "y1": int,   # top-left of plan area
      "x2": int, "y2": int,   # bottom-right
      "img_w": int, "img_h": int
    }
    """
    img  = cv2.imread(str(image_path))
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # All dark pixels (walls + text) — bounding box = plan extents
    _, dark = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV)

    ys, xs = np.where(dark > 0)
    if len(ys) == 0:
        return {"x1": 0, "y1": 0, "x2": w, "y2": h, "img_w": w, "img_h": h}

    pad = 8
    return {
        "x1":    max(0, int(xs.min()) - pad),
        "y1":    max(0, int(ys.min()) - pad),
        "x2":    min(w, int(xs.max()) + pad),
        "y2":    min(h, int(ys.max()) + pad),
        "img_w": w,
        "img_h": h,
    }


def extract_outline(image_path: Path, plan_bounds: dict,
                    plan_w_m: float = 9.8, plan_d_m: float = 11.55,
                    seed_x_m: float = 1.9, seed_y_m: float = 9.9,
                    simplify_tolerance: float = 0.8) -> list[list[float]]:
    """
    Extract the apartment outer boundary as a polygon in metres.

    Algorithm:
      1. Crop to plan area, threshold to get wall pixels
      2. Dilate heavily to seal door/window openings
      3. Flood-fill from a known interior seed point
      4. Trace the contour of the filled region
      5. Simplify with Shapely to remove collinear noise

    seed_x_m / seed_y_m  — a point known to be inside the apartment
                           (default: centre of DINING, works for this plan)
    simplify_tolerance    — metres; controls how much the polygon is smoothed

    Returns [[x, y], ...] in metres, y-axis pointing up, origin bottom-left.
    """
    img  = cv2.imread(str(image_path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    bx1, by1 = plan_bounds["x1"], plan_bounds["y1"]
    bx2, by2 = plan_bounds["x2"], plan_bounds["y2"]
    px_per_m  = (bx2 - bx1) / plan_w_m

    # Work in cropped plan coordinates
    crop = gray[by1:by2, bx1:bx2]
    ch, cw = crop.shape

    _, walls = cv2.threshold(crop, 80, 255, cv2.THRESH_BINARY_INV)

    # Dilate to seal door openings (0.9 m ≈ 125 px; 40 iters × 3 px = 120 px)
    sealed   = cv2.dilate(walls, np.ones((3, 3), np.uint8), iterations=40)
    passable = cv2.bitwise_not(sealed)

    # Seed pixel in cropped image coords (y-down)
    sx = int(seed_x_m * px_per_m)
    sy = int((plan_d_m - seed_y_m) * px_per_m)
    sx = max(1, min(cw - 2, sx))
    sy = max(1, min(ch - 2, sy))

    interior = passable.copy()
    cv2.floodFill(interior, np.zeros((ch + 2, cw + 2), np.uint8), (sx, sy), 128)
    region = np.where(interior == 128, 255, 0).astype(np.uint8)

    contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []
    main  = max(contours, key=cv2.contourArea)
    approx = cv2.approxPolyDP(main, 10, True)

    # Convert pixel vertices → metres (y-flipped)
    raw_pts = []
    for pt in approx:
        px, py = pt[0]
        xm = px / px_per_m
        ym = plan_d_m - py / px_per_m
        raw_pts.append((xm, ym))

    # Shapely simplify to remove collinear / near-duplicate vertices
    from shapely.geometry import Polygon
    poly      = Polygon(raw_pts)
    simplified = poly.simplify(simplify_tolerance, preserve_topology=True)
    coords    = list(simplified.exterior.coords)[:-1]  # drop closing duplicate

    return [[round(x, 3), round(y, 3)] for x, y in coords]


def visualise(image_path: Path, rooms: list, bounds: dict, out_path: Path):
    """Draw coloured bounding boxes for each enriched room."""
    img = cv2.imread(str(image_path))
    colours = [(220,80,80),(80,200,80),(80,80,220),(200,200,60),
               (200,80,200),(80,200,200),(160,100,40),(40,160,100),
               (160,160,80),(80,160,160),(160,80,160),(100,40,160)]
    for i, r in enumerate(rooms):
        col = colours[i % len(colours)]
        bx, by = r.get("bbox_px", [0,0,0,0])[:2]
        bw, bh = r.get("bbox_px", [0,0,0,0])[2:]
        cv2.rectangle(img, (bx, by), (bx+bw, by+bh), col, 3)
        label = r.get("name", f"R{i}")
        cv2.putText(img, label, (bx+4, by+22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2)
    cv2.imwrite(str(out_path), img)
