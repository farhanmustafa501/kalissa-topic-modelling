"""
Tests for Flask application.
"""

import pytest

from app import create_app


@pytest.mark.unit
class TestApp:
    """Tests for Flask application creation."""

    def test_create_app(self):
        """Test creating Flask application."""
        app = create_app()
        assert app is not None
        assert app.config["TESTING"] == False  # Not in test mode by default

    def test_create_app_with_testing(self):
        """Test creating app in testing mode."""
        app = create_app()
        app.config["TESTING"] = True
        assert app.config["TESTING"] == True

    def test_app_has_blueprints(self):
        """Test that app has registered blueprints."""
        app = create_app()
        # Check that blueprints are registered
        blueprint_names = [bp.name for bp in app.blueprints.values()]
        assert "api" in blueprint_names or any("api" in name for name in blueprint_names)

    def test_app_logging_configured(self):
        """Test that logging is configured."""
        app = create_app()
        assert app.logger is not None
        assert len(app.logger.handlers) > 0
