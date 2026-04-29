"""
Structured logging with PHI field exclusion.

Uses structlog for JSON-formatted logging. A custom processor strips
any PHI fields before they reach the log output.

The exclusion list lives in ``app.core.phi`` (SPEC-006 §7 — single
centralized exclusion list shared with the audit service).
"""

import logging

import structlog
from structlog.types import EventDict, WrappedLogger

from app.core.phi import PHI_EXCLUDED_FIELDS


def phi_filter(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Structlog processor that strips PHI fields from log events."""
    for field in PHI_EXCLUDED_FIELDS:
        event_dict.pop(field, None)
    return event_dict


def setup_logging(log_level: str = "INFO", log_json: bool = True) -> None:
    """Configure structlog with JSON or console rendering."""
    renderer = structlog.processors.JSONRenderer() if log_json else structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            phi_filter,
            renderer,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for the given module name."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
