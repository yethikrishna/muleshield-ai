"""
MuleShield AI - Structured Logging
Structlog configuration for JSON logging
"""

import structlog
import logging
from typing import Any


def configure_logging():
    """Configure structured logging"""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Set root logging level
    logging.basicConfig(level=logging.INFO)


def get_logger(name: str, **kwargs: Any) -> structlog.stdlib.BoundLogger:
    """Get a structured logger"""
    return structlog.get_logger(name, **kwargs)
