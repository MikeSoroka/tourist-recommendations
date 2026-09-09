"""WSGI entry point for the web application."""

from __future__ import annotations

import os

from tourist.web import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
