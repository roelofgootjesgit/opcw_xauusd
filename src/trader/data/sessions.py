"""
Session names (OCLW_PRINCIPLES): London, NY = entries; Asia = range-detectie only, no entry.
"""
from datetime import datetime

SESSION_LONDON = "London"
SESSION_NY = "New York"
SESSION_ASIA = "Asia"

# Sessions waar entry toegestaan is (na sweep + structure + validatie)
ENTRY_SESSIONS = (SESSION_LONDON, SESSION_NY)

# Alleen range-detectie, geen entries
RANGE_ONLY_SESSIONS = (SESSION_ASIA,)


def session_from_timestamp(ts) -> str:
    """
    Bepaal sessie uit timestamp (veronderstelt UTC).
    ICT killzones: London 07–10 UTC, New York 12–15 UTC, rest Asia.
    """
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    h = getattr(ts, "hour", 0)
    if 7 <= h < 10:
        return SESSION_LONDON
    if 12 <= h < 15:
        return SESSION_NY
    return SESSION_ASIA
