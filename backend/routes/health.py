"""Dependency-free HTTP probes for the Flask service."""

from time import monotonic

from flask import Blueprint, jsonify


health_bp = Blueprint("health", __name__)
_started_at = monotonic()


@health_bp.after_request
def prevent_probe_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@health_bp.get("/health")
@health_bp.get("/api/health")
def health():
    """Report service availability, not database or market-feed readiness."""
    return jsonify(
        status="ok",
        service="candlesticks-backend",
        uptime_seconds=round(monotonic() - _started_at, 3),
    ), 200


@health_bp.get("/live")
@health_bp.get("/api/live")
def liveness():
    """Answer only whether this application worker can serve an HTTP request."""
    return jsonify(status="alive"), 200
