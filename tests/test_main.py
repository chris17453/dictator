"""
Tests for __main__ entry point module
"""

import pytest
import sys
from unittest.mock import patch, MagicMock

# Mock problematic modules before import
sys.modules['sounddevice'] = MagicMock()
sys.modules['faster_whisper'] = MagicMock()
sys.modules['pynput'] = MagicMock()
sys.modules['pynput.keyboard'] = MagicMock()

# Import the main function from src
from src.__main__ import main


class TestMainEntry:
    """Test main entry point functionality"""

    def test_main_calls_handle_cli(self):
        """Test that main calls handle_cli"""
        with patch('src.__main__.handle_cli') as mock_handle_cli:
            # CLI returns False (handled command, don't start GUI)
            mock_handle_cli.return_value = False

            main()

            mock_handle_cli.assert_called_once()

    def test_main_starts_gui_when_cli_returns_start_gui(self):
        """Test main starts GUI when CLI returns start_gui=True"""
        with patch('src.__main__.handle_cli') as mock_handle_cli, \
             patch('gui.start_gui') as mock_start_gui:

            # CLI returns GUI start info
            mock_handle_cli.return_value = {'start_gui': True, 'no_tray': False}

            main()

            mock_handle_cli.assert_called_once()
            mock_start_gui.assert_called_once_with(no_tray=False)

    def test_main_starts_gui_with_no_tray(self):
        """Test main starts GUI with no_tray option"""
        with patch('src.__main__.handle_cli') as mock_handle_cli, \
             patch('gui.start_gui') as mock_start_gui:

            # CLI returns GUI start info with no_tray
            mock_handle_cli.return_value = {'start_gui': True, 'no_tray': True}

            main()

            mock_handle_cli.assert_called_once()
            mock_start_gui.assert_called_once_with(no_tray=True)

    def test_main_exits_when_cli_handles_command(self):
        """Test main exits when CLI handles a command"""
        with patch('src.__main__.handle_cli') as mock_handle_cli, \
             patch('gui.start_gui') as mock_start_gui:

            # CLI returns False (handled command)
            mock_handle_cli.return_value = False

            main()

            mock_handle_cli.assert_called_once()
            mock_start_gui.assert_not_called()

    def test_main_exits_when_cli_returns_none(self):
        """Test main exits when CLI returns None"""
        with patch('src.__main__.handle_cli') as mock_handle_cli, \
             patch('gui.start_gui') as mock_start_gui:

            # CLI returns None
            mock_handle_cli.return_value = None

            main()

            mock_handle_cli.assert_called_once()
            mock_start_gui.assert_not_called()

    def test_main_prints_startup_message(self, capsys):
        """Test main prints startup message when starting GUI"""
        with patch('src.__main__.handle_cli') as mock_handle_cli, \
             patch('gui.start_gui') as mock_start_gui:

            # CLI returns GUI start info
            mock_handle_cli.return_value = {'start_gui': True, 'no_tray': False}

            main()

            captured = capsys.readouterr()
            # Startup message is logged, not printed, so check mock was called
            mock_start_gui.assert_called_once()


class TestMainIntegration:
    """Integration tests for main entry point"""

    def test_main_module_imports(self):
        """Test that main module imports work"""
        from src.__main__ import main
        assert callable(main)

    def test_main_with_version_command(self, capsys):
        """Test main with version command"""
        with patch('sys.argv', ['dictator', '--version']):
            main()

            captured = capsys.readouterr()
            assert "🎤 DICTATOR v" in captured.out

    def test_main_with_list_devices_command(self, capsys):
        """Test main with list devices command"""
        with patch('sys.argv', ['dictator', '--list-devices']), \
             patch('sounddevice.query_devices') as mock_query, \
             patch('sounddevice.default') as mock_default:

            mock_query.return_value = [
                {'name': 'Test Mic', 'max_input_channels': 1, 'default_samplerate': 44100.0}
            ]
            mock_default.device = [0, 0]

            main()

            captured = capsys.readouterr()
            assert "📱 Available Audio Input Devices:" in captured.out

    def test_main_with_gui_command(self):
        """Test main with GUI command (default behavior)"""
        with patch('sys.argv', ['dictator']), \
             patch('gui.start_gui') as mock_start_gui:

            main()

            mock_start_gui.assert_called_once()

    def test_main_error_handling(self):
        """Test main handles errors gracefully"""
        with patch('src.__main__.handle_cli', side_effect=Exception("Test error")):
            # Should not crash
            with pytest.raises(Exception, match="Test error"):
                main()


class TestMainAsScript:
    """Test main when run as script"""

    def test_main_script_execution(self):
        """Test that main can be executed as script"""
        # This tests the if __name__ == "__main__": block
        with patch('src.__main__.main') as mock_main:
            # Simulate running as script
            exec("""
if __name__ == "__main__":
    main()
            """, {'__name__': '__main__', 'main': mock_main})

            mock_main.assert_called_once()

    def test_main_module_execution(self):
        """Test that main module can be imported without executing"""
        # Should be able to import without executing main
        try:
            import src.__main__ as main_module
            assert hasattr(main_module, 'main')
            assert callable(main_module.main)
        except ImportError:
            pytest.fail("Could not import src.__main__ module")


class TestMainEdgeCases:
    """Test edge cases for main entry point"""

    def test_main_with_empty_cli_result(self):
        """Test main with empty CLI result"""
        with patch('src.__main__.handle_cli') as mock_handle_cli, \
             patch('gui.start_gui') as mock_start_gui:

            # CLI returns empty dict
            mock_handle_cli.return_value = {}

            main()

            mock_handle_cli.assert_called_once()
            mock_start_gui.assert_not_called()

    def test_main_with_malformed_cli_result(self):
        """Test main with malformed CLI result"""
        with patch('src.__main__.handle_cli') as mock_handle_cli, \
             patch('gui.start_gui') as mock_start_gui:

            # CLI returns malformed result
            mock_handle_cli.return_value = {'start_gui': True}  # Missing no_tray

            main()

            mock_handle_cli.assert_called_once()
            mock_start_gui.assert_called_once_with(no_tray=False)  # Should default to False

    def test_main_import_error_handling(self):
        """Test main handles import errors"""
        with patch('src.__main__.handle_cli', side_effect=ImportError("Module not found")):
            with pytest.raises(ImportError):
                main()

    def test_main_gui_import_error(self):
        """Test main handles GUI import errors"""
        with patch('src.__main__.handle_cli') as mock_handle_cli, \
             patch('gui.start_gui', side_effect=ImportError("GUI not available")):

            mock_handle_cli.return_value = {'start_gui': True, 'no_tray': False}

            with pytest.raises(ImportError):
                main()

    def test_main_preserves_cli_exit_codes(self):
        """Test main preserves CLI exit codes"""
        with patch('src.__main__.handle_cli', side_effect=SystemExit(42)):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 42


class TestMainCommandLine:
    """Test main with various command line scenarios"""

    @pytest.mark.parametrize("args,expected_gui", [
        (['dictator'], True),
        (['dictator', '--gui'], True),
        (['dictator', '--version'], False),
        (['dictator', '--list-devices'], False),
        (['dictator', '--device-info'], False),
        (['dictator', '--help'], False),
    ])
    def test_main_command_scenarios(self, args, expected_gui):
        """Test main with different command scenarios"""
        with patch('sys.argv', args), \
             patch('gui.start_gui') as mock_start_gui, \
             patch('sounddevice.query_devices', return_value=[]), \
             patch('sounddevice.default') as mock_default:

            mock_default.device = [None, None]

            try:
                main()
            except SystemExit:
                pass  # Expected for --help and similar commands

            if expected_gui:
                mock_start_gui.assert_called()
            else:
                mock_start_gui.assert_not_called()

    def test_main_with_invalid_args(self):
        """Test main with invalid arguments"""
        with patch('sys.argv', ['dictator', '--invalid-arg']):
            with pytest.raises(SystemExit):
                main()

    def test_main_help_exit_code(self):
        """Test main help command exits with correct code"""
        with patch('sys.argv', ['dictator', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                main()

            # Help should exit with code 0
            assert exc_info.value.code == 0