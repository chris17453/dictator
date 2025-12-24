#!/usr/bin/env python3
"""
CLI interface for DICTATOR
"""

import sys
import json
import argparse
from pathlib import Path


def list_audio_devices():
    """List available audio input devices"""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        
        print("📱 Available Audio Input Devices:")
        print("=" * 50)
        
        input_devices = []
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                default_marker = " (DEFAULT)" if i == sd.default.device[0] else ""
                input_devices.append({
                    'index': i,
                    'name': device['name'],
                    'channels': device['max_input_channels'],
                    'sample_rate': device['default_samplerate'],
                    'is_default': i == sd.default.device[0]
                })
                print(f"  [{i:2d}] {device['name']}{default_marker}")
                print(f"       Channels: {device['max_input_channels']}, "
                      f"Sample Rate: {device['default_samplerate']:.0f} Hz")
                print()
        
        if not input_devices:
            print("⚠️  No input devices found!")
        
        return input_devices
        
    except ImportError:
        print("❌ sounddevice not installed. Install with: pip install sounddevice")
        return []
    except Exception as e:
        print(f"❌ Error listing devices: {e}")
        return []


def show_device_info():
    """Show current device configuration"""
    try:
        import sounddevice as sd
        
        print("🔧 Current Audio Configuration:")
        print("=" * 40)
        
        # Get default devices
        default_input = sd.default.device[0]
        
        devices = sd.query_devices()
        
        if default_input is not None and default_input < len(devices):
            input_dev = devices[default_input]
            print(f"Input Device:  [{default_input}] {input_dev['name']}")
            print(f"Channels:      {input_dev['max_input_channels']}")
            print(f"Sample Rate:   {input_dev['default_samplerate']:.0f} Hz")
        else:
            print("Input Device:  None selected")
        
        print()
        
        # Check for config file
        config_path = Path.home() / ".config" / "dictator" / "config.json"
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    
                print("📁 DICTATOR Configuration:")
                if 'audio_device_index' in config:
                    print(f"Configured Device: {config['audio_device_index']}")
                if 'whisper_model' in config:
                    print(f"Whisper Model: {config['whisper_model']}")
                if 'hotkey' in config:
                    print(f"Hotkey: {config['hotkey']}")
            except Exception as e:
                print(f"⚠️  Error reading config: {e}")
        else:
            print("📁 No DICTATOR config file found")
            
    except ImportError:
        print("❌ sounddevice not installed")
    except Exception as e:
        print(f"❌ Error getting device info: {e}")


def show_version_info():
    """Show version and system information"""
    try:
        from version import __version__, __author__, __email__, __description__
    except ImportError:
        # Handle relative import when running as module
        from .version import __version__, __author__, __email__, __description__
    
    print(f"🎤 DICTATOR v{__version__}")
    print("=" * 30)
    print(f"Description: {__description__}")
    print(f"Author:      {__author__}")
    print(f"Email:       {__email__}")
    print(f"Repository:  https://github.com/chris17453/dictator")
    print()
    
    # System info
    print("💻 System Information:")
    print(f"Python:      {sys.version.split()[0]} (requires >=3.8)")
    print(f"Platform:    {sys.platform}")
    
    # Check dependencies
    print()
    print("📦 Dependencies:")
    deps_to_check = [
        ('PyQt6', 'PyQt6'),
        ('sounddevice', 'sounddevice'),  
        ('speechrecognition', 'speech_recognition'),
        ('faster-whisper', 'faster_whisper'),
        ('pynput', 'pynput'),
        ('numpy', 'numpy')
    ]
    
    for display_name, import_name in deps_to_check:
        try:
            __import__(import_name)
            print(f"  ✅ {display_name}")
        except ImportError:
            print(f"  ❌ {display_name} (not installed)")


def set_audio_device(device_id):
    """Set the audio input device in configuration"""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        
        if device_id < 0 or device_id >= len(devices):
            print(f"❌ Invalid device ID: {device_id}")
            print("Use --list-devices to see available devices")
            return False
            
        device = devices[device_id]
        if device['max_input_channels'] == 0:
            print(f"❌ Device {device_id} '{device['name']}' has no input channels")
            return False
        
        # Create config directory if it doesn't exist
        config_dir = Path.home() / ".config" / "dictator"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "config.json"
        
        # Load existing config or create new one
        config = {}
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
            except Exception as e:
                print(f"⚠️  Warning: Could not read existing config: {e}")
        
        # Update device setting
        config['audio_device_index'] = device_id
        
        # Save config
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Audio device set to: [{device_id}] {device['name']}")
        print(f"📁 Configuration saved to: {config_path}")
        return True
        
    except ImportError:
        print("❌ sounddevice not installed")
        return False
    except Exception as e:
        print(f"❌ Error setting device: {e}")
        return False


def parse_cli_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        prog='dictator',
        description='DICTATOR - Real-time speech-to-text dictation app',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  dictator                    # Start the GUI application  
  dictator --list-devices     # List available audio input devices
  dictator --device-info      # Show current device configuration
  dictator --version          # Show version information
  dictator --set-device 2     # Set audio input device (use ID from --list-devices)
  dictator --gui              # Explicitly start GUI (default behavior)
        """
    )
    
    parser.add_argument(
        '--version', 
        action='store_true',
        help='Show version information and system status'
    )
    
    parser.add_argument(
        '--list-devices',
        action='store_true', 
        help='List available audio input devices'
    )
    
    parser.add_argument(
        '--device-info',
        action='store_true',
        help='Show current audio device configuration'
    )
    
    parser.add_argument(
        '--set-device',
        type=int,
        metavar='DEVICE_ID',
        help='Set audio input device by ID (use --list-devices to see IDs)'
    )
    
    parser.add_argument(
        '--gui',
        action='store_true',
        help='Start GUI application (default behavior)'
    )
    
    parser.add_argument(
        '--no-tray',
        action='store_true',
        help='Start without system tray integration'
    )
    
    return parser.parse_args()


def handle_cli():
    """Handle CLI commands and return True if GUI should start"""
    args = parse_cli_args()
    
    # Handle non-GUI commands first
    if args.version:
        show_version_info()
        return False
    
    if args.list_devices:
        list_audio_devices()
        return False
    
    if args.device_info:
        show_device_info()
        return False
    
    if args.set_device is not None:
        success = set_audio_device(args.set_device)
        sys.exit(0 if success else 1)
    
    # Return GUI startup info
    return {
        'start_gui': True,
        'no_tray': args.no_tray
    }


if __name__ == "__main__":
    # For testing CLI functions directly
    result = handle_cli()
    if result and result.get('start_gui'):
        print("CLI would start GUI here...")