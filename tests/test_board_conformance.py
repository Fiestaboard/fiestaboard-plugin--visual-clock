"""Board-geometry conformance: the clock must render on every board shape.

The shared suite (FiestaBoard core's ``src/plugins/geometry_conformance``) is
the same definition core holds its own plugins to. The extra tests here pin
the two things the suite cannot know about this plugin: that the art is
actually *drawn* (a blank board of the right size would satisfy any bounds
check), and that it is centred rather than pinned to the top-left.
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import pytz

from plugins.visual_clock import VisualClockPlugin, choose_layout
from src.board_chars import BoardChars
from src.devices import BoardContext
from src.plugins.geometry_conformance import assert_board_conformance
from src.text_to_board import count_tiles

MANIFEST = json.loads((Path(__file__).resolve().parent.parent / "manifest.json").read_text())

# A time with two hour digits and two minute digits, so the ink reaches every
# edge of the layout box and the centring assertions have something to measure.
FIXED_TIME = datetime(2024, 6, 15, 12, 34, tzinfo=pytz.UTC)

# Every shape a user can own, plus the two FiestaPanel sizes. A note array is
# not simply "bigger": 15x12 is narrower than a Flagship and twice as tall,
# 120x3 is wider and shorter.
GEOMETRIES = [
    ("flagship", 6, 22),
    ("note", 3, 15),
    ("panel 65in", 12, 30),
    ("panel 85in", 18, 45),
    ("tall-narrow", 12, 15),
    ("wide-short", 3, 120),
    ("max array", 24, 120),
    ("tall array", 24, 15),
]


def make_plugin() -> VisualClockPlugin:
    """A fresh, configured clock. It has no network to stub."""
    plugin = VisualClockPlugin(MANIFEST)
    plugin.config = {
        "timezone": "UTC",
        "time_format": "24h",
        "color_pattern": "solid",
        "digit_color": "white",
        "background_color": "black",
    }
    return plugin


def render(rows: int, cols: int) -> list[str]:
    """Board lines for a ``rows x cols`` board at :data:`FIXED_TIME`."""
    plugin = make_plugin()
    board = BoardContext(device_type="note_array", rows=rows, cols=cols)
    with patch("plugins.visual_clock.datetime") as mock_datetime:
        mock_datetime.now.return_value = FIXED_TIME
        result = plugin.get_data(board)
    return result.formatted_lines


def ink_box(rows: int, cols: int) -> tuple:
    """Bounding box ``(top, bottom, left, right)`` of non-background tiles."""
    plugin = make_plugin()
    board = BoardContext(device_type="note_array", rows=rows, cols=cols)
    with patch("plugins.visual_clock.datetime") as mock_datetime:
        mock_datetime.now.return_value = FIXED_TIME
        array = plugin.get_data(board).data["visual_clock_array"]

    marked = [
        (r, c)
        for r, row in enumerate(array)
        for c, code in enumerate(row)
        if code != BoardChars.BLACK
    ]
    assert marked, f"{cols}x{rows} rendered an empty board"
    return (
        min(r for r, _ in marked),
        max(r for r, _ in marked),
        min(c for _, c in marked),
        max(c for _, c in marked),
    )


def test_renders_on_every_board_shape():
    """The shared conformance suite, including the note_array preview check."""
    report = assert_board_conformance(
        make_plugin,
        manifest=MANIFEST,
        strict_growth=True,
        require_note_array_preview=True,
    )
    # A plugin that emits no whole-board content passes every bounds check
    # vacuously. This clock does emit it, so the absence of that warning is
    # what proves the row and width checks actually ran.
    codes = {warning.code for warning in report.warnings}
    assert "NO_BOARD_OUTPUT" not in codes, report.summary()


@pytest.mark.parametrize("label,rows,cols", GEOMETRIES)
def test_fills_the_board_exactly(label, rows, cols):
    """One row per board row, each exactly the board's width in tiles."""
    lines = render(rows, cols)
    assert len(lines) == rows, label
    for index, line in enumerate(lines):
        assert count_tiles(line) == cols, f"{label} row {index}: {line!r}"


@pytest.mark.parametrize("label,rows,cols", GEOMETRIES)
def test_draws_the_time_centred(label, rows, cols):
    """The art is drawn, and centred on both axes rather than pinned to 0,0."""
    top, bottom, left, right = ink_box(rows, cols)

    assert abs(top - (rows - 1 - bottom)) <= 1, f"{label}: art is not vertically centred"
    assert abs(left - (cols - 1 - right)) <= 1, f"{label}: art is not horizontally centred"


@pytest.mark.parametrize(
    "rows,cols,expected",
    [
        # Flagship: the big inline unit is exactly 22x6.
        (6, 22, ("big", False, 1)),
        # A full 8x8 array is 5 flagships wide but only 4 tall, so 4 is the
        # scale both axes can afford.
        (24, 120, ("big", False, 4)),
        (18, 45, ("big", False, 2)),
        # Narrower than a Flagship: the inline unit cannot fit at any scale,
        # so hours stack over minutes.
        (12, 15, ("compact", True, 1)),
        (24, 15, ("compact", True, 2)),
        # Three rows cannot hold a legible bitmap digit at all.
        (3, 15, None),
        (3, 120, None),
    ],
)
def test_layout_choice(rows, cols, expected):
    """The layout decision itself, pinned per geometry."""
    layout = choose_layout(rows, cols)
    if expected is None:
        assert layout is None
        return
    assert layout is not None
    assert (layout.glyphs.name, layout.stacked, layout.scale) == expected


def test_unbound_board_assumes_a_flagship():
    """``self.board`` is None on legacy paths; that must mean 22x6, not a crash."""
    plugin = make_plugin()
    result = plugin.get_data(None)
    assert result.available
    assert len(result.formatted_lines) == 6
    assert all(count_tiles(line) == 22 for line in result.formatted_lines)


def test_taller_boards_use_bigger_digits():
    """Growth for a clock is glyph size, not item count: more board, bigger time."""
    heights = [choose_layout(rows, 120).digit_height for rows in (6, 12, 24)]
    assert heights == sorted(heights)
    assert heights[0] < heights[-1]
