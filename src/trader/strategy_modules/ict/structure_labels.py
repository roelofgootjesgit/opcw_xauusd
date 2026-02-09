"""
Structure labels (OCLW_PRINCIPLES): exact één per timeframe.

- BULLISH_STRUCTURE → alleen LONGS
- BEARISH_STRUCTURE → alleen SHORTS
- RANGE → NO TRADE

HTF (e.g. H1) drives context; nooit tegen H1-structuur in.
"""
from typing import Literal

StructureLabel = Literal["BULLISH_STRUCTURE", "BEARISH_STRUCTURE", "RANGE"]

BULLISH_STRUCTURE: StructureLabel = "BULLISH_STRUCTURE"
BEARISH_STRUCTURE: StructureLabel = "BEARISH_STRUCTURE"
RANGE: StructureLabel = "RANGE"

ALL_LABELS: tuple[StructureLabel, ...] = (BULLISH_STRUCTURE, BEARISH_STRUCTURE, RANGE)


def no_trade_for_structure(label: StructureLabel) -> bool:
    """RANGE = NO TRADE."""
    return label == RANGE


def direction_allowed_for_structure(label: StructureLabel, direction: str) -> bool:
    """Alleen LONGS bij BULLISH, alleen SHORTS bij BEARISH."""
    if label == RANGE:
        return False
    if label == BULLISH_STRUCTURE:
        return direction.upper() == "LONG"
    if label == BEARISH_STRUCTURE:
        return direction.upper() == "SHORT"
    return False
