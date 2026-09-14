"""Timestamp helpers used to make pipeline outputs auditable."""

from datetime import datetime, timezone


def current_utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp suitable for a CSV datetime column."""
    return datetime.now(timezone.utc).isoformat()
