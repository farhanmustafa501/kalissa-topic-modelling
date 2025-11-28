from flask import Blueprint, jsonify, render_template

api_bp = Blueprint("api", __name__)
ui_bp = Blueprint("ui", __name__)


@api_bp.get("/health")
def health():
	return jsonify({"status": "ok"})


@ui_bp.get("/")
def index():
	return render_template("index.html")


