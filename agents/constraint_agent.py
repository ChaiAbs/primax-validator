"""
Constraint-based room position solver.

Given room dimensions + an adjacency graph, asks Claude to derive
globally-consistent (x_m, y_m) positions that satisfy:
  - All rooms fit within plan_width_m × plan_depth_m
  - Adjacent rooms share walls exactly (no gaps, no overlaps)
  - Room dimensions are preserved; if labeled widths sum > plan width,
    rooms are scaled proportionally while preserving the layout graph.

This replaces pixel-centroid positioning (geometry_combiner's default),
which accumulates ~2m error when labeled dimensions are inconsistent
with the plan's actual pixel extents.
"""

import anthropic
from agents.utils import parse_json_response
from config import MODEL_SMART


def solve_positions(
    rooms: list[dict],
    adjacency: list[dict],
    plan_width_m: float,
    plan_depth_m: float,
) -> list[dict]:
    """
    rooms     — list of {name, width_m, depth_m, ...}
    adjacency — list of {room_a, room_b, shared_edge}
                shared_edge in {"right", "left", "top", "bottom"}
                (from room_a's perspective, see semantic_agent docstring)

    Returns list of {name, x_m, y_m} — bottom-left corner in metres,
    coordinate origin at bottom-left of plan, y-axis pointing up.
    Returns [] if Claude cannot produce a valid solution.
    """
    client = anthropic.Anthropic()

    room_lines = "\n".join(
        f"  {r['name']}: width={r['width_m']}m  depth={r['depth_m']}m"
        for r in rooms
    )

    if adjacency:
        adj_lines = "\n".join(
            f"  {a['room_a']} [{a['shared_edge']} wall] → {a['room_b']}"
            for a in adjacency
        )
    else:
        adj_lines = "  (none provided — use label pixel positions as a guide)"

    names_csv = ", ".join(r["name"] for r in rooms)

    prompt = f"""You are a spatial constraint solver for residential floor plans.

## Plan envelope
  Width : {plan_width_m} m  (x-axis, left → right)
  Depth : {plan_depth_m} m  (y-axis, bottom → top)
  Origin: (0, 0) at bottom-left corner of plan.

## Rooms  (name: width × depth)
{room_lines}

## Adjacency graph  (shared_edge is from room_a's perspective)
{adj_lines}

## Your task
Assign a bottom-left corner position (x_m, y_m) to every room so that:

1. No room exceeds the plan envelope:
     x_m ≥ 0,  x_m + width_m ≤ {plan_width_m}
     y_m ≥ 0,  y_m + depth_m ≤ {plan_depth_m}

2. Adjacency constraints are honoured exactly:
     shared_edge "right"  → room_a.x_m + room_a.width_m = room_b.x_m
     shared_edge "left"   → room_b.x_m + room_b.width_m = room_a.x_m
     shared_edge "top"    → room_a.y_m + room_a.depth_m = room_b.y_m
     shared_edge "bottom" → room_b.y_m + room_b.depth_m = room_a.y_m

3. No two rooms overlap.

4. If labeled dimensions are inconsistent (e.g., widths sum > {plan_width_m} m),
   scale the affected rooms proportionally along that axis so they fit,
   preserving the topology of the adjacency graph.

Work through the constraints row-by-row / column-by-column before writing
your answer. Anchor the first room at x=0 or y=0 as appropriate, then
place neighbors using the adjacency edges.

Return ONLY valid JSON — no markdown, no explanation outside the JSON:
{{
  "rooms": [
    {{"name": "DINING", "x_m": 0.0, "y_m": 7.55}},
    ...
  ]
}}

Include ALL {len(rooms)} rooms: {names_csv}"""

    for attempt in range(2):
      try:
        response = client.messages.create(
            model=MODEL_SMART,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text
        result = parse_json_response(raw)
        positions = result.get("rooms", [])

        # Sanity check — warn on missing rooms
        solved_names = {p["name"] for p in positions}
        expected_names = {r["name"] for r in rooms}
        missing = expected_names - solved_names
        if missing:
            print(f"  [constraint_agent] WARNING: missing positions for {missing}")

        # Build dim lookup for bounds enforcement
        dim = {r["name"]: (float(r["width_m"]), float(r["depth_m"])) for r in rooms}

        # Clamp to plan bounds via proportional scaling if any room overflows
        positions = _clamp_to_bounds(positions, dim, plan_width_m, plan_depth_m)

        return positions

      except Exception as e:
        if attempt == 0:
            print(f"  [constraint_agent] attempt 1 failed ({e}), retrying...")
        else:
            print(f"  [constraint_agent] ERROR: {e} — falling back to pixel centroids")
            return []


def _clamp_to_bounds(
    positions: list[dict],
    dim: dict[str, tuple[float, float]],
    plan_w: float,
    plan_d: float,
) -> list[dict]:
    """
    If any room's right/top edge exceeds the plan envelope, scale all positions
    proportionally along that axis so the layout fits exactly.
    Adjacency topology is preserved because all positions scale uniformly.
    """
    if not positions:
        return positions

    max_right = max(p["x_m"] + dim.get(p["name"], (0, 0))[0] for p in positions)
    max_top   = max(p["y_m"] + dim.get(p["name"], (0, 0))[1] for p in positions)

    scale_x = plan_w / max_right if max_right > plan_w else 1.0
    scale_y = plan_d / max_top   if max_top   > plan_d else 1.0

    if scale_x < 1.0:
        print(f"  [constraint_agent] Scaling x by {scale_x:.3f} "
              f"(max_right={max_right:.2f}m > plan_width={plan_w}m)")
    if scale_y < 1.0:
        print(f"  [constraint_agent] Scaling y by {scale_y:.3f} "
              f"(max_top={max_top:.2f}m > plan_depth={plan_d}m)")

    return [
        {**p, "x_m": round(p["x_m"] * scale_x, 3),
               "y_m": round(p["y_m"] * scale_y, 3)}
        for p in positions
    ]
