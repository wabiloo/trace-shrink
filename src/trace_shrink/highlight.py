"""
Highlight color mapping for trace entries.

This module provides the mapping between string highlight names and their
corresponding integer values used in Proxyman format.
"""

# Mapping from string highlight names to Proxyman color integer values
HIGHLIGHT_COLOR_MAP = {
    "red": 0,
    "yellow": 1,
    "green": 2,
    "blue": 3,
    "purple": 4,
    "grey": 5,
}

# Valid highlight values (colors + strike)
VALID_HIGHLIGHT_VALUES = list(HIGHLIGHT_COLOR_MAP.keys()) + ["strike"]


def validate_highlight(highlight: str) -> None:
    """
    Validate that a highlight value is valid.

    Args:
        highlight: The highlight value to validate.

    Raises:
        ValueError: If the highlight value is invalid.
    """
    if highlight not in VALID_HIGHLIGHT_VALUES:
        raise ValueError(
            f"Invalid highlight value '{highlight}'. "
            f"Valid values are: {', '.join(VALID_HIGHLIGHT_VALUES)}"
        )

