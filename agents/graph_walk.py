"""
Graph-walk room positioner.

BFS from an anchor room, placing each neighbor exactly flush using the
shared_edge from the adjacency graph. Guarantees zero gaps between
adjacent rooms — no LLM, no rounding drift, deterministic.

Alignment assumption: rooms sharing a horizontal edge (left/right) are
bottom-aligned; rooms sharing a vertical edge (top/bottom) are left-aligned.
Holds for rectilinear plans. Cycles in the graph are broken by first-visit
(BFS order), which is correct for the primary load-bearing edges.
"""

from collections import deque

_REVERSE = {"right": "left", "left": "right", "top": "bottom", "bottom": "top"}


def walk(rooms: list[dict], adjacency: list[dict]) -> list[dict]:
    """
    Returns [{name, x_m, y_m}] — bottom-left corner of each room in metres,
    origin at (0, 0). Rooms not reachable from the anchor are placed at (0, 0)
    with a warning (pixel-centroid fallback kicks in for them in the combiner).
    """
    if not rooms:
        return []

    dim = {r["name"]: (float(r["width_m"]), float(r["depth_m"])) for r in rooms}

    # Build bidirectional adjacency list
    adj: dict[str, list[tuple[str, str]]] = {}
    for a in adjacency:
        ra, rb, edge = a["room_a"], a["room_b"], a["shared_edge"]
        adj.setdefault(ra, []).append((rb, edge))
        adj.setdefault(rb, []).append((ra, _REVERSE[edge]))

    # Anchor: prefer a room with "DINING" in the name, else first in list
    names = [r["name"] for r in rooms]
    anchor = next((n for n in names if "DINING" in n), names[0])

    positions: dict[str, tuple[float, float]] = {anchor: (0.0, 0.0)}
    queue: deque[str] = deque([anchor])
    visited: set[str] = {anchor}

    while queue:
        cur = queue.popleft()
        cx, cy = positions[cur]
        cw, cd = dim[cur]

        used_edges: set[str] = set()  # one neighbour per direction per room

        for nbr, edge in adj.get(cur, []):
            if nbr in visited:
                continue
            # If we've already placed a neighbour in this direction from this
            # room, skip — the skipped room will be reached via another edge
            # (e.g. the second "bottom" neighbour via a "right" edge between
            # the two sibling rooms).
            if edge in used_edges:
                continue
            nw, nd = dim[nbr]

            if edge == "right":
                pos = (cx + cw, cy)
            elif edge == "left":
                pos = (cx - nw, cy)
            elif edge == "top":
                pos = (cx, cy + cd)
            else:  # bottom
                pos = (cx, cy - nd)

            positions[nbr] = pos
            visited.add(nbr)
            used_edges.add(edge)
            queue.append(nbr)

    # Disconnected rooms — warn and place at origin (combiner falls back to pixel)
    for n in names:
        if n not in positions:
            print(f"  [graph_walk] WARNING: '{n}' not reachable from anchor '{anchor}'")
            positions[n] = (0.0, 0.0)

    # Shift so bottom-left corner of the layout is at (0, 0)
    min_x = min(x for x, _ in positions.values())
    min_y = min(y for _, y in positions.values())

    return [
        {"name": n, "x_m": round(x - min_x, 4), "y_m": round(y - min_y, 4)}
        for n, (x, y) in positions.items()
    ]
