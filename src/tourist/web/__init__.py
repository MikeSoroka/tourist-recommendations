from __future__ import annotations
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from tourist import config

db = SQLAlchemy()


def create_app() -> Flask:
    """Build and configure the Flask application."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = config.database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }
    app.config["SCHEMA_NAME"] = config.SCHEMA_NAME
    app.config["IMAGES_DIR"] = str(config.IMAGES_DIR)
    db.init_app(app)

    from .api import api, register_error_handlers
    from .views import main

    app.register_blueprint(main)
    app.register_blueprint(api)
    register_error_handlers(app)

    return app
