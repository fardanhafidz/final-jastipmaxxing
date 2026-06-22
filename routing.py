"""
OSRM (Open Source Routing Machine) integration for real road routing.

Uses the free OSRM demo server for:
  - Distance matrix computation (table service) — used by GA fitness
  - Route polyline extraction (route service) — used for map display

Falls back to Haversine (straight-line) distance if OSRM is unavailable.
"""

import requests
import polyline as polyline_lib
from distance import haversine

OSRM_BASE = "https://router.project-osrm.org"
_TIMEOUT = 30  # seconds


def compute_distance_matrix(ordered_points: list, points_map: dict) -> list:
    """
    Compute an N×N road-distance matrix via OSRM Table API.

    Args:
        ordered_points: list of point IDs in a fixed order [id0, id1, ..., idN]
        points_map: {id: {lat, lng, ...}}

    Returns:
        2D list (N×N) of distances in meters.
        Falls back to Haversine on failure.
    """
    n = len(ordered_points)
    idx = {pid: i for i, pid in enumerate(ordered_points)}

    # OSRM expects coordinates as lng,lat;lng,lat;...
    coords_str = ";".join(
        f"{points_map[pid]['lng']},{points_map[pid]['lat']}"
        for pid in ordered_points
    )

    try:
        resp = requests.get(
            f"{OSRM_BASE}/table/v1/driving/{coords_str}",
            params={"annotations": "distance"},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "Ok":
                return data["distances"]
    except Exception as e:
        print(f"[OSRM] Table API failed: {e}")

    # Fallback: Haversine matrix
    print("[OSRM] Falling back to Haversine distance matrix")
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        pi = points_map[ordered_points[i]]
        for j in range(i + 1, n):
            pj = points_map[ordered_points[j]]
            d = haversine(pi["lat"], pi["lng"], pj["lat"], pj["lng"])
            matrix[i][j] = d
            matrix[j][i] = d
    return matrix


def get_route_polyline(lat1: float, lng1: float,
                       lat2: float, lng2: float) -> list:
    """
    Get road polyline coordinates between two points via OSRM Route API.

    Returns:
        List of [lat, lng] pairs following actual roads.
        Falls back to straight line on failure.
    """
    try:
        resp = requests.get(
            f"{OSRM_BASE}/route/v1/driving/{lng1},{lat1};{lng2},{lat2}",
            params={"overview": "full", "geometries": "polyline"},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data["code"] == "Ok" and data["routes"]:
                geometry = data["routes"][0]["geometry"]
                # polyline_lib returns (lat, lng) tuples — convert to lists
                decoded = polyline_lib.decode(geometry)
                return [[lat, lng] for lat, lng in decoded]
    except Exception as e:
        print(f"[OSRM] Route API failed: {e}")

    # Fallback: straight line
    return [[lat1, lng1], [lat2, lng2]]


def build_route_polyline(chain_ids: list, points_map: dict) -> list:
    """
    Build full road polyline for the route chain.
    Fetches OSRM road geometry for each consecutive segment and
    stitches them together (removing duplicate junction points).

    Args:
        chain_ids: [bc_id, stop1, stop2, ..., bc_id] point IDs
        points_map: {id: {lat, lng, ...}}

    Returns:
        List of [lat, lng] coordinates tracing actual roads.
    """
    all_coords = []
    for k in range(len(chain_ids) - 1):
        src = points_map[chain_ids[k]]
        tgt = points_map[chain_ids[k + 1]]

        segment = get_route_polyline(
            src["lat"], src["lng"],
            tgt["lat"], tgt["lng"],
        )

        # Remove duplicate at junction
        if all_coords and segment and all_coords[-1] == segment[0]:
            segment = segment[1:]

        all_coords.extend(segment)

    return all_coords
