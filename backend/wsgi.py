"""Flask entry point.

    cd backend
    .venv/bin/python wsgi.py

Or via the CLI:
    FLASK_APP=wsgi:app .venv/bin/flask run --port 5000
"""
from __future__ import annotations

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", "5000"))
    debug = os.environ.get("FLASK_ENV", "development") == "development"
    print(f"\n  API on http://127.0.0.1:{port}/api/health")
    print(f"  CORS origin: {os.environ.get('CORS_ORIGIN', 'http://localhost:5173')}\n")
    app.run(host="127.0.0.1", port=port, debug=debug, use_reloader=debug)
