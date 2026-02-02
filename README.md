# DICTATOR 🎤

<div align="center">
  <img src="desktop/dictator-128.png" alt="DICTATOR Logo" width="128" height="128">
</div>

**Real-time speech-to-text dictation app with floating Qt interface**

[![Version](https://img.shields.io/badge/version-1.0.2-blue.svg)](https://github.com/chris17453/dictator)
[![Python](https://img.shields.io/badge/python-≥3.8-green.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

DICTATOR is a modern, feature-rich speech-to-text dictation application built with PyQt6 and powered by OpenAI's Whisper for accurate transcription. It provides a floating, always-on-top interface for seamless dictation anywhere on your desktop.

## ✨ Features

- **🎙️ Real-time Speech Recognition**: Powered by faster-whisper for high-accuracy transcription
- **🖼️ Floating Interface**: Always-on-top, draggable window that stays accessible
- **⌨️ Global Hotkeys**: System-wide Ctrl+Space hotkey for instant voice recording
- **📋 Smart Output**: Automatically copies to clipboard or types directly into active applications
- **🎨 Customizable UI**: Adjustable transparency, colors, fonts, and themes
- **🔊 Live Audio Monitoring**: Real-time volume level display while recording
- **📝 Session Management**: Organize transcriptions by named sessions
- **📚 History Tracking**: Keep track of all your dictations with clickable history
- **🔧 Device Management**: Easy microphone selection and audio device configuration
- **🖥️ System Tray**: Minimize to tray with quick access controls
- **🎯 GNOME Integration**: Proper desktop integration with icons and notifications

## 🚀 Quick Start

### Installation

```bash
# Install from PyPI (recommended)
pip install the-dictator

# Or install from source
git clone https://github.com/chris17453/dictator.git
cd dictator
pip install -e .
```

### First Run

1. **Launch DICTATOR**:
   ```bash
   dictator
   ```

2. **Setup Audio Permissions** (Linux only):
   ```bash
   # Run the setup script to enable global hotkeys
   dictator --setup-permissions
   # Or manually add yourself to the input group
   sudo usermod -a -G input $USER
   # Then log out and back in
   ```

3. **Configure Audio Device**:
   ```bash
   # List available microphones
   dictator --list-devices
   
   # Set your preferred microphone
   dictator --set-device 2  # Use the ID from --list-devices
   ```

## 📖 Usage

### Basic Usage

1. **Start Recording**: Press `Ctrl+Space` or click the "🎤 Start Listening" button
2. **Speak Clearly**: Watch the real-time audio level indicator
3. **Stop Recording**: Press `Ctrl+Space` again or click "⏹️ Stop Listening"
4. **Get Results**: Text is automatically copied to clipboard and appears in the interface

### Interface Overview

- **🎤 Recording Button**: Manual start/stop recording
- **⏱️ Timer**: Shows recording duration
- **📊 Audio Levels**: Real-time microphone input visualization
- **💬 Current Transcription**: Most recent speech-to-text result
- **📜 History**: Expandable list of all previous transcriptions
- **⚙️ Settings**: Customize appearance, audio, and behavior

### Global Hotkeys

- `Ctrl+Space` - Toggle recording on/off (customizable in settings)

### CLI Commands

```bash
# Show version and system info
dictator --version

# List available audio input devices
dictator --list-devices

# Show current audio configuration
dictator --device-info

# Set audio input device
dictator --set-device <device_id>

# Start without system tray
dictator --no-tray

# Show help
dictator --help
```

## 🔧 Configuration

DICTATOR stores its configuration in `~/.config/dictator/config.json`. Key settings include:

- **Audio Device**: Microphone selection
- **Hotkey**: Customizable key combination
- **UI Appearance**: Colors, fonts, transparency
- **Window Behavior**: Always-on-top, auto-hide settings
- **Session Management**: Current and saved sessions

## 🎨 Customization

Access the settings panel by clicking the ⚙️ gear icon:

### Audio Settings
- Select microphone input device
- Adjust recording sensitivity
- Configure speech timeout settings

### Appearance
- **Window Opacity**: Adjust transparency (50-100%)
- **Color Scheme**: Customize background, text, and accent colors
- **Fonts**: Set different fonts and sizes for transcription and history
- **Always On Top**: Keep window above other applications

### Hotkeys
- Customize the global recording hotkey
- Choose from various key combinations

### Sessions
- Create named sessions for different contexts
- Switch between sessions to organize transcriptions
- Export session history

## 🛠️ Development

### Requirements

- Python ≥3.8
- PyQt6 ≥6.0.0
- faster-whisper ≥0.10.0
- sounddevice ≥0.4.0
- pynput ≥1.6.0
- speechrecognition ≥3.8.0

#### CUDA Support (Optional, for GPU Acceleration)

For GPU-accelerated transcription, you need:

- **NVIDIA GPU** with compute capability ≥7.0
- **NVIDIA Drivers** (≥450.x)
- **CUDA Toolkit** installed on your system

**CUDA 12 vs CUDA 13 Compatibility:**

DICTATOR uses `faster-whisper` which requires CUDA 12 libraries (`libcublas.so.12`, etc.). If you have CUDA 13 installed on your system, the application automatically handles this by using PyTorch's bundled CUDA 12 libraries.

**Automatic Setup (Recommended):**

DICTATOR includes PyTorch as a dependency, which bundles all necessary CUDA 12 libraries. The application automatically detects and configures these libraries at runtime - **no manual setup required**. Your system CUDA installation (whether 12 or 13) remains untouched.

**Manual cuDNN Installation (Optional):**

If you prefer to install CUDA 12 libraries system-wide:

```bash
# For systems with CUDA 13.x
sudo dnf install libcudnn9-cuda-12  # Installs CUDA 12 libs alongside CUDA 13

# For CUDA 12.x systems
sudo dnf install libcudnn9-cuda-12

# For Debian/Ubuntu
sudo apt install libcudnn9-cuda-12
```

**Note:**
- Installing CUDA 12 libraries on a CUDA 13 system is safe - they coexist without conflicts
- If GPU acceleration fails, DICTATOR automatically falls back to CPU mode
- Check logs in `~/.config/dictator/logs/` to verify GPU detection

### Development Setup

```bash
# Clone the repository
git clone https://github.com/chris17453/dictator.git
cd dictator

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e ".[test]"

# Run tests
pytest

# Run with development settings
python -m src.dictator
```

### Project Structure

```
dictator/
├── src/                    # Main source code
│   ├── dictator.py        # Main application window
│   ├── cli.py             # Command line interface
│   ├── gui.py             # GUI startup and management
│   ├── recorder.py        # Audio recording and processing
│   ├── hotkey_manager.py  # Global hotkey handling
│   ├── settings_ui.py     # Settings dialog
│   └── version.py         # Version information
├── desktop/               # Desktop integration files
│   ├── *.png             # Application icons
│   └── dictator.desktop  # Linux desktop entry
├── scripts/               # Utility scripts
└── tests/                 # Test suite
```

## 🐧 Linux Integration

DICTATOR includes proper Linux desktop integration:

- **Desktop Entry**: Appears in application menus and launchers
- **System Tray**: Minimize to system tray with context menu
- **Global Hotkeys**: System-wide keyboard shortcuts (requires input group membership)
- **Icons**: Multi-resolution icons for different display sizes
- **Notifications**: System notifications for recording status

### Permission Setup

For global hotkeys to work on Linux, your user must be in the `input` group:

```bash
# Automated setup
sudo usermod -a -G input $USER

# Then log out and back in, or run:
newgrp input
```

## 🔍 Troubleshooting

### Common Issues

**Global hotkeys not working (Linux)**:
- Ensure you're in the `input` group: `groups | grep input`
- Run the setup script: `bash scripts/setup-permissions.sh`
- Log out and back in after adding to the group

**No audio input detected**:
- Check available devices: `dictator --list-devices`
- Set the correct device: `dictator --set-device <id>`
- Verify microphone permissions in system settings

**Poor transcription quality**:
- Ensure a quiet environment
- Check microphone levels in the audio level indicator
- Speak clearly and at a consistent pace
- Consider using a better quality microphone

**Window not visible**:
- The window might be off-screen after resolution changes
- Delete `~/.config/dictator/config.json` to reset window position
- Or use `dictator --no-tray` to force window visibility

**CUDA/GPU not working**:
- Error: `Library libcublas.so.12 is not found or cannot be loaded`
  - This means faster-whisper is looking for CUDA 12 libraries but can't find them
  - **Solution**: DICTATOR automatically uses PyTorch's bundled CUDA 12 libraries
  - If this fails, ensure PyTorch is properly installed: `uv pip install --pre torch --index-url https://download.pytorch.org/whl/nightly/cu124`
  - The bundled libraries work alongside any system CUDA version (12 or 13)
- Error: `Unable to load any of {libcudnn_ops.so...}`
  - Less common; usually means ctranslate2 needs additional libraries
  - Install system CUDA 12 libraries: `sudo dnf install libcudnn9-cuda-12` (safe to install alongside CUDA 13)
- Error: `no kernel image is available for execution on the device`
  - Your GPU is too new for the current PyTorch version
  - For RTX 50-series GPUs: Use PyTorch nightly (already configured in dependencies)
  - App will automatically fall back to CPU if GPU incompatibility is detected
- Verify CUDA detection:
  - Check logs in `~/.config/dictator/logs/` for "CUDA available" and "Added PyTorch CUDA 12 libraries" messages
  - Look for "Using GPU: [your GPU name]" in startup logs
  - App will automatically fall back to CPU if CUDA fails (no errors, just slower)

### Getting Help

- Check the [GitHub Issues](https://github.com/chris17453/dictator/issues)
- Run `dictator --version` to see system information
- Use `dictator --device-info` for audio configuration details

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👨‍💻 Author

**Chris Watkins**
- Email: chris@watkinslabs.com
- GitHub: [@chris17453](https://github.com/chris17453)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 🙏 Acknowledgments

- [OpenAI Whisper](https://github.com/openai/whisper) for the speech recognition model
- [faster-whisper](https://github.com/guillaumekln/faster-whisper) for optimized Whisper implementation
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) for the GUI framework
- The open-source community for inspiration and tools

---

**Made with ❤️ for productive dictation workflows**