"""Flask application factory."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

from . import db
from .validation import ValidationError

BACKEND_DIR = Path(__file__).resolve().parent.parent


def create_app(config: dict | None = None) -> Flask:
    # Load backend/.env before anything reads os.environ. override=False
    # so a value already exported in the shell wins, which is what lets
    # the test suite point at a scratch database.
    load_dotenv(BACKEND_DIR / ".env", override=False)

    app = Flask(__name__)
    app.config.update(
        COUNTRY=os.environ.get("COLLECT_COUNTRY", "IN").upper(),
        JSON_SORT_KEYS=False,
    )
    if config:
        app.config.update(config)

    # Exactly one origin: the Vite dev server. Not "*", and only under
    # /api/* -- there is nothing else on this server to reach.
    CORS(
        app,
        resources={r"/api/*": {"origins": [os.environ.get("CORS_ORIGIN",
                                                          "http://localhost:5173")]}},
        methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
        max_age=600,
    )

    db.init_app(app)

    from .routes.stations import bp as stations_bp
    from .routes.compare import bp as compare_bp
    from .routes.subscriptions import bp as subscriptions_bp
    from .routes.health import bp as health_bp

    for blueprint in (health_bp, stations_bp, compare_bp, subscriptions_bp):
        app.register_blueprint(blueprint)

    # ---- error handling -------------------------------------------------
    # Errors are JSON everywhere. An HTML error page reaching a fetch()
    # turns a clear 400 into an opaque parse failure in the browser.
    @app.errorhandler(ValidationError)
    def _bad_request(err: ValidationError):
        payload = {"error": "bad_request", "message": err.message}
        if err.field:
            payload["field"] = err.field
        return jsonify(payload), 400

    @app.errorhandler(404)
    def _not_found(_err):
        return jsonify({"error": "not_found",
                        "message": "No such endpoint or resource."}), 404

    @app.errorhandler(405)
    def _bad_method(_err):
        return jsonify({"error": "method_not_allowed",
                        "message": "That method is not allowed on this endpoint."}), 405

    @app.errorhandler(500)
    def _server_error(_err):
        return jsonify({"error": "server_error",
                        "message": "Something failed server-side. Check the Flask log."}), 500

    return app
