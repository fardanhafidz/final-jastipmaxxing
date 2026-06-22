"""
Flask application for GA Jastip Route Optimizer.
Serves both the web UI and the /optimize API endpoint.
"""

import csv
import os
import time
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from ga_engine import run_pctsp_ga, repair
from distance import haversine
from routing import compute_distance_matrix, build_route_polyline

app = Flask(__name__)
app.secret_key = "jastipmaxxing-secret-key"

# Default GA settings
DEFAULT_SETTINGS = {
    "pop_size": 80,
    "generations": 200,
    "mutation_rate": 0.03,
    "elite_size": 8,
}

# In-memory route history (resets on server restart)
ROUTE_HISTORY = []

# ---------------------------------------------------------------------------
# Load POI data from CSV
# ---------------------------------------------------------------------------

POI_DATA = []

def load_poi_csv(filepath):
    """Load pinpoint.csv into memory, skipping malformed rows."""
    data = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)  # skip header
        for row in reader:
            if len(row) < 5:
                continue
            name, category, tag, lat, lng = row[0], row[1], row[2], row[3], row[4]
            try:
                lat_f = float(lat)
                lng_f = float(lng)
            except (ValueError, TypeError):
                continue
            data.append({
                "name": name.strip().strip('"'),
                "category": category.strip(),
                "tag": tag.strip(),
                "lat": lat_f,
                "lng": lng_f,
            })
    return data

# Load on startup
csv_path = os.path.join(os.path.dirname(__file__), "pinpoint.csv")
if os.path.exists(csv_path):
    POI_DATA = load_poi_csv(csv_path)
    print(f"Loaded {len(POI_DATA)} POI from pinpoint.csv")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the optimize/maps page."""
    settings = session.get("ga_settings", DEFAULT_SETTINGS)
    return render_template("index.html", settings=settings, active_page="maps")


@app.route("/history")
def history():
    """Serve the history page."""
    return render_template("history.html", routes=ROUTE_HISTORY, active_page="history")


@app.route("/settings", methods=["GET", "POST"])
def settings():
    """GA parameter settings page."""
    if request.method == "POST":
        new_settings = {
            "pop_size": int(request.form.get("pop_size", 80)),
            "generations": int(request.form.get("generations", 200)),
            "mutation_rate": float(request.form.get("mutation_rate", 0.03)),
            "elite_size": int(request.form.get("elite_size", 8)),
        }
        session["ga_settings"] = new_settings
        return redirect(url_for("settings"))
    current = session.get("ga_settings", DEFAULT_SETTINGS)
    return render_template("settings.html", settings=current, active_page="settings")


@app.route("/poi-list")
def poi_list():
    """
    Return POI list from pinpoint.csv.
    Supports ?q=search and ?category=amenity filters.
    """
    q = request.args.get("q", "").lower().strip()
    category = request.args.get("category", "").strip()

    results = POI_DATA
    if category:
        results = [p for p in results if p["category"] == category]
    if q:
        results = [p for p in results if q in p["name"].lower() or q in p["tag"].lower()]

    # Limit to 50 results for performance
    return jsonify(results[:50])


@app.route("/optimize", methods=["POST"])
def optimize():
    """
    Run the GA optimizer on user-submitted pickup & delivery points.

    Expected JSON body:
    {
        "basecamp": {"name": "...", "lat": float, "lng": float},
        "pickups": [{"id": "p1", "name": "...", "lat": float, "lng": float}, ...],
        "delivery_map": {
            "p1": [{"id": "d1", "name": "...", "lat": float, "lng": float}, ...],
            ...
        },
        "pop_size": int (default 80),
        "generations": int (default 200),
        "mutation_rate": float (default 0.03)
    }
    """
    body = request.get_json()
    if not body:
        return jsonify({"error": "Request body must be JSON"}), 400

    # --- Parse & validate input ---
    basecamp = body.get("basecamp")
    pickups = body.get("pickups", [])
    delivery_map_raw = body.get("delivery_map", {})
    pop_size = body.get("pop_size", 80)
    generations = body.get("generations", 200)
    mutation_rate = body.get("mutation_rate", 0.03)

    if not basecamp or "lat" not in basecamp or "lng" not in basecamp:
        return jsonify({"error": "Basecamp with lat/lng is required"}), 400

    if not pickups:
        return jsonify({"error": "At least 1 pickup point is required"}), 400

    for p in pickups:
        if not delivery_map_raw.get(p["id"]):
            return jsonify({"error": f"Pickup '{p.get('name', p['id'])}' must have at least 1 delivery target"}), 400

    # --- Build points_map (unified lookup) ---
    points_map = {}

    bc_id = "bc"
    points_map[bc_id] = {
        "name": basecamp.get("name", "Basecamp"),
        "lat": float(basecamp["lat"]),
        "lng": float(basecamp["lng"]),
        "type": "basecamp",
    }

    pickup_ids = []
    for p in pickups:
        pid = p["id"]
        pickup_ids.append(pid)
        points_map[pid] = {
            "name": p["name"],
            "lat": float(p["lat"]),
            "lng": float(p["lng"]),
            "type": "pickup",
        }

    # delivery_map: {pickup_id: [delivery_id, ...]}
    delivery_map = {}
    pickup_id_to_name = {}
    for p in pickups:
        pid = p["id"]
        pickup_id_to_name[pid] = p["name"]
        delivery_map[pid] = []
        for d in delivery_map_raw.get(pid, []):
            did = d["id"]
            delivery_map[pid].append(did)
            points_map[did] = {
                "name": d["name"],
                "lat": float(d["lat"]),
                "lng": float(d["lng"]),
                "type": "delivery",
                "owner": pid,
            }

    # --- Compute OSRM road distance matrix ---
    ordered_points = [bc_id] + pickup_ids + list(
        did for dids in delivery_map.values() for did in dids
    )
    print(f"[OSRM] Computing distance matrix for {len(ordered_points)} points...")
    t_osrm = time.time()
    dist_matrix = compute_distance_matrix(ordered_points, points_map)
    print(f"[OSRM] Matrix ready in {time.time() - t_osrm:.2f}s")

    # --- Run GA ---
    t0 = time.time()
    best_route, best_dist, history = run_pctsp_ga(
        bc=bc_id,
        pickups=pickup_ids,
        delivery_map=delivery_map,
        dist_matrix=dist_matrix,
        ordered_points=ordered_points,
        pop_size=pop_size,
        generations=generations,
        mutation_rate=mutation_rate,
    )
    elapsed = time.time() - t0

    # --- Build stops detail ---
    pickup_set = set(pickup_ids)
    target_to_amenity = {}
    for pid, dids in delivery_map.items():
        for did in dids:
            target_to_amenity[did] = pid

    stops = []

    # Basecamp start
    bc_info = points_map[bc_id]
    stops.append({
        "step": 0,
        "type": "basecamp",
        "name": bc_info["name"],
        "lat": bc_info["lat"],
        "lng": bc_info["lng"],
        "note": "Titik awal & akhir",
    })

    # Route stops
    for step_num, pid in enumerate(best_route, start=1):
        info = points_map[pid]
        is_pickup = pid in pickup_set

        if is_pickup:
            n_targets = len(delivery_map.get(pid, []))
            note = f"Pickup untuk {n_targets} tujuan"
        else:
            owner_id = target_to_amenity.get(pid)
            owner_name = points_map[owner_id]["name"] if owner_id else "?"
            note = f"Antar (dari {owner_name})"

        stops.append({
            "step": step_num,
            "type": "pickup" if is_pickup else "delivery",
            "name": info["name"],
            "lat": info["lat"],
            "lng": info["lng"],
            "note": note,
        })

    # Basecamp return
    stops.append({
        "step": len(best_route) + 1,
        "type": "basecamp_return",
        "name": bc_info["name"],
        "lat": bc_info["lat"],
        "lng": bc_info["lng"],
        "note": "Kembali ke basecamp",
    })

    # --- Build polyline (real road via OSRM) ---
    chain = [bc_id] + best_route + [bc_id]
    print(f"[OSRM] Building road polyline for {len(chain)} stops...")
    polyline = build_route_polyline(chain, points_map)

    # --- Response + save to history ---
    route_id = uuid.uuid4().hex[:8]
    route_record = {
        "id": route_id,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "distance_km": round(best_dist / 1000, 3),
        "stops": len(stops) - 1,  # exclude basecamp return
        "generations": len(history),
        "elapsed_s": round(elapsed, 2),
        "basecamp": basecamp.get("name", "Basecamp"),
        "route": stops,
        "polyline": polyline,
    }
    ROUTE_HISTORY.insert(0, route_record)

    return jsonify({
        "id": route_id,
        "best_dist_m": round(best_dist, 1),
        "best_dist_km": round(best_dist / 1000, 3),
        "elapsed_s": round(elapsed, 2),
        "generations": len(history),
        "history": history,
        "route": stops,
        "polyline": polyline,
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
