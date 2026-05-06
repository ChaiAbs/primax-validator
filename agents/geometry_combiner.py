"""
Geometry combiner.

Takes graph-walk positions + semantic room data, applies a uniform scale
to fit the plan envelope, then computes the apartment outline polygon
(Shapely union of all room rectangles) for the Three.js renderer.

Output includes:
  rooms      — list of enriched room dicts with x_m, y_m, width_m, depth_m
  bounds     — actual {width_m, depth_m} of the assembled layout
  outline_m  — apartment perimeter as [[x, y], ...] in metres (for ExtrudeGeometry)
"""

from shapely.geometry import box as shapely_box
from shapely.ops import unary_union


def combine(plan_bounds: dict, semantic_data: dict,
            walk_positions: list[dict],
            outline_m: list[list[float]] | None = None) -> dict:
    """
    plan_bounds    — from cv_geometry_agent.get_plan_bounds()
    semantic_data  — from semantic_agent.extract_semantics()
    walk_positions — from graph_walk.walk(): [{name, x_m, y_m}]
    """
    plan_w = float(semantic_data.get("plan_width_m", 9.8))
    plan_d = float(semantic_data.get("plan_depth_m", 11.55))

    x1_px    = plan_bounds["x1"]
    y1_px    = plan_bounds["y1"]
    px_scale = (plan_bounds["x2"] - x1_px) / plan_w

    pos_map = {p["name"]: p for p in walk_positions}

    rooms = []
    for sem in semantic_data.get("rooms", []):
        name = sem["name"]
        w    = float(sem.get("width_m", 1))
        d    = float(sem.get("depth_m", 1))

        if name in pos_map:
            x_m = float(pos_map[name]["x_m"])
            y_m = float(pos_map[name]["y_m"])
        else:
            # Pixel-centroid fallback for rooms not reached by the graph walk
            lbl_px = float(sem.get("label_px", x1_px + (plan_bounds["x2"] - x1_px) / 2))
            lbl_py = float(sem.get("label_py", y1_px + (plan_bounds["y2"] - y1_px) / 2))
            x_m = (lbl_px - x1_px) / px_scale - w / 2
            y_m = plan_d - (lbl_py - y1_px) / px_scale - d / 2

        rooms.append({
            "name":        name,
            "type":        sem.get("type", "internal"),
            "is_external": sem.get("type") == "external",
            "width_m":     w,
            "depth_m":     d,
            "area_m2":     sem.get("area_m2") or round(w * d, 2),
            "x_m":         x_m,
            "y_m":         y_m,
        })

    # Uniform scale so the layout fits within the plan envelope.
    # Applied to both positions AND dimensions so adjacency is preserved.
    max_right = max(r["x_m"] + r["width_m"] for r in rooms)
    max_top   = max(r["y_m"] + r["depth_m"] for r in rooms)
    sx = plan_w / max_right if max_right > plan_w else 1.0
    sy = plan_d / max_top   if max_top   > plan_d else 1.0

    if sx < 1.0 or sy < 1.0:
        print(f"  Scale to fit: sx={sx:.3f}  sy={sy:.3f}")
        for r in rooms:
            r["x_m"]     *= sx
            r["y_m"]     *= sy
            r["width_m"] *= sx
            r["depth_m"] *= sy
            r["area_m2"]  = round(r["width_m"] * r["depth_m"], 2)

    # Round and add derived fields + pixel bbox for debug viz
    for r in rooms:
        r["x_m"]     = round(r["x_m"],     3)
        r["y_m"]     = round(r["y_m"],     3)
        r["width_m"] = round(r["width_m"], 3)
        r["depth_m"] = round(r["depth_m"], 3)
        r["cx_m"]    = round(r["x_m"] + r["width_m"] / 2, 3)
        r["cy_m"]    = round(r["y_m"] + r["depth_m"] / 2, 3)
        bx = int(x1_px + r["x_m"] * px_scale)
        by = int(y1_px + (plan_d - r["y_m"] - r["depth_m"]) * px_scale)
        r["bbox_px"] = [bx, by, int(r["width_m"] * px_scale), int(r["depth_m"] * px_scale)]

    rooms.sort(key=lambda r: (-r["y_m"], r["x_m"]))

    if outline_m:
        outline_pts = outline_m
    else:
        # Fallback: Shapely union of all room rectangles
        polys   = [shapely_box(r["x_m"], r["y_m"],
                               r["x_m"] + r["width_m"],
                               r["y_m"] + r["depth_m"]) for r in rooms]
        union = unary_union(polys)
        from shapely.geometry import MultiPolygon
        if isinstance(union, MultiPolygon):
            union = max(union.geoms, key=lambda p: p.area)
        outline_pts = [[round(x, 3), round(y, 3)]
                       for x, y in list(union.exterior.coords)[:-1]]

    max_x = max(r["x_m"] + r["width_m"] for r in rooms)
    max_y = max(r["y_m"] + r["depth_m"] for r in rooms)

    print(f"  Outline: {len(outline_pts)} vertices  "
          f"bounds: {round(max_x,2)}m × {round(max_y,2)}m")

    return {
        "rooms":          rooms,
        "bounds":         {"width_m": round(max_x, 2), "depth_m": round(max_y, 2)},
        "outline_m":      outline_pts,
        "plan_bounds_px": plan_bounds,
    }
