"""OSM extract -> static/plan.json: simplified site geometry in local metres.

Input: the Overpass extract osm/core.geojson (© OpenStreetMap contributors,
ODbL). Output: a small JSON the plan view draws as SVG. Coordinates are
metres east (x) and north (y) from the origin; the view flips y.

  python -I web/tools/osm2plan.py ../osm/core.geojson web/static/plan.json
  python -I web/tools/osm2plan.py ../osm/core.geojson --inspect     # table only

Standard library only; run once by hand, the result is committed.
"""
from __future__ import annotations

import json
import math
import sys

# Origin of the local frame: near the plant, so numbers stay small.
ORIGIN = (79.93, 46.94)  # lon, lat
KX = 111320.0 * math.cos(math.radians(ORIGIN[1]))
KY = 110574.0

# OSM classes we draw: (class, simplification tolerance m, minimum length km or area ha, 0 = keep all).
LAYERS = {
    "quarry": ("landuse=quarry", 30.0, 0),
    "mine": ("industrial=mine", 80.0, 0),
    "industrial": ("landuse=industrial", 40.0, 5.0),
    "landfill": ("landuse=landfill", 90.0, 0),
    "tailings": ("man_made=tailings_pond", 60.0, 0),
    "water": ("natural=water", 40.0, 0),
    "reservoir": ("water=reservoir", 10.0, 0),
    "building": ("building=industrial", 8.0, 0),
    "house": ("building=yes", 8.0, 0.15),
    "conveyor": ("man_made=goods_conveyor", 10.0, 0),
    "rail": ("railway=rail", 60.0, 0.25),
    "road": ("highway=tertiary", 60.0, 0),
    "road2": ("highway=unclassified", 80.0, 0.9),
    "power_line": ("power=line", 80.0, 1.0),
    "substation": ("power=substation", 10.0, 0),
    "pipeline": ("man_made=pipeline", 50.0, 0.4),
}
# Part of the extract shown on the plan (metres from ORIGIN): the pit, the
# plant, the near tailings pond and the waste dumps. Features entirely outside
# are dropped; the far railway and the 220 kV line are cut at the edge.
VIEW = (-4200, -2600, 7000, 5600)

# Where each twin sits on the plan (metres). From OSM where the object is
# mapped; "scheme" items are not in OSM and are drawn as a scheme.
ANCHORS = {
    "pit": {"xy": [3466, 3191], "osm": "way/773805067"},
    "exc-1": {"xy": [2950, 3600], "scheme": True},
    "exc-2": {"xy": [3900, 3900], "scheme": True},
    "exc-3": {"xy": [3500, 2700], "scheme": True},
    "fleet": {"xy": [3466, 2000], "scheme": True},
    "crusher-1": {"xy": [3618, 1580], "osm": "way/773805064"},
    "crusher-2": {"xy": [3629, 1323], "scheme": True},
    "conveyor-1": {"path": [[3584, 1562], [1158, 1190], [706, 1125]], "osm": "way/773805065 + way/1347766946"},
    "conveyor-2": {"path": [[3629, 1323], [2632, 1222], [2154, 1173]], "osm": "way/1347766945 + way/1347766944"},
    "stockpile-1": {"xy": [665, 1090], "scheme": True, "to_sag": [[624, 1048], [466, 897]]},
    "stockpile-2": {"xy": [2125, 1140], "scheme": True, "to_sag": [[2094, 1105], [1936, 955]]},
    "line-1": {"xy": [405, 774], "osm": "way/1347766933"},
    "line-2": {"xy": [1881, 837], "osm": "way/1347766934"},
    "conc-stock": {"xy": [700, 290], "scheme": True, "rail": "way/1097493544"},
    # oxide line (heap leach -> SX-EW): the place is not published, so a scheme west of the concentrator
    "leach-1": {"xy": [-1500, 420], "scheme": True},
    "sxew-1": {"xy": [-1500, 150], "scheme": True},
    "water": {"xy": [1215, -1024], "osm": "way/773805070"},
    "power": {"xy": [1800, 1171], "osm": "way/1347766951", "line": "way/1027119995"},
    "crew-kip": {"xy": [1150, 560], "scheme": True},
    "crew-cpd": {"xy": [3350, 1700], "scheme": True},
    "crew-mill": {"xy": [1150, 720], "scheme": True},
    # pit twins the simulator places by name only (face of an excavator, haul roads): OSM maps
    # no faces or haul roads, so their places are a scheme on the pit outline
    "exc-4": {"xy": [4250, 3650], "scheme": True},
    "exc-5": {"xy": [4380, 3000], "scheme": True},
    "face-1": {"xy": [2950, 3600], "scheme": True},
    "face-2": {"xy": [3900, 3900], "scheme": True},
    "face-3": {"xy": [3500, 2700], "scheme": True},
    "face-4": {"xy": [4250, 3650], "scheme": True},
    "face-5": {"xy": [4380, 3000], "scheme": True},
    "ramp-1": {"path": [[3050, 3420], [3300, 2950], [3560, 2480], [3700, 2200], [3640, 1640]], "scheme": True},
    "ramp-2": {"path": [[3820, 3700], [4050, 3250], [4000, 2700], [3880, 2250], [3760, 1800], [3660, 1390]], "scheme": True},
    "road-dump": {"path": [[4320, 3330], [4780, 3300], [5500, 3200]], "scheme": True},
}


def fix_text(s):
    """Undo latin-1 mojibake: the extract holds some UTF-8 names read as latin-1
    ("ÐÒÑÐ¾ÒÐ°Ð¹" -> "Ақтоғай"). Text that is not such mojibake stays as it is."""
    if not isinstance(s, str) or not any("À" <= c <= "ÿ" for c in s):
        return s
    try:
        fixed = s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s
    return fixed


def project(lon: float, lat: float) -> tuple[float, float]:
    return ((lon - ORIGIN[0]) * KX, (lat - ORIGIN[1]) * KY)


def rings(geom: dict) -> list[list[list[float]]]:
    t, c = geom["type"], geom["coordinates"]
    if t == "LineString":
        return [c]
    if t == "Polygon":
        return c[:1]  # outer ring only
    if t == "MultiPolygon":
        return [poly[0] for poly in c]
    return []


def dp(points: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Douglas-Peucker; keeps the first and last point."""
    if len(points) < 3:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy)
    best, idx = -1.0, 0
    for i in range(1, len(points) - 1):
        x, y = points[i]
        d = abs(dx * (y1 - y) - (x1 - x) * dy) / norm if norm else math.hypot(x - x1, y - y1)
        if d > best:
            best, idx = d, i
    if best > tol:
        return dp(points[: idx + 1], tol)[:-1] + dp(points[idx:], tol)
    return [points[0], points[-1]]


def simplify_ring(ring: list[list[float]], tol: float, closed: bool) -> list[list[int]]:
    pts = [project(p[0], p[1]) for p in ring]
    if closed and len(pts) > 3 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if closed and len(pts) > 3:
        # split at the farthest point from the first so DP sees two open chains
        far = max(range(1, len(pts)), key=lambda i: math.hypot(pts[i][0] - pts[0][0], pts[i][1] - pts[0][1]))
        out = dp(pts[: far + 1], tol)[:-1] + dp(pts[far:] + [pts[0]], tol)[:-1]
    else:
        out = dp(pts, tol)
    return [[int(round(x)), int(round(y))] for x, y in out]


def bbox(pts: list[list[int]]) -> tuple[int, int, int, int]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def centroid(pts: list[list[int]]) -> list[int]:
    return [int(round(sum(p[0] for p in pts) / len(pts))), int(round(sum(p[1] for p in pts) / len(pts)))]


def clip_line(pts: list[list[int]], view: tuple[int, int, int, int]) -> list[list[int]]:
    """Cut an open line at the view edge: keep inside points plus one outside neighbour each side."""
    x0, y0, x1, y1 = view
    inside = [x0 <= x <= x1 and y0 <= y <= y1 for x, y in pts]
    if not any(inside):
        return []
    keep = [i for i, ok in enumerate(inside) if ok or (i > 0 and inside[i - 1]) or (i + 1 < len(pts) and inside[i + 1])]
    return [pts[i] for i in keep]


def build(geojson: dict) -> dict:
    layers: dict[str, list[dict]] = {k: [] for k in LAYERS}
    vx0, vy0, vx1, vy1 = VIEW
    for ft in geojson["features"]:
        geom = ft["geometry"]
        if geom["type"] == "Point":
            continue
        props = ft["properties"]
        cls = props.get("class", "")
        for key, (want, tol, minimum) in LAYERS.items():
            if cls != want:
                continue
            closed = geom["type"] != "LineString"
            size = float(props.get("area_ha" if closed else "len_km") or 0)
            if minimum and size < minimum:
                continue
            for ring in rings(geom):
                pts = simplify_ring(ring, tol, closed)
                if closed:
                    bx0, by0, bx1, by1 = bbox(pts)
                    if bx1 < vx0 or bx0 > vx1 or by1 < vy0 or by0 > vy1:
                        continue
                else:
                    pts = clip_line(pts, VIEW)
                if len(pts) < 2:
                    continue
                item = {"id": props["osm_id"], "pts": pts}
                for tag in ("name", "description", "voltage", "service", "usage", "area_ha", "len_km"):
                    if props.get(tag) not in (None, ""):
                        item[tag] = fix_text(props[tag])
                layers[key].append(item)
    out = {
        "attribution": "© OpenStreetMap contributors",
        "license": "ODbL 1.0",
        "license_url": "https://opendatacommons.org/licenses/odbl/1-0/",
        "source": geojson.get("source", "Overpass API"),
        "origin_lonlat": list(ORIGIN),
        "metres_per_deg": [round(KX, 1), round(KY, 1)],
        "view": list(VIEW),
        "anchors": ANCHORS,
        "layers": layers,
    }
    allpts = [p for items in layers.values() for it in items for p in it["pts"]]
    out["bbox"] = list(bbox(allpts)) if allpts else [0, 0, 0, 0]
    out["points"] = len(allpts)
    return out


def inspect(plan: dict) -> None:
    for key, items in plan["layers"].items():
        for it in items:
            x0, y0, x1, y1 = bbox(it["pts"])
            c = centroid(it["pts"])
            extra = " ".join(f"{k}={it[k]}" for k in ("name", "voltage", "service", "usage", "area_ha", "len_km") if k in it)
            ends = ""
            if key in ("conveyor", "pipeline", "power_line", "rail"):
                ends = f"  {it['pts'][0]}..{it['pts'][-1]}"
            print(f"{key:<11} {it['id']:<16} {len(it['pts']):>3} pts  c=({c[0]:>6},{c[1]:>6})  "
                  f"{x1 - x0:>5}x{y1 - y0:<5} m  {extra[:60]}{ends}")
    print(f"total points: {plan['points']}  bbox: {plan['bbox']}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    with open(argv[0], encoding="utf-8") as f:
        plan = build(json.load(f))
    if "--inspect" in argv or len(argv) < 2:
        inspect(plan)
        return 0
    with open(argv[1], "w", encoding="utf-8", newline="\n") as f:
        json.dump(plan, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"wrote {argv[1]}: {plan['points']} points, bbox {plan['bbox']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
