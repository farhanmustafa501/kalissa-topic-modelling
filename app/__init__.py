import logging
import os

from flask import Flask

from .config import get_config
from .db import Base, engine


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    app.config.from_mapping(get_config())

    # Logging configuration
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    if not app.logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(getattr(logging, log_level, logging.INFO))
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        handler.setFormatter(formatter)
        app.logger.addHandler(handler)
    app.logger.setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger(__name__).setLevel(getattr(logging, log_level, logging.INFO))

    from .api.routes import api_bp, ui_bp

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(ui_bp)

    # Dev convenience: ensure tables exist if migrations not run.
    try:
        Base.metadata.create_all(engine)
    except Exception:
        # Avoid crashing app boot if DB is not ready; container orchestration will handle retries.
        pass

    return app
