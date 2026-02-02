"""
Tests for CLI module
"""

import pytest
import sys
import json
import builtins
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import tempfile
import argparse

from cli import (
    list_audio_devices,
    show_device_info,
    show_version_info,
    set_audio_device,
    parse_cli_args,
    handle_cli
)


class TestListAudioDevices:
    """Test audio device listing functionality"""
    
    def test_list_audio_devices_success(self, mock_sounddevice, capsys):
        """Test successful device listing"""
        result = list_audio_devices()
        
        captured = capsys.readouterr()
        assert "📱 Available Audio Input Devices:" in captured.out
        assert "Built-in Microphone" in captured.out
        assert "USB Headset" in captured.out
        assert "(DEFAULT)" in captured.out
        assert len(result) == 2
        
    def test_list_audio_devices_no_sounddevice(self, capsys):
        """Test device listing when sounddevice not available"""
        original_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == 'sounddevice':
                raise ImportError("No module named 'sounddevice'")
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            result = list_audio_devices()

            captured = capsys.readouterr()
            assert "❌ sounddevice not installed" in captured.out
            assert result == []
    
    def test_list_audio_devices_no_input_devices(self, capsys):
        """Test when no input devices available"""
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = [
            {'name': 'Output Only', 'max_input_channels': 0, 'default_samplerate': 44100.0}
        ]
        mock_sd.default.device = [None, 0]
        
        with patch.dict('sys.modules', {'sounddevice': mock_sd}):
            result = list_audio_devices()
            
            captured = capsys.readouterr()
            assert "⚠️  No input devices found!" in captured.out
            assert result == []


class TestShowDeviceInfo:
    """Test device info display"""
    
    def test_show_device_info_success(self, mock_sounddevice, capsys):
        """Test successful device info display"""
        show_device_info()
        
        captured = capsys.readouterr()
        assert "🔧 Current Audio Configuration:" in captured.out
        assert "Built-in Microphone" in captured.out
        assert "Channels:" in captured.out
        assert "Sample Rate:" in captured.out
    
    def test_show_device_info_with_config(self, mock_sounddevice, temp_config_dir, capsys):
        """Test device info with existing config"""
        dictator_dir = temp_config_dir / ".config" / "dictator"
        dictator_dir.mkdir(parents=True, exist_ok=True)
        config_file = dictator_dir / "config.json"

        config_data = {
            'audio_device_index': 1,
            'whisper_model': 'base',
            'hotkey': 'ctrl+space'
        }

        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        with patch('pathlib.Path.home', return_value=temp_config_dir):
            show_device_info()

            captured = capsys.readouterr()
            assert "📁 DICTATOR Configuration:" in captured.out
            assert "Configured Device: 1" in captured.out
            assert "Whisper Model: base" in captured.out
    
    def test_show_device_info_no_sounddevice(self, capsys):
        """Test device info when sounddevice not available"""
        original_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == 'sounddevice':
                raise ImportError("No module named 'sounddevice'")
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            show_device_info()

            captured = capsys.readouterr()
            assert "❌ sounddevice not installed" in captured.out


class TestShowVersionInfo:
    """Test version info display"""
    
    def test_show_version_info(self, capsys):
        """Test version information display"""
        show_version_info()
        
        captured = capsys.readouterr()
        assert "🎤 DICTATOR v" in captured.out
        assert "Description:" in captured.out
        assert "Author:" in captured.out
        assert "Email:" in captured.out
        assert "Repository:" in captured.out
        assert "💻 System Information:" in captured.out
        assert "Python:" in captured.out
        assert "Platform:" in captured.out
        assert "📦 Dependencies:" in captured.out
    
    def test_version_info_checks_dependencies(self, capsys):
        """Test that version info checks for dependencies"""
        original_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            # Make some dependencies available, others not
            if name in ['PyQt6', 'numpy']:
                return MagicMock()
            elif name in ['sounddevice', 'speech_recognition', 'faster_whisper', 'pynput']:
                raise ImportError(f"No module named '{name}'")
            else:
                return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            show_version_info()

            captured = capsys.readouterr()
            assert "✅ PyQt6" in captured.out
            assert "✅ numpy" in captured.out
            assert "❌" in captured.out  # Should have some missing deps


class TestSetAudioDevice:
    """Test audio device setting functionality"""
    
    def test_set_audio_device_success(self, mock_sounddevice, temp_config_dir, capsys):
        """Test successful device setting"""
        with patch('pathlib.Path.home', return_value=temp_config_dir):
            result = set_audio_device(1)

            assert result == True
            captured = capsys.readouterr()
            assert "✅ Audio device set to: [1] USB Headset" in captured.out

            # Check config was saved
            config_file = temp_config_dir / ".config" / "dictator" / "config.json"
            assert config_file.exists()

            with open(config_file) as f:
                config = json.load(f)
                assert config['audio_device_index'] == 1
    
    def test_set_audio_device_invalid_index(self, mock_sounddevice, capsys):
        """Test setting invalid device index"""
        result = set_audio_device(999)
        
        assert result == False
        captured = capsys.readouterr()
        assert "❌ Invalid device ID: 999" in captured.out
        assert "Use --list-devices to see available devices" in captured.out
    
    def test_set_audio_device_no_input_channels(self, capsys):
        """Test setting device with no input channels"""
        with patch('sounddevice.query_devices') as mock_query, \
             patch('sounddevice.default') as mock_default:
            
            mock_query.return_value = [
                {'name': 'Output Only', 'max_input_channels': 0, 'default_samplerate': 44100.0}
            ]
            mock_default.device = [0, 0]
            
            result = set_audio_device(0)
            
            assert result == False
            captured = capsys.readouterr()
            assert "❌ Device 0 'Output Only' has no input channels" in captured.out
    
    def test_set_audio_device_preserves_existing_config(self, mock_sounddevice, temp_config_dir):
        """Test that device setting preserves other config values"""
        config_file = temp_config_dir / ".config" / "dictator" / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # Create existing config
        existing_config = {
            'whisper_model': 'base',
            'hotkey': 'ctrl+alt+space',
            'history': ['test entry']
        }

        with open(config_file, 'w') as f:
            json.dump(existing_config, f)

        with patch('pathlib.Path.home', return_value=temp_config_dir):
            result = set_audio_device(1)

            assert result == True

            # Check config preserved other values
            with open(config_file) as f:
                config = json.load(f)
                assert config['audio_device_index'] == 1
                assert config['whisper_model'] == 'base'
                assert config['hotkey'] == 'ctrl+alt+space'
                assert config['history'] == ['test entry']


class TestParseCliArgs:
    """Test CLI argument parsing"""
    
    def test_parse_no_args(self):
        """Test parsing with no arguments"""
        with patch('sys.argv', ['dictator']):
            args = parse_cli_args()
            
            assert args.version == False
            assert args.list_devices == False
            assert args.device_info == False
            assert args.set_device is None
            assert args.gui == False
            assert args.no_tray == False
    
    def test_parse_version_arg(self):
        """Test parsing version argument"""
        with patch('sys.argv', ['dictator', '--version']):
            args = parse_cli_args()
            assert args.version == True
    
    def test_parse_list_devices_arg(self):
        """Test parsing list devices argument"""
        with patch('sys.argv', ['dictator', '--list-devices']):
            args = parse_cli_args()
            assert args.list_devices == True
    
    def test_parse_device_info_arg(self):
        """Test parsing device info argument"""
        with patch('sys.argv', ['dictator', '--device-info']):
            args = parse_cli_args()
            assert args.device_info == True
    
    def test_parse_set_device_arg(self):
        """Test parsing set device argument"""
        with patch('sys.argv', ['dictator', '--set-device', '2']):
            args = parse_cli_args()
            assert args.set_device == 2
    
    def test_parse_gui_arg(self):
        """Test parsing gui argument"""
        with patch('sys.argv', ['dictator', '--gui']):
            args = parse_cli_args()
            assert args.gui == True
    
    def test_parse_no_tray_arg(self):
        """Test parsing no-tray argument"""
        with patch('sys.argv', ['dictator', '--no-tray']):
            args = parse_cli_args()
            assert args.no_tray == True
    
    def test_parse_multiple_args(self):
        """Test parsing multiple arguments"""
        with patch('sys.argv', ['dictator', '--gui', '--no-tray']):
            args = parse_cli_args()
            assert args.gui == True
            assert args.no_tray == True
    
    def test_parse_help_displays_examples(self):
        """Test that help includes usage examples"""
        with patch('sys.argv', ['dictator', '--help']):
            with pytest.raises(SystemExit):
                parse_cli_args()


class TestHandleCli:
    """Test CLI handling logic"""
    
    def test_handle_cli_version(self, capsys):
        """Test CLI handling for version command"""
        with patch('sys.argv', ['dictator', '--version']):
            result = handle_cli()
            
            assert result == False
            captured = capsys.readouterr()
            assert "🎤 DICTATOR v" in captured.out
    
    def test_handle_cli_list_devices(self, mock_sounddevice, capsys):
        """Test CLI handling for list devices command"""
        with patch('sys.argv', ['dictator', '--list-devices']):
            result = handle_cli()
            
            assert result == False
            captured = capsys.readouterr()
            assert "📱 Available Audio Input Devices:" in captured.out
    
    def test_handle_cli_device_info(self, mock_sounddevice, capsys):
        """Test CLI handling for device info command"""
        with patch('sys.argv', ['dictator', '--device-info']):
            result = handle_cli()
            
            assert result == False
            captured = capsys.readouterr()
            assert "🔧 Current Audio Configuration:" in captured.out
    
    def test_handle_cli_set_device_success(self, mock_sounddevice, temp_config_dir):
        """Test CLI handling for set device command"""
        with patch('sys.argv', ['dictator', '--set-device', '1']), \
             patch('pathlib.Path.home', return_value=temp_config_dir.parent), \
             pytest.raises(SystemExit) as exc_info:
            
            handle_cli()
            
            # Should exit with code 0 (success)
            assert exc_info.value.code == 0
    
    def test_handle_cli_set_device_failure(self, mock_sounddevice):
        """Test CLI handling for set device command failure"""
        with patch('sys.argv', ['dictator', '--set-device', '999']), \
             pytest.raises(SystemExit) as exc_info:
            
            handle_cli()
            
            # Should exit with code 1 (failure)
            assert exc_info.value.code == 1
    
    def test_handle_cli_gui_default(self):
        """Test CLI handling defaults to GUI"""
        with patch('sys.argv', ['dictator']):
            result = handle_cli()
            
            assert result == {'start_gui': True, 'no_tray': False}
    
    def test_handle_cli_gui_with_no_tray(self):
        """Test CLI handling for GUI with no tray"""
        with patch('sys.argv', ['dictator', '--no-tray']):
            result = handle_cli()
            
            assert result == {'start_gui': True, 'no_tray': True}
    
    def test_handle_cli_explicit_gui(self):
        """Test CLI handling for explicit GUI flag"""
        with patch('sys.argv', ['dictator', '--gui']):
            result = handle_cli()
            
            assert result == {'start_gui': True, 'no_tray': False}


class TestCliIntegration:
    """Integration tests for CLI module"""
    
    def test_cli_module_imports(self):
        """Test that all CLI functions can be imported"""
        from cli import (
            list_audio_devices,
            show_device_info, 
            show_version_info,
            set_audio_device,
            parse_cli_args,
            handle_cli
        )
        
        # All functions should be callable
        assert callable(list_audio_devices)
        assert callable(show_device_info)
        assert callable(show_version_info)
        assert callable(set_audio_device)
        assert callable(parse_cli_args)
        assert callable(handle_cli)
    
    def test_cli_error_handling(self, capsys):
        """Test CLI error handling for various edge cases"""
        # Test with corrupted config file
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "dictator" / "config.json"
            config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write invalid JSON
            with open(config_file, 'w') as f:
                f.write("invalid json content")
            
            with patch('pathlib.Path.home', return_value=Path(temp_dir)):
                show_device_info()
                
                # Should handle gracefully without crashing
                captured = capsys.readouterr()
                assert "🔧 Current Audio Configuration:" in captured.out