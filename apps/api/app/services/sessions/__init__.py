"""Study sessions: an append-only event log per session, replayed into state and totals.

Every function takes a keyword-only ``user_id`` and filters on it. Another
user's ID behaves exactly like a missing one (``NotFound``).
"""
