"""User-scoped data access for modules, topics, assessments and tasks.

Every function takes a keyword-only ``user_id`` and filters on it. Another
user's ID behaves exactly like a missing one (``NotFound``).
"""
