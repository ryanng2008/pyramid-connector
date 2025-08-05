"""Logging configuration and utilities."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

import structlog
import colorlog
from structlog.typing import Processor

from ..config.settings import get_settings


def setup_logging(
    log_level: Optional[str] = None,
    log_format: Optional[str] = None,
    log_file: Optional[str] = None
) -> None:
    """Set up logging configuration."""
    settings = get_settings()
    
    level = log_level or settings.logging.level
    format_type = log_format or settings.logging.format
    file_path = log_file or settings.logging.file_path
    
    # Configure standard library logging
    logging.basicConfig(level=getattr(logging, level.upper()))
    
    # Set up processors based on format
    processors: list[Processor] = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]
    
    if format_type == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Set up file logging if specified
    if file_path:
        setup_file_logging(file_path, level)
    
    # Set up colored console logging
    setup_console_logging(level)


def setup_file_logging(file_path: str, level: str) -> None:
    """Set up file logging with rotation."""
    log_file = Path(file_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Create a rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        file_path,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(getattr(logging, level.upper()))
    
    # JSON formatter for file logs
    file_formatter = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
        '"logger": "%(name)s", "message": "%(message)s"}'
    )
    file_handler.setFormatter(file_formatter)
    
    # Add handler to root logger
    logging.getLogger().addHandler(file_handler)


def setup_console_logging(level: str) -> None:
    """Set up colored console logging."""
    console_handler = colorlog.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    
    # Colored formatter for console
    console_formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        reset=True,
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )
    console_handler.setFormatter(console_formatter)
    
    # Add handler to root logger
    logging.getLogger().addHandler(console_handler)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


class LoggerMixin:
    """Mixin class to add logging capabilities to any class."""
    
    @property
    def logger(self) -> structlog.stdlib.BoundLogger:
        """Get logger instance for this class."""
        return get_logger(self.__class__.__name__)


# Performance logging decorator
def log_execution_time(func):
    """Decorator to log function execution time."""
    import time
    import functools
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__name__)
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.info(
                "Function executed successfully",
                function=func.__name__,
                execution_time=f"{execution_time:.4f}s"
            )
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                "Function execution failed",
                function=func.__name__,
                execution_time=f"{execution_time:.4f}s",
                error=str(e)
            )
            raise
    
    return wrapper


# Async version of the decorator
def log_async_execution_time(func):
    """Decorator to log async function execution time."""
    import time
    import functools
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        logger = get_logger(func.__name__)
        start_time = time.time()
        
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.info(
                "Async function executed successfully",
                function=func.__name__,
                execution_time=f"{execution_time:.4f}s"
            )
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                "Async function execution failed",
                function=func.__name__,
                execution_time=f"{execution_time:.4f}s",
                error=str(e)
            )
            raise
    
    return wrapper