"""DML Shipping Calculator - Flask web app.

Run locally:   python app.py            (http://127.0.0.1:5050)
Production:    gunicorn app:app --bind 0.0.0.0:$PORT --workers 2

Environment variables: none required.
  DML_TOOLS_HOME_URL   Optional link for "DML Tools" in the header.

The page opens directly (no sign-in). Its "How to Get Shipping Prices" panel shows
the DML UPS login, so keep the repository private and share the URL with DML staff only.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from flask import Flask, jsonify, render_template, request

from shipping.config import ConfigError, load_config
from shipping.packing import PackingError, suggest
from shipping.quote import SERVICES, evaluate, public

APP_VERSION = "1.5.0"
UPS_RATE_URL = ("https://www.ups.com/lasso/login?returnto=https%3a//www.ups.com/webqvm%3floc%3den_CA"
                "&reasonCode=-1&appid=CVA#/thirdparty")


def create_app(config_path: str = None) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024  # requests are small JSON
    app.json.sort_keys = False
    cfg = load_config(config_path)  # raises ConfigError on a bad data file
    tools_home = os.environ.get("DML_TOOLS_HOME_URL", "").strip()

    def body() -> Dict[str, Any]:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
        )
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route("/")
    def index():
        resp = app.make_response(render_template("index.html", app_version=APP_VERSION, tools_home=tools_home,
                                                 ups_url=UPS_RATE_URL))
        resp.headers["Cache-Control"] = "no-store"  # the page contains the UPS login
        return resp

    @app.route("/healthz")
    def healthz():
        return jsonify({"ok": True, "app_version": APP_VERSION, "config_version": cfg.version})

    @app.route("/api/config")
    def api_config():
        products = []
        for pid in cfg.product_order:
            p = cfg.products[pid]
            products.append({
                "id": p.id,
                "name": p.name,
                "boxes": [{"box_id": b.id, "capacity": p.boxes[b.id].capacity, "status": p.boxes[b.id].status,
                           "auto": p.boxes[b.id].auto, "selectable": p.boxes[b.id].selectable}
                          for b in cfg.boxes.values() if b.id in p.boxes],
            })
        return jsonify({
            "config_version": cfg.version,
            "currency": cfg.currency,
            "services": [{"id": k, "label": v["label"], "weights_apply": v["weights_apply"]} for k, v in SERVICES.items()],
            "boxes": [{"id": b.id, "label": b.label, "dims_text": b.dims_text, "dim_weight_lb": b.dim_weight_lb}
                      for b in cfg.boxes.values()],
            "products": products,
            "limits": {"max_quantity": cfg.max_quantity, "max_box_rows": cfg.max_rows},
        })

    @app.route("/api/suggest", methods=["POST"])
    def api_suggest():
        b = body()
        try:
            return jsonify(suggest(cfg, b.get("product_id"), b.get("quantity")))
        except PackingError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/quote", methods=["POST"])
    def api_quote():
        return jsonify(public(evaluate(cfg, body())))

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify({"error": "Request too large."}), 413

    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found."}), 404
        return "Not found", 404

    @app.errorhandler(405)
    def bad_method(_e):
        return jsonify({"error": "Method not allowed."}), 405

    @app.errorhandler(500)
    def server_error(_e):
        return jsonify({"error": "Unexpected error. Please try again."}), 500

    return app


try:
    app = create_app()
except ConfigError as _exc:  # make a broken data file obvious at start-up
    raise SystemExit("DML Shipping Calculator: invalid data file - %s" % _exc)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    host = os.environ.get("HOST", "127.0.0.1")
    print("DML Shipping Calculator %s running at http://%s:%d" % (APP_VERSION, host, port))
    app.run(host=host, port=port, debug=False)
