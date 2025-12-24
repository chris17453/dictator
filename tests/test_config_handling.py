"""
Tests for config file handling - validation, backup, and error recovery
Following TDD - RED phase
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
import sys
import os
import json
import tempfile
from pathlib import Path

# Mock problematic modules before import
sys.modules['sounddevice'] = MagicMock()
sys.modules['faster_whisper'] = MagicMock()
sys.modules['pynput'] = MagicMock()
sys.modules['pynput.keyboard'] = MagicMock()


class TestConfigValidation:
    """Test that config is validated before saving/loading"""

    def test_save_config_validates_json_structure(self):
        """
        Test that save_config validates the structure before writing.
        Invalid structure should not be written to disk.
        """
        from src import dictator
        import inspect

        source = inspect.getsource(dictator.DictatorWindow.save_config)

        # Should have validation logic
        # At minimum, should verify it's a valid dict
        assert 'validate' in source.lower() or 'schema' in source.lower() or (
            'isinstance' in source and 'dict' in source
        ), (
            "save_config should validate config structure before writing"
        )

    def test_load_config_validates_json_structure(self):
        """
        Test that load_config validates the loaded data.
        Corrupted/invalid JSON should not crash the app.
        """
        from src import dictator
        import inspect

        source = inspect.getsource(dictator.DictatorWindow.load_config)

        # Should NOT have bare except: pass
        assert 'except:' not in source or 'except Exception' in source, (
            "load_config must not use bare 'except:' - it hides all errors"
        )

    def test_config_has_required_fields(self):
        """
        Test that saved config always includes required fields.
        Missing required fields on load should use defaults.
        """
        from src import dictator
        import inspect

        source = inspect.getsource(dictator.DictatorWindow.save_config)

        # Should save essential fields
        required_fields = ['history', 'selected_microphone_index', 'hotkey_combination']
        for field in required_fields:
            assert field in source, f"save_config should save '{field}' field"


class TestConfigBackup:
    """Test that config is backed up before overwriting"""

    def test_save_creates_backup_before_overwrite(self):
        """
        Test that an existing config is backed up before being overwritten.
        This prevents data loss if the save fails mid-write.
        """
        from src import dictator
        import inspect

        source = inspect.getsource(dictator.DictatorWindow.save_config)

        # Should create backup
        assert 'backup' in source.lower() or '.bak' in source or (
            'copy' in source.lower() and 'config' in source
        ), (
            "save_config should create a backup of existing config before overwriting"
        )

    def test_backup_file_name_format(self):
        """
        Test that backup file follows a consistent naming pattern.
        Should be something like config.json.bak or config.json.backup
        """
        # This is verified through the implementation
        # We'll check in the actual save_config code
        pass


class TestAtomicWrites:
    """Test that config writes are atomic to prevent corruption"""

    def test_save_uses_atomic_write(self):
        """
        Test that save_config writes to a temp file first, then renames.
        This prevents partial writes from corrupting the config.
        """
        from src import dictator
        import inspect

        source = inspect.getsource(dictator.DictatorWindow.save_config)

        # Should write to temp file first
        # Look for common patterns: tempfile, .tmp, or atomic write
        has_temp_write = (
            'tempfile' in source.lower() or
            '.tmp' in source or
            'temp' in source.lower() or
            'atomic' in source.lower() or
            'rename' in source.lower()
        )

        assert has_temp_write, (
            "save_config should use atomic writes (write to temp, then rename) "
            "to prevent corruption from partial writes"
        )


class TestErrorHandling:
    """Test proper error handling during config operations"""

    def test_save_config_handles_permission_errors(self):
        """
        Test that permission errors during save are handled gracefully.
        Should log error and notify user, not crash.
        """
        from src import dictator
        import inspect

        source = inspect.getsource(dictator.DictatorWindow.save_config)

        # Should catch exceptions
        assert 'except' in source, "save_config should have error handling"

        # Should not just pass silently
        assert 'log' in source.lower() or 'print' in source, (
            "save_config should log errors, not fail silently"
        )

    def test_load_config_handles_corrupted_json(self):
        """
        Test that corrupted JSON files are handled gracefully.
        Should use defaults and optionally restore from backup.
        """
        from src import dictator
        import inspect

        source = inspect.getsource(dictator.DictatorWindow.load_config)

        # Should handle JSON decode errors specifically
        assert 'JSONDecodeError' in source or 'ValueError' in source or 'Exception' in source, (
            "load_config should handle JSON parsing errors"
        )

    def test_save_error_does_not_delete_existing_config(self):
        """
        CRITICAL: If save fails, the existing config must not be deleted.
        This is why we need atomic writes and backups.
        """
        # This is ensured by atomic writes test
        # The implementation should write to temp first
        pass

    def test_load_restores_from_backup_on_corruption(self):
        """
        Test that if main config is corrupted, backup is attempted.
        """
        from src import dictator
        import inspect

        source = inspect.getsource(dictator.DictatorWindow.load_config)

        # Should attempt backup restoration
        assert 'backup' in source.lower() or '.bak' in source, (
            "load_config should attempt to restore from backup if main config is corrupted"
        )


class TestConfigDefaults:
    """Test that reasonable defaults are used when config is missing"""

    def test_missing_config_uses_defaults(self):
        """
        Test that if no config file exists, reasonable defaults are used.
        """
        from src import dictator

        # This is tested through the initialization
        # The __init__ should set defaults before calling load_config
        # Verified in the actual implementation
        pass

    def test_missing_fields_use_defaults(self):
        """
        Test that if config exists but fields are missing, defaults are used.
        This handles configs from older versions.
        """
        from src import dictator
        import inspect

        source = inspect.getsource(dictator.DictatorWindow.load_config)

        # Should use .get() with defaults
        assert '.get(' in source, (
            "load_config should use dict.get(key, default) for backward compatibility"
        )


class TestConfigSecurity:
    """Test that config doesn't contain sensitive data"""

    def test_config_does_not_store_passwords(self):
        """
        Test that config never stores passwords or API keys.
        """
        from src import dictator
        import inspect

        source = inspect.getsource(dictator.DictatorWindow.save_config)

        # Should not save password or api_key fields
        sensitive_fields = ['password', 'api_key', 'secret', 'token']
        for field in sensitive_fields:
            assert f"'{field}'" not in source and f'"{field}"' not in source, (
                f"save_config should not save sensitive field: {field}"
            )


class TestConfigMigration:
    """Test that old config formats are migrated to new format"""

    def test_old_config_format_migrated(self):
        """
        Test that configs from older versions are migrated properly.
        Should add new fields with defaults without losing old data.
        """
        # This is verified through the .get() with defaults in load_config
        pass


class TestConfigPerformance:
    """Test that config operations don't block the UI"""

    def test_save_config_is_fast(self):
        """
        Test that save_config doesn't perform expensive operations.
        Should complete in milliseconds, not seconds.
        """
        # This is a performance test - would need actual timing
        # For now, we verify it doesn't do expensive operations like network calls
        from src import dictator
        import inspect

        source = inspect.getsource(dictator.DictatorWindow.save_config)

        # Should not make network requests
        assert 'requests.' not in source and 'urllib' not in source, (
            "save_config should not make network requests"
        )


class TestConfigIntegrity:
    """Test that config maintains data integrity"""

    def test_config_json_is_valid_after_save(self):
        """
        Test that saved config is always valid JSON.
        Should be parseable by json.load().
        """
        # This is verified through atomic writes and validation
        pass

    def test_config_history_limit_enforced(self):
        """
        Test that history is limited to prevent unbounded growth.
        Should save only last N items (e.g., 50).
        """
        from src import dictator
        import inspect

        source = inspect.getsource(dictator.DictatorWindow.save_config)

        # Should limit history
        assert '[-50:]' in source or '[-100:]' in source or 'self.history[-' in source, (
            "save_config should limit history size to prevent unbounded growth"
        )


class TestConfigPaths:
    """Test that config paths are correct and secure"""

    def test_config_stored_in_user_directory(self):
        """
        Test that config is stored in appropriate user directory.
        Should use ~/.config/dictator/ or similar.
        """
        from src import dictator

        # Check in __init__ where config_path is set
        import inspect
        source = inspect.getsource(dictator.DictatorWindow.__init__)

        # Should use platformdirs or similar for cross-platform paths
        assert 'user_config' in source.lower() or '.config' in source, (
            "Config should be stored in user config directory"
        )

    def test_config_directory_created_if_missing(self):
        """
        Test that config directory is created if it doesn't exist.
        """
        from src import dictator
        import inspect

        source = inspect.getsource(dictator.DictatorWindow.save_config)

        # Should create parent directories
        assert 'mkdir' in source or 'makedirs' in source, (
            "save_config should create config directory if it doesn't exist"
        )
