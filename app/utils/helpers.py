"""
app/utils/helpers.py — Shared utility functions for the DailyDigest application.

These are pure, reusable functions with no side effects.
"""

from datetime import datetime, time, timedelta


def last_scheduled_digest_time(digest_time: time, now: datetime) -> datetime:
    """
    Returns the most recent past datetime when this user's digest was due.

    Always returns a datetime in the past (or equal to now), never in the future.

    Examples:
        digest_time=23:00, now=01:00 AM next day → yesterday at 23:00
        digest_time=08:00, now=10:00 AM          → today at 08:00
        digest_time=08:00, now=07:00 AM          → yesterday at 08:00
    """
    candidate = now.replace(
        hour=digest_time.hour,
        minute=digest_time.minute,
        second=0,
        microsecond=0,
    )
    if candidate > now:
        candidate -= timedelta(days=1)
    return candidate