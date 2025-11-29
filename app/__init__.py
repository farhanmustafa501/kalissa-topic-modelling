from flask import Flask

from .config import get_config
from .db import Base, engine


def create_app() -> Flask:
	app = Flask(__name__, template_folder="templates", static_folder="static")

	app.config.from_mapping(get_config())

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


