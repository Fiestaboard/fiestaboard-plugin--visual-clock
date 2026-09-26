"""Visual Clock plugin for FiestaBoard.

Draws the time as pixel-art digits sized to whatever board it is rendering
on: a Flagship (22x6), a Note (15x3), or any note array from 15x3 up to
120x24 (which is what a FiestaPanel is).

Nothing here is measured in literal tiles. The art is a glyph unit that is
integer-scaled and centred:

* ``BIG`` digits are 6x4 and their inline ``HH:MM`` unit is exactly 22x6 --
  a Flagship at scale 1, and 88x24 at scale 4 on a full 8x8 array.
* ``COMPACT`` digits are 5x3, for boards too narrow for the inline big unit.
  Their *stacked* unit (``HH`` over ``MM``) is 7x11, which is what makes a
  tall-narrow array (15x12 -- narrower than a Flagship and twice as tall)
  render real digits instead of nothing.
* Below five rows no bitmap digit is legible -- three rows cannot express a
  digit without collisions -- so a board that short falls back to the board's
  own letterforms, letter-spaced to the width it has.

The chosen layout is the one with the tallest rendered digits, then the one
covering the most board. Every guard bounds against the real array, so a
layout bug clips instead of raising.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

import pytz

from src.board_chars import BoardChars
from src.devices import BoardContext
from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# A plugin is rendered with no board bound on legacy paths and in unit tests.
# The contract is "assume a Flagship", read from the device table rather than
# retyped here as 6 and 22.
DEFAULT_BOARD = BoardContext.from_device_type("flagship")

# One tile of clear space between neighbouring glyphs, scaled with the art.
GLYPH_GAP = 1

# Color code mapping
COLOR_MAP = {
    "red": BoardChars.RED,
    "orange": BoardChars.ORANGE,
    "yellow": BoardChars.YELLOW,
    "green": BoardChars.GREEN,
    "blue": BoardChars.BLUE,
    "violet": BoardChars.VIOLET,
    "white": BoardChars.WHITE,
    "black": BoardChars.BLACK,
}

# Color patterns - define colors for each of the 5 elements (h1, h2, colon, m1, m2)
# or row-based colors for gradient patterns
COLOR_PATTERNS = {
    # Pride: each row is a different rainbow color
    "pride": {
        "type": "per_row",
        "colors": ["red", "orange", "yellow", "green", "blue", "violet"],
    },
    # Rainbow: each digit is a different rainbow color
    "rainbow": {
        "type": "per_digit",
        "colors": ["red", "orange", "yellow", "green", "blue", "violet"],
    },
    # Sunset: warm gradient from top to bottom
    "sunset": {
        "type": "per_row",
        "colors": ["red", "red", "orange", "orange", "yellow", "yellow"],
    },
    # Ocean: cool gradient from top to bottom
    "ocean": {
        "type": "per_row",
        "colors": ["blue", "blue", "green", "green", "violet", "violet"],
    },
    # Retro: classic amber LED look
    "retro": {
        "type": "per_row",
        "colors": ["orange", "orange", "yellow", "yellow", "orange", "orange"],
    },
    # Christmas: alternating red and green
    "christmas": {
        "type": "per_digit",
        "colors": ["red", "green", "red", "green", "red", "green"],
    },
    # Halloween: alternating orange and violet
    "halloween": {
        "type": "per_digit",
        "colors": ["orange", "violet", "orange", "violet", "orange", "violet"],
    },
}

# Digit patterns (6 rows x 4 columns each) - full board height
# 1 = foreground (digit color), 0 = background
# All digits designed with consistent visual weight (2-col minimum strokes)
DIGIT_PATTERNS = {
    0: [
        [1, 1, 1, 1],
        [1, 0, 0, 1],
        [1, 0, 0, 1],
        [1, 0, 0, 1],
        [1, 0, 0, 1],
        [1, 1, 1, 1],
    ],
    1: [
        [0, 1, 1, 0],
        [1, 1, 1, 0],
        [0, 1, 1, 0],
        [0, 1, 1, 0],
        [0, 1, 1, 0],
        [1, 1, 1, 1],
    ],
    2: [
        [1, 1, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
        [1, 1, 1, 1],
        [1, 1, 0, 0],
        [1, 1, 1, 1],
    ],
    3: [
        [1, 1, 1, 1],
        [0, 0, 1, 1],
        [1, 1, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
        [1, 1, 1, 1],
    ],
    4: [
        [1, 0, 0, 1],
        [1, 0, 0, 1],
        [1, 0, 0, 1],
        [1, 1, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
    ],
    5: [
        [1, 1, 1, 1],
        [1, 1, 0, 0],
        [1, 1, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
        [1, 1, 1, 1],
    ],
    6: [
        [1, 1, 1, 1],
        [1, 1, 0, 0],
        [1, 1, 1, 1],
        [1, 1, 0, 1],
        [1, 0, 0, 1],
        [1, 1, 1, 1],
    ],
    7: [
        [1, 1, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
    ],
    8: [
        [1, 1, 1, 1],
        [1, 0, 0, 1],
        [1, 1, 1, 1],
        [1, 1, 1, 1],
        [1, 0, 0, 1],
        [1, 1, 1, 1],
    ],
    9: [
        [1, 1, 1, 1],
        [1, 0, 0, 1],
        [1, 1, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
        [1, 1, 1, 1],
    ],
}

# Colon pattern (6 rows x 2 columns) - full board height
# Dots at rows 1-2 and 4-5 for visibility
COLON_PATTERN = [
    [0, 0],
    [1, 1],
    [0, 0],
    [0, 0],
    [1, 1],
    [0, 0],
]


# Compact digits (5 rows x 3 columns) and their 5x1 colon. Five rows is the
# floor for a legible bitmap digit: with three, 2/3/5 and 0/8 collapse into
# each other whatever you do with the columns, which is why short boards get
# letterforms instead of a third, unreadable font.
COMPACT_DIGIT_PATTERNS = {
    0: [
        [1, 1, 1],
        [1, 0, 1],
        [1, 0, 1],
        [1, 0, 1],
        [1, 1, 1],
    ],
    1: [
        [0, 1, 0],
        [1, 1, 0],
        [0, 1, 0],
        [0, 1, 0],
        [1, 1, 1],
    ],
    2: [
        [1, 1, 1],
        [0, 0, 1],
        [1, 1, 1],
        [1, 0, 0],
        [1, 1, 1],
    ],
    3: [
        [1, 1, 1],
        [0, 0, 1],
        [1, 1, 1],
        [0, 0, 1],
        [1, 1, 1],
    ],
    4: [
        [1, 0, 1],
        [1, 0, 1],
        [1, 1, 1],
        [0, 0, 1],
        [0, 0, 1],
    ],
    5: [
        [1, 1, 1],
        [1, 0, 0],
        [1, 1, 1],
        [0, 0, 1],
        [1, 1, 1],
    ],
    6: [
        [1, 1, 1],
        [1, 0, 0],
        [1, 1, 1],
        [1, 0, 1],
        [1, 1, 1],
    ],
    7: [
        [1, 1, 1],
        [0, 0, 1],
        [0, 1, 0],
        [0, 1, 0],
        [0, 1, 0],
    ],
    8: [
        [1, 1, 1],
        [1, 0, 1],
        [1, 1, 1],
        [1, 0, 1],
        [1, 1, 1],
    ],
    9: [
        [1, 1, 1],
        [1, 0, 1],
        [1, 1, 1],
        [0, 0, 1],
        [1, 1, 1],
    ],
}

COMPACT_COLON_PATTERN = [
    [0],
    [1],
    [0],
    [1],
    [0],
]


@dataclass(frozen=True)
class GlyphSet:
    """A digit font and the colon drawn beside it.

    Dimensions are read off the bitmaps, so adding or reshaping a font needs
    no matching constant anywhere else.
    """

    name: str
    digits: Dict[int, List[List[int]]]
    colon: List[List[int]]

    @property
    def height(self) -> int:
        return len(self.colon)

    @property
    def digit_width(self) -> int:
        return len(self.digits[0][0])

    @property
    def colon_width(self) -> int:
        return len(self.colon[0])

    @property
    def weight(self) -> int:
        """Tiles in one digit: the tie-break that prefers the richer font."""
        return self.height * self.digit_width


BIG = GlyphSet("big", DIGIT_PATTERNS, COLON_PATTERN)
COMPACT = GlyphSet("compact", COMPACT_DIGIT_PATTERNS, COMPACT_COLON_PATTERN)

GLYPH_SETS = (BIG, COMPACT)


@dataclass(frozen=True)
class Layout:
    """One way to arrange the clock, at one integer scale.

    ``inline`` is ``H H : M M`` on a single glyph line; ``stacked`` is ``HH``
    over ``MM`` with the colon dropped, because the line break already
    separates hours from minutes.
    """

    glyphs: GlyphSet
    stacked: bool
    scale: int

    @property
    def unit_width(self) -> int:
        if self.stacked:
            return 2 * self.glyphs.digit_width + GLYPH_GAP
        return 4 * self.glyphs.digit_width + self.glyphs.colon_width + 4 * GLYPH_GAP

    @property
    def unit_height(self) -> int:
        if self.stacked:
            return 2 * self.glyphs.height + GLYPH_GAP
        return self.glyphs.height

    @property
    def width(self) -> int:
        return self.unit_width * self.scale

    @property
    def height(self) -> int:
        return self.unit_height * self.scale

    @property
    def digit_height(self) -> int:
        """Rendered height of one digit -- how big the clock actually reads."""
        return self.glyphs.height * self.scale


def choose_layout(rows: int, cols: int) -> "Layout | None":
    """Pick the arrangement that draws the biggest legible clock on ``rows x cols``.

    Candidates are every (glyph set, arrangement) pair at its largest integer
    scale that still fits. The winner has the tallest digits; ties go to the
    layout covering more of the board, then to the inline reading order, then
    to the richer font. Returns ``None`` when no bitmap fits -- the caller
    falls back to letterforms.
    """
    best_key = None
    best_layout = None
    for glyphs in GLYPH_SETS:
        for stacked in (False, True):
            probe = Layout(glyphs, stacked, 1)
            scale = min(rows // probe.unit_height, cols // probe.unit_width)
            if scale < 1:
                continue
            layout = Layout(glyphs, stacked, scale)
            key = (
                layout.digit_height,
                layout.width * layout.height,
                0 if stacked else 1,
                glyphs.weight,
            )
            if best_key is None or key > best_key:
                best_key, best_layout = key, layout
    return best_layout


def letter_spaced(text: str, cols: int) -> str:
    """Widen ``text`` with even letter spacing while it still fits ``cols``.

    A five-tile time string on a 120-tile row is a rounding error; spacing it
    out is the only way a text fallback can answer a wider board at all.
    """
    gap = 0
    while gap < 3 and len(text) + (len(text) - 1) * (gap + 1) <= cols:
        gap += 1
    return (" " * gap).join(text)


# Board codes that are characters rather than colour flaps, so a text
# fallback survives the trip back out through _array_to_string.
_CODE_TO_CHAR = {}
for _char in " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:.,-+/?!":
    _code = BoardChars.get_char_code(_char)
    if _code is not None:
        _CODE_TO_CHAR.setdefault(_code, _char)


class VisualClockPlugin(PluginBase):
    """Visual clock plugin.
    
    Displays a full-screen clock with large pixel-art style digits.
    """
    
    @property
    def plugin_id(self) -> str:
        return "visual_clock"
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate visual clock configuration."""
        errors = []
        
        # Validate timezone
        timezone = config.get("timezone", "America/Los_Angeles")
        try:
            pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            errors.append(f"Invalid timezone: {timezone}")
        
        # Validate time format
        time_format = config.get("time_format", "12h")
        if time_format not in ["12h", "24h"]:
            errors.append(f"Invalid time format: {time_format}. Must be '12h' or '24h'.")
        
        # Validate color pattern
        color_pattern = config.get("color_pattern", "solid")
        valid_patterns = ["solid"] + list(COLOR_PATTERNS.keys())
        if color_pattern not in valid_patterns:
            errors.append(f"Invalid color pattern: {color_pattern}")
        
        # Validate colors
        digit_color = config.get("digit_color", "white")
        if digit_color not in COLOR_MAP:
            errors.append(f"Invalid digit color: {digit_color}")
        
        background_color = config.get("background_color", "black")
        if background_color not in COLOR_MAP:
            errors.append(f"Invalid background color: {background_color}")
        
        return errors
    
    def fetch_data(self) -> PluginResult:
        """Fetch current time and render the clock for the bound board."""
        try:
            timezone_str = self.config.get("timezone", "America/Los_Angeles")
            time_format = self.config.get("time_format", "12h")
            color_pattern = self.config.get("color_pattern", "solid")
            digit_color = self.config.get("digit_color", "white")
            background_color = self.config.get("background_color", "black")

            tz = pytz.timezone(timezone_str)
            now = datetime.now(tz)

            if time_format == "12h":
                hour = now.hour % 12
                if hour == 0:
                    hour = 12
                time_str = now.strftime("%I:%M %p").lstrip("0")
            else:
                hour = now.hour
                time_str = now.strftime("%H:%M")

            minute = now.minute

            clock_array = self._generate_clock_display(
                hour, minute, color_pattern, digit_color, background_color
            )
            clock_lines = self._array_to_lines(clock_array)

            data = {
                "visual_clock": "\n".join(clock_lines),
                "visual_clock_array": clock_array,
                "time": time_str,
                "time_format": time_format,
                "hour": str(hour),
                "minute": str(minute).zfill(2),
            }

            # formatted_lines is the live whole-board path (displays/service.py);
            # every row is exactly board.cols tiles, so a page that drops the
            # variable on a line splits it one row per board row on any board.
            return PluginResult(
                available=True,
                data=data,
                formatted_lines=clock_lines,
            )

        except Exception as e:
            logger.exception("Error fetching visual clock data")
            return PluginResult(
                available=False,
                error=str(e)
            )

    def get_formatted_display(self) -> "List[str] | None":
        """Whole-board rendering for the documented single-page hook."""
        result = self.fetch_data()
        return result.formatted_lines if result.available else None

    def _board_size(self) -> "tuple[int, int]":
        """``(rows, cols)`` of the board being rendered, Flagship if unbound."""
        board = self.board or DEFAULT_BOARD
        return board.rows, board.cols

    def _generate_clock_display(
        self,
        hour: int,
        minute: int,
        color_pattern: str,
        digit_color: str,
        background_color: str
    ) -> List[List[int]]:
        """Render the clock as a ``board.rows x board.cols`` array of codes.

        The art is the largest glyph layout that fits (see :func:`choose_layout`),
        centred on both axes. The hours slot keeps its width even when the
        leading zero is blank, so the clock does not shuffle sideways as the
        hour rolls over.

        Args:
            hour: Hour value (1-12 for 12h, 0-23 for 24h)
            minute: Minute value (0-59)
            color_pattern: Color pattern name ("solid", "pride", etc.)
            digit_color: Color name for solid pattern
            background_color: Color name for background

        Returns:
            Array of character codes, one row per board row.
        """
        rows, cols = self._board_size()
        bg = COLOR_MAP.get(background_color, BoardChars.BLACK)
        board = [[bg for _ in range(cols)] for _ in range(rows)]

        layout = choose_layout(rows, cols)
        if layout is None:
            self._draw_text_clock(board, hour, minute)
            return board

        colors = self._element_colors(color_pattern, digit_color, layout.glyphs.height)
        digits = {
            "h1": hour // 10,
            "h2": hour % 10,
            "m1": minute // 10,
            "m2": minute % 10,
        }

        row_offset = (rows - layout.height) // 2
        col_offset = (cols - layout.width) // 2

        for name, pattern, row, col in self._placements(layout, digits):
            # A blank leading hour digit still reserves its slot above.
            if name == "h1" and digits["h1"] == 0:
                continue
            self._blit(
                board,
                pattern,
                row_offset + row * layout.scale,
                col_offset + col * layout.scale,
                layout.scale,
                colors[name],
                bg,
            )

        return board

    @staticmethod
    def _placements(layout: Layout, digits: Dict[str, int]) -> List[tuple]:
        """Glyph placements in unscaled unit coordinates.

        Positions accumulate from the glyph widths, so a different font or a
        different gap moves everything without a second set of numbers to
        keep in step.
        """
        glyphs = layout.glyphs
        step = glyphs.digit_width + GLYPH_GAP

        if layout.stacked:
            return [
                ("h1", glyphs.digits[digits["h1"]], 0, 0),
                ("h2", glyphs.digits[digits["h2"]], 0, step),
                ("m1", glyphs.digits[digits["m1"]], glyphs.height + GLYPH_GAP, 0),
                ("m2", glyphs.digits[digits["m2"]], glyphs.height + GLYPH_GAP, step),
            ]

        colon_col = 2 * step
        minutes_col = colon_col + glyphs.colon_width + GLYPH_GAP
        return [
            ("h1", glyphs.digits[digits["h1"]], 0, 0),
            ("h2", glyphs.digits[digits["h2"]], 0, step),
            ("colon", glyphs.colon, 0, colon_col),
            ("m1", glyphs.digits[digits["m1"]], 0, minutes_col),
            ("m2", glyphs.digits[digits["m2"]], 0, minutes_col + step),
        ]

    @staticmethod
    def _element_colors(color_pattern: str, digit_color: str, glyph_height: int) -> Dict[str, List[int]]:
        """Per-glyph-row colours for each element of the clock.

        Colours are indexed by *glyph* row, not board row, so a gradient
        stretches with the art instead of banding it at scale 4.
        """
        if color_pattern == "solid" or color_pattern not in COLOR_PATTERNS:
            fg = COLOR_MAP.get(digit_color, BoardChars.WHITE)
            uniform = [fg] * glyph_height
            return {name: uniform for name in ("h1", "h2", "colon", "m1", "m2")}

        pattern = COLOR_PATTERNS[color_pattern]
        if pattern["type"] == "per_row":
            row_colors = [COLOR_MAP[c] for c in pattern["colors"]]
            return {name: row_colors for name in ("h1", "h2", "colon", "m1", "m2")}

        palette = pattern["colors"]
        return {
            name: [COLOR_MAP[palette[index % len(palette)]]] * glyph_height
            for index, name in enumerate(("h1", "h2", "colon", "m1", "m2"))
        }

    def _draw_text_clock(self, board: List[List[int]], hour: int, minute: int) -> None:
        """Fallback for boards too short for a bitmap digit (any 3-row board).

        The board has real letterforms; three rows do not have a legible
        bitmap digit. The time is letter-spaced to the width available and
        centred. Character tiles carry no colour, so the digit colour does
        not apply here -- the background still does.
        """
        rows = len(board)
        cols = len(board[0]) if board else 0
        if not rows or not cols:
            return

        text = letter_spaced(f"{hour}:{minute:02d}", cols)
        codes = BoardChars.text_to_codes(text)[:cols]
        row = (rows - 1) // 2
        col_start = (cols - len(codes)) // 2

        for index, code in enumerate(codes):
            # Spaces keep the background tile rather than punching a hole in it.
            if code == BoardChars.SPACE:
                continue
            col = col_start + index
            if 0 <= col < cols:
                board[row][col] = code

    def _blit(
        self,
        board: List[List[int]],
        pattern: List[List[int]],
        row_start: int,
        col_start: int,
        scale: int,
        row_colors: List[int],
        bg: int
    ) -> None:
        """Draw one glyph onto the board, each cell a ``scale x scale`` block.

        Bounds come from the array being written to, never from a constant,
        so a layout that miscalculates clips instead of raising -- and the
        conformance suite still sees the overflow as an out-of-bounds row.

        Args:
            board: The board array to modify, sized to the real board
            pattern: Glyph bitmap, 1 = foreground, 0 = background
            row_start: Top row of the glyph
            col_start: Left column of the glyph
            scale: Integer magnification
            row_colors: Colour codes indexed by glyph row
            bg: Background color code
        """
        rows = len(board)
        cols = len(board[0]) if board else 0
        for row_idx, pattern_row in enumerate(pattern):
            fg = row_colors[row_idx] if row_idx < len(row_colors) else row_colors[-1]
            for col_idx, val in enumerate(pattern_row):
                code = fg if val == 1 else bg
                for dr in range(scale):
                    board_row = row_start + row_idx * scale + dr
                    if not 0 <= board_row < rows:
                        continue
                    for dc in range(scale):
                        board_col = col_start + col_idx * scale + dc
                        if 0 <= board_col < cols:
                            board[board_row][board_col] = code

    def _array_to_lines(self, array: List[List[int]]) -> List[str]:
        """Convert a board array to one string per row.

        Colour tiles become named markers (one tile, four characters);
        character tiles become their character. Each row is therefore exactly
        as many tiles as the board is wide.
        """
        color_markers = {
            BoardChars.RED: "{red}",
            BoardChars.ORANGE: "{orange}",
            BoardChars.YELLOW: "{yellow}",
            BoardChars.GREEN: "{green}",
            BoardChars.BLUE: "{blue}",
            BoardChars.VIOLET: "{violet}",
            BoardChars.WHITE: "{white}",
            BoardChars.BLACK: "{black}",
        }

        lines = []
        for row in array:
            line = ""
            for code in row:
                if code in color_markers:
                    line += color_markers[code]
                else:
                    line += _CODE_TO_CHAR.get(code, " ")
            lines.append(line)

        return lines

    def _array_to_string(self, array: List[List[int]]) -> str:
        """Newline-separated board rows, as the ``visual_clock`` variable."""
        return "\n".join(self._array_to_lines(array))



Plugin = VisualClockPlugin
