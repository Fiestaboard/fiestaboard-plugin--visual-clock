"""Test fixtures for Visual Clock plugin."""

import pytest


@pytest.fixture
def manifest():
    """Return a basic manifest for testing."""
    return {
        "id": "visual_clock",
        "name": "Visual Clock",
        "version": "1.0.0",
        "description": "Displays a full-screen clock with large pixel-art style digits.",
        "settings_schema": {
            "type": "object",
            "properties": {
                "timezone": {"type": "string", "default": "America/Los_Angeles"},
                "time_format": {"type": "string", "enum": ["12h", "24h"], "default": "12h"},
                "color_pattern": {"type": "string", "enum": ["solid", "pride", "rainbow", "sunset", "ocean", "retro", "christmas", "halloween"], "default": "solid"},
                "digit_color": {"type": "string", "default": "white"},
                "background_color": {"type": "string", "default": "black"},
            }
        },
        "variables": {
            "groups": {
                "display": {"label": "Display"},
                "time_data": {"label": "Time Data"}
            },
            "simple": {
                "visual_clock": {"description": "Full pixel-art clock display for the board", "type": "string", "max_length": 132, "group": "display", "example": "(clock pattern)"},
                "time": {"description": "Current time string", "type": "string", "max_length": 8, "group": "time_data", "example": "2:30 PM"},
                "time_format": {"description": "Active time format (12h or 24h)", "type": "string", "max_length": 3, "group": "time_data", "example": "12h"},
                "hour": {"description": "Current hour", "type": "number", "max_length": 2, "group": "time_data", "example": "14"},
                "minute": {"description": "Current minute", "type": "number", "max_length": 2, "group": "time_data", "example": "30"}
            }
        }
    }
