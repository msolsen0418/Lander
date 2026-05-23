"""
Flask web server for the Florida Property Arbitrage Dashboard.
"""

import json
import logging
from flask import Flask, jsonify, render_template, request, Response, stream_with_context, send_from_directory

import database as db
import scraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = Flask(__name__)


@app.before_request
def ensure_db():
    db.init_db()


# ── Pages ────────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    return render_template("index.html")


@app.route("/sw.js")
def service_worker():
    # Must be served from root path so its scope covers the whole app
    resp = send_from_directory("static", "sw.js", mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# ── API ──────────────────────────────────────────────────────────────────────

@app.route("/api/properties")
def api_properties():
    county = request.args.get("county", "").strip()
    auction_type = request.args.get("type", "").strip()
    min_equity = request.args.get("min_equity_pct", type=float)

    properties = db.get_all_properties_with_valuations()

    if county:
        properties = [p for p in properties if p.get("county", "").lower() == county.lower()]
    if auction_type:
        properties = [p for p in properties if p.get("auction_type") == auction_type]
    if min_equity is not None:
        properties = [p for p in properties if (p.get("equity_gap_pct") or 0) >= min_equity]

    # Sort by equity_gap_pct descending (best opportunities first)
    properties.sort(key=lambda p: p.get("equity_gap_pct") or -9999, reverse=True)

    return jsonify(properties)


@app.route("/api/stats")
def api_stats():
    stats = db.get_stats()
    properties = db.get_all_properties_with_valuations()

    equity_gaps = [p["equity_gap_pct"] for p in properties if p.get("equity_gap_pct") is not None]
    positive = [g for g in equity_gaps if g > 0]

    counties = sorted({p["county"] for p in properties if p.get("county")})
    types = sorted({p["auction_type"] for p in properties if p.get("auction_type")})

    stats.update(
        {
            "positive_equity_count": len(positive),
            "avg_equity_gap_pct": round(sum(positive) / len(positive), 1) if positive else 0,
            "best_equity_gap_pct": round(max(positive), 1) if positive else 0,
            "counties": counties,
            "auction_types": types,
        }
    )
    return jsonify(stats)


@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    state = scraper.get_state()
    if state["running"]:
        return jsonify({"status": "already_running", "state": state}), 409

    max_counties = request.json.get("max_counties") if request.is_json else None
    scraper.start_background_scrape(max_counties=max_counties)
    return jsonify({"status": "started"})


@app.route("/api/scrape/status")
def api_scrape_status():
    return jsonify(scraper.get_state())


@app.route("/api/scrape/stream")
def api_scrape_stream():
    """Server-Sent Events stream for real-time scrape progress."""
    def generate():
        import time
        while True:
            state = scraper.get_state()
            yield f"data: {json.dumps(state)}\n\n"
            if not state["running"] and state["phase"] in ("idle", "error"):
                break
            time.sleep(1)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
