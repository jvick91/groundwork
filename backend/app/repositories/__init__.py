"""Per-aggregate Repository classes (ADR-009).

Each ``<aggregate>_repository.py`` file owns every query against its
aggregate's tables — no module-level lookup tables, no generic base class.
"""
