"""
Logging configuration for DICTATOR
Provides centralized logging with file rotation and configurable levels
"""

import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
import platformdirs


# Global logger registry
_loggers = {}
_log_level = logging.INFO
_log_dir = None


def setup_logging(log_dir=None, max_files=10, max_bytes=10*1024*1024):
    """
    Set up logging configuration with file rotation.

    Args:
        log_dir: Directory for log files. Defaults to ~/.config/dictator/logs/
        max_files: Maximum number of log files to keep (default: 10)
        max_bytes: Maximum size per log file in bytes (default: 10MB)
    """
    global _log_dir

    # Determine log directory
    if log_dir is None:
        app_dir = platformdirs.user_config_dir("dictator", "dictator")
        log_dir = str(Path(app_dir) / "logs")

    _log_dir = Path(log_dir)

    # Create log directory if it doesn't exist
    _log_dir.mkdir(parents=True, exist_ok=True)

    # Log file name with date
    log_file = _log_dir / f"dictator_{datetime.now().strftime('%Y%m%d')}.log"

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(_log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Create rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=max_files - 1,  # -1 because current file counts as 1
        encoding='utf-8'
    )
    file_handler.setLevel(_log_level)

    # Create console handler for errors and above
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers to root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Clean up old log files (keep only max_files)
    _cleanup_old_logs(max_files)

    logging.info("Logging system initialized")
    logging.info(f"Log directory: {_log_dir}")
    logging.info(f"Log level: {logging.getLevelName(_log_level)}")


def _cleanup_old_logs(max_files):
    """
    Remove old log files, keeping only the most recent max_files.

    Args:
        max_files: Maximum number of log files to keep
    """
    if not _log_dir:
        return

    # Get all log files sorted by modification time (newest first)
    log_files = sorted(
        _log_dir.glob("dictator_*.log*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    # Remove old files beyond max_files
    for old_file in log_files[max_files:]:
        try:
            old_file.unlink()
            logging.debug(f"Removed old log file: {old_file}")
        except Exception as e:
            logging.error(f"Failed to remove old log file {old_file}: {e}")


def get_logger(name):
    """
    Get a logger instance for the given name.

    Args:
        name: Logger name (typically __name__ or module name)

    Returns:
        logging.Logger instance
    """
    if name not in _loggers:
        logger = logging.getLogger(name)
        logger.setLevel(_log_level)
        _loggers[name] = logger

    return _loggers[name]


def set_log_level(level):
    """
    Set the global log level.

    Args:
        level: Log level as string ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
               or logging constant (logging.DEBUG, etc.)
    """
    global _log_level

    # Convert string to logging constant
    if isinstance(level, str):
        level = level.upper()
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        level = level_map.get(level, logging.INFO)

    _log_level = level

    # Update root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Update all registered loggers
    for logger in _loggers.values():
        logger.setLevel(level)

    # Update all handlers
    for handler in root_logger.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler.setLevel(level)

    logging.info(f"Log level changed to: {logging.getLevelName(level)}")


def get_log_level():
    """
    Get the current log level.

    Returns:
        Current log level as logging constant
    """
    return _log_level


def get_log_level_name():
    """
    Get the current log level name.

    Returns:
        Current log level name as string ('DEBUG', 'INFO', etc.)
    """
    return logging.getLevelName(_log_level)
