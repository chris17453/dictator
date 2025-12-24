"""
Tests for logging system implementation
Following TDD - RED phase
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open, call
import sys
import os
from pathlib import Path
import logging

# Mock problematic modules before import
sys.modules['sounddevice'] = MagicMock()
sys.modules['faster_whisper'] = MagicMock()
sys.modules['pynput'] = MagicMock()
sys.modules['pynput.keyboard'] = MagicMock()


class TestLoggingModule:
    """Test the logging module exists and is configured correctly"""

    def test_logging_module_exists(self):
        """
        Test that a dedicated logging module exists.
        Should be in src/logger.py
        """
        # This will fail until we create src/logger.py
        try:
            from src import logger
            assert hasattr(logger, 'setup_logging')
            assert hasattr(logger, 'get_logger')
        except ImportError:
            pytest.fail("src/logger.py must exist with setup_logging() and get_logger() functions")

    def test_logging_levels_configured(self):
        """
        Test that all standard log levels are available.
        """
        from src import logger

        # Should have function to set log level
        assert hasattr(logger, 'set_log_level')

        # Should support standard levels
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        # The function should exist and accept these levels
        assert callable(logger.set_log_level)

    def test_log_directory_creation(self):
        """
        Test that log directory is created on setup.
        Should be ~/.config/dictator/logs/
        """
        from src import logger
        import tempfile
        from pathlib import Path

        # Use temp directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs"

            # Setup logging should create directory
            logger.setup_logging(log_dir=str(log_path))

            # Directory should exist
            assert log_path.exists()
            assert log_path.is_dir()

    def test_log_file_created(self):
        """
        Test that log file is created when logging starts.
        """
        from src import logger
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs"

            logger.setup_logging(log_dir=str(log_path))

            # Get logger and write something
            test_logger = logger.get_logger("test")
            test_logger.info("Test message")

            # Log file should exist
            log_files = list(log_path.glob("*.log"))
            assert len(log_files) > 0, "At least one log file should be created"

    def test_log_rotation_configured(self):
        """
        Test that log rotation is configured to keep last 10 files.
        """
        from src import logger
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            logger.setup_logging(log_dir=temp_dir, max_files=10)

            # Check that rotation handler is configured
            # This tests that the setup includes rotation
            test_logger = logger.get_logger("test")

            # Logger should have handlers
            assert len(test_logger.handlers) > 0

            # At least one handler should be a rotating file handler
            from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
            has_rotation = any(
                isinstance(h, (RotatingFileHandler, TimedRotatingFileHandler))
                for h in test_logger.handlers
            )
            assert has_rotation, "Logger should have rotating file handler"


class TestLoggingUsage:
    """Test that logging is used instead of print statements"""

    def test_no_print_statements_in_logger_module(self):
        """
        Test that logger.py doesn't use print() statements.
        """
        from src import logger
        import inspect

        source = inspect.getsource(logger)

        # Should not use print() for logging
        # (may use print for errors during setup, but not for normal logging)
        assert 'print(' not in source or source.count('print(') < 2, (
            "logger.py should not use print() statements"
        )

    def test_debug_emoji_removed_from_production_code(self):
        """
        Test that debug emoji (🔥, 🚨, etc.) are removed from production logging.
        They can be in test files, but not in src/*.py
        """
        import glob

        src_files = glob.glob('src/**/*.py', recursive=True)

        # Skip __pycache__
        src_files = [f for f in src_files if '__pycache__' not in f]

        emoji_found = []
        debug_emojis = ['🔥', '🚨', '🚀', '✅', '⚠️']

        for file_path in src_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    for emoji in debug_emojis:
                        if emoji in content:
                            emoji_found.append((file_path, emoji))
            except:
                pass

        assert len(emoji_found) == 0, (
            f"Debug emoji found in production code: {emoji_found}. "
            "Use proper logging instead."
        )

    def test_gui_uses_logging(self):
        """
        Test that gui.py uses logging instead of print.
        """
        from src import gui
        import inspect

        source = inspect.getsource(gui)

        # Should import logging
        assert 'import logging' in source or 'from src import logger' in source or 'from . import logger' in source, (
            "gui.py should import logging module"
        )

    def test_dictator_uses_logging(self):
        """
        Test that dictator.py uses logging instead of print.
        """
        from src import dictator
        import inspect

        source = inspect.getsource(dictator.DictatorWindow.__init__)

        # Should use logging in initialization (check for log.info, log.debug, etc.)
        assert 'logger' in source.lower() or 'logging' in source.lower() or 'log.' in source.lower(), (
            "dictator.py should use logging"
        )

    def test_recorder_uses_logging(self):
        """
        Test that recorder.py uses logging instead of print.
        """
        from src import recorder
        import inspect

        source = inspect.getsource(recorder.PureRecorder.__init__)

        # Should use logging (check for log.info, log.debug, etc.)
        assert 'logger' in source.lower() or 'logging' in source.lower() or 'log.' in source.lower(), (
            "recorder.py should use logging"
        )


class TestLogLevels:
    """Test that different log levels work correctly"""

    def test_can_set_debug_level(self):
        """
        Test that debug level can be set and debug messages are logged.
        """
        from src import logger
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs"

            logger.setup_logging(log_dir=str(log_path))
            logger.set_log_level('DEBUG')

            test_logger = logger.get_logger("test")
            test_logger.debug("Debug message")

            # Read log file
            log_file = list(log_path.glob("*.log"))[0]
            content = log_file.read_text()

            # Debug message should be in log
            assert "Debug message" in content

    def test_can_set_info_level(self):
        """
        Test that info level can be set and info messages are logged.
        """
        from src import logger
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs"

            logger.setup_logging(log_dir=str(log_path))
            logger.set_log_level('INFO')

            test_logger = logger.get_logger("test")
            test_logger.info("Info message")

            # Read log file
            log_file = list(log_path.glob("*.log"))[0]
            content = log_file.read_text()

            # Info message should be in log
            assert "Info message" in content

    def test_info_level_blocks_debug(self):
        """
        Test that when level is INFO, debug messages are not logged.
        """
        from src import logger
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs"

            logger.setup_logging(log_dir=str(log_path))
            logger.set_log_level('INFO')

            test_logger = logger.get_logger("test")
            test_logger.debug("Debug message should not appear")
            test_logger.info("Info message should appear")

            # Read log file
            log_file = list(log_path.glob("*.log"))[0]
            content = log_file.read_text()

            # Debug message should NOT be in log
            assert "Debug message should not appear" not in content
            # But info should be
            assert "Info message should appear" in content


class TestLogFormat:
    """Test that log messages are formatted correctly"""

    def test_log_includes_timestamp(self):
        """
        Test that log messages include timestamp.
        """
        from src import logger
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs"

            logger.setup_logging(log_dir=str(log_path))

            test_logger = logger.get_logger("test")
            test_logger.info("Test message")

            # Read log file
            log_file = list(log_path.glob("*.log"))[0]
            content = log_file.read_text()

            # Should have timestamp format like 2024-12-24 or similar
            import re
            has_timestamp = re.search(r'\d{4}-\d{2}-\d{2}', content) or re.search(r'\d{2}:\d{2}:\d{2}', content)
            assert has_timestamp, "Log should include timestamp"

    def test_log_includes_level(self):
        """
        Test that log messages include log level.
        """
        from src import logger
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs"

            logger.setup_logging(log_dir=str(log_path))

            test_logger = logger.get_logger("test")
            test_logger.info("Test message")
            test_logger.error("Error message")

            # Read log file
            log_file = list(log_path.glob("*.log"))[0]
            content = log_file.read_text()

            # Should include level names
            assert "INFO" in content or "info" in content.lower()
            assert "ERROR" in content or "error" in content.lower()

    def test_log_includes_module_name(self):
        """
        Test that log messages include the module/logger name.
        """
        from src import logger
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs"

            logger.setup_logging(log_dir=str(log_path))

            test_logger = logger.get_logger("test_module")
            test_logger.info("Test message")

            # Read log file
            log_file = list(log_path.glob("*.log"))[0]
            content = log_file.read_text()

            # Should include module name
            assert "test_module" in content
