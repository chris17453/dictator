
import sys
import json
import os
from pathlib import Path

try:
    from logger import get_logger
except ImportError:
    from .logger import get_logger
log = get_logger(__name__)
try:
    import importlib.resources as pkg_resources
except ImportError:
    # Fallback for Python < 3.9
    import importlib_resources as pkg_resources
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                            QWidget, QLabel, QPushButton, QScrollArea, QFrame, 
                            QComboBox, QGroupBox, QCheckBox, QProgressBar, QTextEdit,
                            QSystemTrayIcon, QMenu, QDialog, QDialogButtonBox, QSlider,
                            QTabWidget, QSpinBox, QFormLayout, QLineEdit, QFileDialog, QMessageBox, QColorDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint, QDateTime, QSize
from PyQt6.QtGui import QFont, QPalette, QColor, QClipboard, QIcon, QAction
import numpy as np
import threading
import tempfile
import signal
import time
import queue
import subprocess

# Import our separated classes
try:
    from recorder import PureRecorder
    from hotkey_manager import HotkeyManager
    from ui_utils import UIWatchdog, UIUpdateRequest
    from version import __version__
except ImportError:
    # Handle relative imports when running as module
    from .recorder import PureRecorder
    from .hotkey_manager import HotkeyManager
    from .ui_utils import UIWatchdog, UIUpdateRequest
    from .version import __version__


class SettingsDialog(QDialog):
    """Comprehensive settings dialog for DICTATOR"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DICTATOR Settings")
        self.setModal(True)
        self.resize(500, 600)
        self.parent_window = parent
        
        # Set window icon properly for GNOME
        self.set_window_icon()
        
        # Apply dark theme styling
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
                color: white;
            }
            QTabWidget::pane {
                border: 1px solid #4CAF50;
                background-color: #2a2a2a;
            }
            QTabWidget::tab-bar {
                alignment: center;
            }
            QTabBar::tab {
                background-color: #333;
                color: white;
                padding: 8px 16px;
                margin: 2px;
            }
            QTabBar::tab:selected {
                background-color: #4CAF50;
            }
            QGroupBox {
                border: 1px solid #4CAF50;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 15px;
                color: #4CAF50;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #5CBF60;
            }
            QCheckBox {
                color: white;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                background-color: #333;
                border: 1px solid #666;
            }
            QCheckBox::indicator:checked {
                background-color: #4CAF50;
                border: 1px solid #4CAF50;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #333;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #4CAF50;
                width: 16px;
                border-radius: 8px;
                margin: -5px 0;
            }
            QComboBox {
                background-color: #333;
                color: white;
                border: 1px solid #666;
                padding: 4px;
                border-radius: 4px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border: none;
            }
        """)
        
        self.init_ui()

    def show_info_dialog(self, title, message):
        """
        Show information dialog, non-blocking in tests.

        Args:
            title: Dialog title
            message: Information message
        """
        # Use non-blocking dialogs in tests to prevent blocking
        if 'pytest' in sys.modules:
            # Create and show non-blocking dialog
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle(title)
            msg.setText(message)
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.show()  # Non-blocking
        else:
            # Production: use blocking modal dialog
            QMessageBox.information(self, title, message)

    def init_ui(self):
        """Initialize the settings UI"""
        layout = QVBoxLayout()
        
        # Create tabs
        tabs = QTabWidget()
        
        # Audio tab
        audio_tab = QWidget()
        audio_layout = QVBoxLayout(audio_tab)
        
        # Microphone selection
        mic_group = QGroupBox("Audio Input")
        mic_layout = QFormLayout(mic_group)
        
        self.microphone_combo = QComboBox()
        self.microphone_combo.setStyleSheet("""
            QComboBox {
                background-color: #333;
                color: white;
                border: 1px solid #4CAF50;
                border-radius: 4px;
                padding: 5px 8px;
                min-height: 20px;
            }
            QComboBox::drop-down {
                border: none;
                background-color: #4CAF50;
                width: 20px;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                width: 0px;
                height: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #333;
                color: white;
                selection-background-color: #4CAF50;
                border: 1px solid #4CAF50;
            }
        """)
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_microphones)
        
        mic_row = QHBoxLayout()
        mic_row.addWidget(self.microphone_combo)
        mic_row.addWidget(refresh_btn)
        
        mic_layout.addRow("Microphone:", mic_row)
        audio_layout.addWidget(mic_group)

        # Whisper Model Settings
        whisper_group = QGroupBox("Whisper Model Settings")
        whisper_layout = QFormLayout(whisper_group)

        # Model selection dropdown
        self.model_combo = QComboBox()
        self.model_combo.addItems(['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3'])
        self.model_combo.setStyleSheet("""
            QComboBox {
                background-color: #333;
                color: white;
                border: 1px solid #4CAF50;
                border-radius: 4px;
                padding: 5px 8px;
                min-height: 20px;
            }
            QComboBox::drop-down {
                border: none;
                background-color: #4CAF50;
                width: 20px;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                width: 0px;
                height: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #333;
                color: white;
                selection-background-color: #4CAF50;
                border: 1px solid #4CAF50;
            }
        """)
        self.model_combo.setToolTip("Choose Whisper model size (larger = more accurate but slower)")
        whisper_layout.addRow("Model Size:", self.model_combo)

        # Language selection dropdown
        self.language_combo = QComboBox()
        # Add common languages with display names
        languages = [
            ("auto", "Auto-detect"),
            ("en", "English"),
            ("es", "Spanish (Español)"),
            ("fr", "French (Français)"),
            ("de", "German (Deutsch)"),
            ("it", "Italian (Italiano)"),
            ("pt", "Portuguese (Português)"),
            ("ru", "Russian (Русский)"),
            ("zh", "Chinese (中文)"),
            ("ja", "Japanese (日本語)"),
            ("ko", "Korean (한국어)"),
            ("ar", "Arabic (العربية)"),
            ("hi", "Hindi (हिन्दी)"),
            ("nl", "Dutch (Nederlands)"),
            ("pl", "Polish (Polski)"),
            ("tr", "Turkish (Türkçe)"),
            ("sv", "Swedish (Svenska)"),
            ("da", "Danish (Dansk)"),
            ("no", "Norwegian (Norsk)"),
            ("fi", "Finnish (Suomi)")
        ]
        for code, name in languages:
            self.language_combo.addItem(name, code)

        self.language_combo.setStyleSheet("""
            QComboBox {
                background-color: #333;
                color: white;
                border: 1px solid #4CAF50;
                border-radius: 4px;
                padding: 5px 8px;
                min-height: 20px;
            }
            QComboBox::drop-down {
                border: none;
                background-color: #4CAF50;
                width: 20px;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                width: 0px;
                height: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #333;
                color: white;
                selection-background-color: #4CAF50;
                border: 1px solid #4CAF50;
            }
        """)
        self.language_combo.setToolTip("Select transcription language or use auto-detect")
        whisper_layout.addRow("Language:", self.language_combo)

        # Model directory selection
        self.model_dir_input = QLineEdit()
        self.model_dir_input.setPlaceholderText("~/.config/dictator/models")
        self.model_dir_input.setStyleSheet("""
            QLineEdit {
                background-color: #333;
                color: white;
                border: 1px solid #4CAF50;
                border-radius: 4px;
                padding: 5px 8px;
            }
        """)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_model_directory)

        model_dir_row = QHBoxLayout()
        model_dir_row.addWidget(self.model_dir_input)
        model_dir_row.addWidget(browse_btn)

        whisper_layout.addRow("Model Directory:", model_dir_row)

        # Device selection (CPU/GPU)
        self.device_combo = QComboBox()
        self.device_combo.addItems(['auto', 'cpu', 'cuda'])
        self.device_combo.setStyleSheet(self.model_combo.styleSheet())
        self.device_combo.setToolTip("Choose processing device (auto, CPU, or CUDA GPU)")
        whisper_layout.addRow("Compute Device:", self.device_combo)

        # Model download section
        download_container = QWidget()
        download_layout = QVBoxLayout(download_container)
        download_layout.setContentsMargins(0, 10, 0, 0)

        # Download button
        self.download_model_btn = QPushButton("Download Selected Model")
        self.download_model_btn.clicked.connect(self.download_whisper_model)
        self.download_model_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #666;
                color: #999;
            }
        """)
        self.download_model_btn.setToolTip("Download the selected Whisper model for offline use")
        download_layout.addWidget(self.download_model_btn)

        # Status label
        self.download_status = QLabel("")
        self.download_status.setStyleSheet("color: #ccc; font-size: 12px; padding: 5px;")
        download_layout.addWidget(self.download_status)

        # Progress bar
        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.setTextVisible(True)
        self.download_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #4CAF50;
                border-radius: 4px;
                text-align: center;
                background-color: #333;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
            }
        """)
        self.download_progress.hide()  # Initially hidden
        download_layout.addWidget(self.download_progress)

        whisper_layout.addRow("", download_container)

        audio_layout.addWidget(whisper_group)

        tabs.addTab(audio_tab, "Audio")
        
        # Appearance tab
        appearance_tab = QWidget()
        appearance_layout = QVBoxLayout(appearance_tab)
        
        # Window settings
        window_group = QGroupBox("Window Behavior")
        window_layout = QVBoxLayout(window_group)
        
        self.always_on_top_checkbox = QCheckBox("Always keep window on top")
        self.always_on_top_checkbox.setChecked(getattr(self.parent_window, 'always_on_top', True))
        window_layout.addWidget(self.always_on_top_checkbox)
        
        self.auto_hide_checkbox = QCheckBox("Auto-hide after dictation")
        self.auto_hide_checkbox.setChecked(True)
        window_layout.addWidget(self.auto_hide_checkbox)
        
        appearance_layout.addWidget(window_group)
        
        # Opacity settings (using alpha channel transparency)
        opacity_group = QGroupBox("Window Transparency") 
        opacity_layout = QVBoxLayout(opacity_group)
        
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(50, 100)  # Don't go too transparent
        self.opacity_slider.setValue(95)
        self.opacity_slider.valueChanged.connect(self.update_opacity_alpha)
        
        self.opacity_label = QLabel("Opacity: 95%")
        opacity_layout.addWidget(self.opacity_label)
        opacity_layout.addWidget(self.opacity_slider)
        
        appearance_layout.addWidget(opacity_group)
        
        # Color customization
        color_group = QGroupBox("Color Theme")
        color_layout = QVBoxLayout(color_group)
        
        # Background color
        bg_color_layout = QHBoxLayout()
        bg_color_label = QLabel("Background Color:")
        self.bg_color_btn = QPushButton("🎨 Choose Color")
        self.bg_color_btn.setStyleSheet("QPushButton { background-color: #141414; color: white; }")
        self.bg_color_btn.clicked.connect(self.choose_background_color)
        bg_color_layout.addWidget(bg_color_label)
        bg_color_layout.addWidget(self.bg_color_btn)
        color_layout.addLayout(bg_color_layout)
        
        # Border/trim color  
        border_color_layout = QHBoxLayout()
        border_color_label = QLabel("Border Color:")
        self.border_color_btn = QPushButton("🎨 Choose Color")
        self.border_color_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; }")
        self.border_color_btn.clicked.connect(self.choose_border_color)
        border_color_layout.addWidget(border_color_label)
        border_color_layout.addWidget(self.border_color_btn)
        color_layout.addLayout(border_color_layout)
        
        # Text color
        text_color_layout = QHBoxLayout()
        text_color_label = QLabel("Text Color:")
        self.text_color_btn = QPushButton("🎨 Choose Color")
        self.text_color_btn.setStyleSheet("QPushButton { background-color: #ffffff; color: black; }")
        self.text_color_btn.clicked.connect(self.choose_text_color)
        text_color_layout.addWidget(text_color_label)
        text_color_layout.addWidget(self.text_color_btn)
        color_layout.addLayout(text_color_layout)
        
        # Button color
        button_color_layout = QHBoxLayout()
        button_color_label = QLabel("Button Color:")
        self.button_color_btn = QPushButton("🎨 Choose Color")
        self.button_color_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; }")
        self.button_color_btn.clicked.connect(self.choose_button_color)
        button_color_layout.addWidget(button_color_label)
        button_color_layout.addWidget(self.button_color_btn)
        color_layout.addLayout(button_color_layout)
        
        # Current Translation Colors
        trans_bg_color_layout = QHBoxLayout()
        trans_bg_color_label = QLabel("Translation Background:")
        self.trans_bg_color_btn = QPushButton("🎨 Choose Color")
        self.trans_bg_color_btn.setStyleSheet("QPushButton { background-color: #1a1a1a; color: white; }")
        self.trans_bg_color_btn.clicked.connect(self.choose_translation_bg_color)
        trans_bg_color_layout.addWidget(trans_bg_color_label)
        trans_bg_color_layout.addWidget(self.trans_bg_color_btn)
        color_layout.addLayout(trans_bg_color_layout)
        
        # Current Translation Text Color
        trans_text_color_layout = QHBoxLayout()
        trans_text_color_label = QLabel("Translation Text:")
        self.trans_text_color_btn = QPushButton("🎨 Choose Color")
        self.trans_text_color_btn.setStyleSheet("QPushButton { background-color: #ffffff; color: black; }")
        self.trans_text_color_btn.clicked.connect(self.choose_translation_text_color)
        trans_text_color_layout.addWidget(trans_text_color_label)
        trans_text_color_layout.addWidget(self.trans_text_color_btn)
        color_layout.addLayout(trans_text_color_layout)
        
        # History Colors
        history_bg_color_layout = QHBoxLayout()
        history_bg_color_label = QLabel("History Background:")
        self.history_bg_color_btn = QPushButton("🎨 Choose Color")
        self.history_bg_color_btn.setStyleSheet("QPushButton { background-color: #0f0f0f; color: white; }")
        self.history_bg_color_btn.clicked.connect(self.choose_history_bg_color)
        history_bg_color_layout.addWidget(history_bg_color_label)
        history_bg_color_layout.addWidget(self.history_bg_color_btn)
        color_layout.addLayout(history_bg_color_layout)
        
        # History Text Color
        history_text_color_layout = QHBoxLayout()
        history_text_color_label = QLabel("History Text:")
        self.history_text_color_btn = QPushButton("🎨 Choose Color")
        self.history_text_color_btn.setStyleSheet("QPushButton { background-color: #cccccc; color: black; }")
        self.history_text_color_btn.clicked.connect(self.choose_history_text_color)
        history_text_color_layout.addWidget(history_text_color_label)
        history_text_color_layout.addWidget(self.history_text_color_btn)
        color_layout.addLayout(history_text_color_layout)
        
        # Reset to defaults
        reset_colors_btn = QPushButton("🔄 Reset to Default Colors")
        reset_colors_btn.clicked.connect(self.reset_colors)
        color_layout.addWidget(reset_colors_btn)
        
        appearance_layout.addWidget(color_group)
        
        # Font customization
        font_group = QGroupBox("Font Settings")
        font_layout = QVBoxLayout(font_group)
        
        # Translation font settings
        trans_font_layout = QHBoxLayout()
        trans_font_label = QLabel("Translation Font:")
        self.translation_font_btn = QPushButton("🔤 Choose Font")
        self.translation_font_size_spin = QSpinBox()
        self.translation_font_size_spin.setRange(8, 72)
        self.translation_font_size_spin.setValue(14)
        self.translation_font_size_spin.setSuffix("px")
        self.translation_font_btn.clicked.connect(self.choose_translation_font)
        self.translation_font_size_spin.valueChanged.connect(self.update_translation_font_size)
        trans_font_layout.addWidget(trans_font_label)
        trans_font_layout.addWidget(self.translation_font_btn)
        trans_font_layout.addWidget(self.translation_font_size_spin)
        font_layout.addLayout(trans_font_layout)
        
        # History font settings
        hist_font_layout = QHBoxLayout()
        hist_font_label = QLabel("History Font:")
        self.history_font_btn = QPushButton("🔤 Choose Font")
        self.history_font_size_spin = QSpinBox()
        self.history_font_size_spin.setRange(8, 72)
        self.history_font_size_spin.setValue(12)
        self.history_font_size_spin.setSuffix("px")
        self.history_font_btn.clicked.connect(self.choose_history_font)
        self.history_font_size_spin.valueChanged.connect(self.update_history_font_size)
        hist_font_layout.addWidget(hist_font_label)
        hist_font_layout.addWidget(self.history_font_btn)
        hist_font_layout.addWidget(self.history_font_size_spin)
        font_layout.addLayout(hist_font_layout)
        
        # Reset to defaults
        reset_fonts_btn = QPushButton("🔄 Reset to Default Fonts")
        reset_fonts_btn.clicked.connect(self.reset_fonts)
        font_layout.addWidget(reset_fonts_btn)
        
        appearance_layout.addWidget(font_group)
        tabs.addTab(appearance_tab, "Appearance")
        
        # Hotkeys tab
        hotkeys_tab = QWidget()
        hotkeys_layout = QVBoxLayout(hotkeys_tab)
        
        hotkey_group = QGroupBox("Keyboard Shortcuts")
        hotkey_layout = QFormLayout(hotkey_group)
        
        self.hotkey_label = QLabel("Ctrl+Space")
        change_hotkey_btn = QPushButton("Change Hotkey")
        change_hotkey_btn.clicked.connect(self.change_hotkey)
        
        hotkey_row = QHBoxLayout()
        hotkey_row.addWidget(self.hotkey_label)
        hotkey_row.addWidget(change_hotkey_btn)
        
        hotkey_layout.addRow("Record Toggle:", hotkey_row)

        # Recording mode selector
        self.recording_mode_combo = QComboBox()
        self.recording_mode_combo.addItem("Toggle Mode", "toggle")
        self.recording_mode_combo.addItem("Push-to-Talk Mode", "push-to-talk")
        self.recording_mode_combo.setToolTip("Toggle: Press key to start/stop. Push-to-talk: Hold key to record, release to stop")
        hotkey_layout.addRow("Recording Mode:", self.recording_mode_combo)

        # Recording timeout selector
        self.timeout_combo = QComboBox()
        self.timeout_combo.addItem("30 seconds", 30)
        self.timeout_combo.addItem("1 minute", 60)
        self.timeout_combo.addItem("2 minutes", 120)
        self.timeout_combo.addItem("5 minutes", 300)
        self.timeout_combo.addItem("10 minutes", 600)
        self.timeout_combo.addItem("15 minutes", 900)
        self.timeout_combo.addItem("30 minutes", 1800)
        self.timeout_combo.setToolTip("Maximum recording duration before automatic stop")
        hotkey_layout.addRow("Max Recording Time:", self.timeout_combo)

        # Silence detection (VAD) checkbox
        self.silence_detection_checkbox = QCheckBox("Enable silence detection")
        self.silence_detection_checkbox.setToolTip("Automatically stop recording after detecting silence")
        hotkey_layout.addRow("Auto-stop on silence:", self.silence_detection_checkbox)

        # Silence threshold slider
        self.silence_threshold_spin = QSpinBox()
        self.silence_threshold_spin.setRange(1, 20)
        self.silence_threshold_spin.setSuffix("%")
        self.silence_threshold_spin.setToolTip("Audio level below which is considered silence (1-20%)")
        hotkey_layout.addRow("Silence threshold:", self.silence_threshold_spin)

        # Silence duration combo
        self.silence_duration_combo = QComboBox()
        self.silence_duration_combo.addItem("1 second", 1.0)
        self.silence_duration_combo.addItem("1.5 seconds", 1.5)
        self.silence_duration_combo.addItem("2 seconds", 2.0)
        self.silence_duration_combo.addItem("2.5 seconds", 2.5)
        self.silence_duration_combo.addItem("3 seconds", 3.0)
        self.silence_duration_combo.addItem("4 seconds", 4.0)
        self.silence_duration_combo.addItem("5 seconds", 5.0)
        self.silence_duration_combo.setToolTip("How long to wait before stopping after silence is detected")
        hotkey_layout.addRow("Silence duration:", self.silence_duration_combo)

        hotkeys_layout.addWidget(hotkey_group)

        tabs.addTab(hotkeys_tab, "Hotkeys")
        
        # History management tab
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        
        # Session management
        session_group = QGroupBox("Session Management")
        session_layout = QVBoxLayout(session_group)
        
        current_session_layout = QHBoxLayout()
        self.current_session_label = QLabel("Current Session: Default")
        current_session_layout.addWidget(self.current_session_label)
        current_session_layout.addStretch()
        session_layout.addLayout(current_session_layout)
        
        new_session_layout = QHBoxLayout()
        self.session_name_input = QLineEdit()
        self.session_name_input.setPlaceholderText("Enter new session name...")
        new_session_btn = QPushButton("Start New Session")
        new_session_btn.clicked.connect(self.start_new_session)
        new_session_layout.addWidget(self.session_name_input)
        new_session_layout.addWidget(new_session_btn)
        session_layout.addLayout(new_session_layout)
        
        history_layout.addWidget(session_group)
        
        # History actions
        actions_group = QGroupBox("History Actions")
        actions_layout = QVBoxLayout(actions_group)
        
        stats_label = QLabel("Current session: 0 entries | Total history: 0 entries")
        self.history_stats_label = stats_label
        actions_layout.addWidget(stats_label)
        
        button_layout = QHBoxLayout()
        
        export_btn = QPushButton("📤 Export History")
        export_btn.clicked.connect(self.export_history)
        export_btn.setStyleSheet("QPushButton { background-color: #2196F3; }")
        
        clear_session_btn = QPushButton("🗑️ Clear Current Session")
        clear_session_btn.clicked.connect(self.clear_current_session)
        clear_session_btn.setStyleSheet("QPushButton { background-color: #FF9800; }")
        
        clear_all_btn = QPushButton("Clear All History")
        clear_all_btn.clicked.connect(self.clear_all_history)
        clear_all_btn.setStyleSheet("QPushButton { background-color: #f44336; }")
        
        button_layout.addWidget(export_btn)
        button_layout.addWidget(clear_session_btn)
        button_layout.addWidget(clear_all_btn)
        
        actions_layout.addLayout(button_layout)
        history_layout.addWidget(actions_group)
        
        tabs.addTab(history_tab, "History")

        # Advanced tab
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)

        # Logging settings
        logging_group = QGroupBox("Logging Settings")
        logging_layout = QVBoxLayout(logging_group)

        # Debug mode checkbox
        self.debug_mode_checkbox = QCheckBox("Enable debug logging")
        self.debug_mode_checkbox.setToolTip(
            "Enable detailed debug logging for troubleshooting.\n"
            "Debug logs include verbose information about app operations."
        )
        self.debug_mode_checkbox.stateChanged.connect(self.toggle_debug_mode)
        logging_layout.addWidget(self.debug_mode_checkbox)

        # Debug info label
        debug_info = QLabel(
            "Debug mode provides detailed logging information useful for troubleshooting.\n"
            "Normal operation uses INFO level logging."
        )
        debug_info.setStyleSheet("color: #999; font-size: 11px; padding: 5px;")
        debug_info.setWordWrap(True)
        logging_layout.addWidget(debug_info)

        advanced_layout.addWidget(logging_group)
        advanced_layout.addStretch()

        tabs.addTab(advanced_tab, "Advanced")

        layout.addWidget(tabs)
        
        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal
        )
        buttons.accepted.connect(self.accept_settings)
        buttons.rejected.connect(self.reject)
        
        layout.addWidget(buttons)
        
        self.setLayout(layout)
        
        # Load current settings
        self.load_current_settings()
        
        # Initial microphone refresh
        QTimer.singleShot(100, self.refresh_microphones)
    
    def set_window_icon(self):
        """Set window icon with multiple sizes for better GNOME integration"""
        icon = QIcon()
        
        # Find icon directory
        icon_dir = Path(__file__).parent / "icons"
        
        # Add multiple sizes to the icon for better rendering
        icon_sizes = [16, 32, 48, 64, 128, 256]
        for size in icon_sizes:
            icon_file = icon_dir / f"dictator-{size}.png"
            if icon_file.exists():
                icon.addFile(str(icon_file), QSize(size, size))
        
        # Fallback to generic icon if sized ones don't exist
        fallback_icon = icon_dir / "dictator.png"
        if fallback_icon.exists() and icon.isNull():
            icon.addFile(str(fallback_icon))
        
        # Set the window icon
        if not icon.isNull():
            self.setWindowIcon(icon)
            # Also set on application level for GNOME integration
            if QApplication.instance():
                QApplication.instance().setWindowIcon(icon)
    
    def load_current_settings(self):
        """Load current settings from parent window"""
        if not self.parent_window:
            return
            
        # Load always on top
        if hasattr(self.parent_window, 'always_on_top'):
            self.always_on_top_checkbox.setChecked(self.parent_window.always_on_top)
        
        # Load auto-hide
        if hasattr(self.parent_window, 'auto_hide_checkbox'):
            self.auto_hide_checkbox.setChecked(self.parent_window.auto_hide_checkbox.isChecked())
        
        # Load current hotkey
        if hasattr(self.parent_window, 'hotkey_manager'):
            current_hotkey_string = self.parent_window.hotkey_manager.get_hotkey_string()
            self.hotkey_label.setText(current_hotkey_string)

        # Load recording mode
        if hasattr(self.parent_window, 'recording_mode'):
            mode = self.parent_window.recording_mode
            for i in range(self.recording_mode_combo.count()):
                if self.recording_mode_combo.itemData(i) == mode:
                    self.recording_mode_combo.setCurrentIndex(i)
                    break

        # Load recording timeout
        if hasattr(self.parent_window, 'recording_timeout'):
            timeout = self.parent_window.recording_timeout
            for i in range(self.timeout_combo.count()):
                if self.timeout_combo.itemData(i) == timeout:
                    self.timeout_combo.setCurrentIndex(i)
                    break

        # Load silence detection settings
        if hasattr(self.parent_window, 'silence_detection_enabled'):
            self.silence_detection_checkbox.setChecked(self.parent_window.silence_detection_enabled)

        if hasattr(self.parent_window, 'silence_threshold'):
            self.silence_threshold_spin.setValue(self.parent_window.silence_threshold)

        if hasattr(self.parent_window, 'silence_duration'):
            duration = self.parent_window.silence_duration
            for i in range(self.silence_duration_combo.count()):
                if self.silence_duration_combo.itemData(i) == duration:
                    self.silence_duration_combo.setCurrentIndex(i)
                    break

        # Load debug mode setting
        if hasattr(self.parent_window, 'debug_mode_enabled'):
            self.debug_mode_checkbox.setChecked(self.parent_window.debug_mode_enabled)

        # Load current opacity (if slider exists)
        if hasattr(self, 'opacity_slider') and hasattr(self.parent_window, 'current_opacity_percent'):
            current_opacity = self.parent_window.current_opacity_percent
            self.opacity_slider.setValue(current_opacity)
            self.opacity_label.setText(f"Opacity: {current_opacity}%")
            log.info(f"SETTINGS: Loaded opacity slider value: {current_opacity}%")
        
        # Load current microphone selection
        if hasattr(self.parent_window, 'recorder') and hasattr(self.parent_window.recorder, 'current_microphone_index'):
            current_mic_index = self.parent_window.recorder.current_microphone_index
            if current_mic_index is not None and hasattr(self, 'microphone_combo'):
                # Find the combo box index that matches the recorder's microphone index
                for i in range(self.microphone_combo.count()):
                    item_data = self.microphone_combo.itemData(i)
                    if item_data == current_mic_index:
                        self.microphone_combo.setCurrentIndex(i)
                        log.debug(f"SETTINGS: Set microphone combo to index {i} for device {current_mic_index}")
                        break
        
        # Load current colors into buttons
        if hasattr(self.parent_window, 'custom_bg_color'):
            bg_color = QColor(self.parent_window.custom_bg_color)
            self.bg_color_btn.setStyleSheet(f"QPushButton {{ background-color: {self.parent_window.custom_bg_color}; color: {'white' if bg_color.lightness() < 64 else 'black'}; }}")
        
        if hasattr(self.parent_window, 'custom_border_color'):
            border_color = QColor(self.parent_window.custom_border_color)
            self.border_color_btn.setStyleSheet(f"QPushButton {{ background-color: {self.parent_window.custom_border_color}; color: {'white' if border_color.lightness() < 64 else 'black'}; }}")
        
        if hasattr(self.parent_window, 'custom_text_color'):
            text_color = QColor(self.parent_window.custom_text_color)
            self.text_color_btn.setStyleSheet(f"QPushButton {{ background-color: {self.parent_window.custom_text_color}; color: {'black' if text_color.lightness() > 64 else 'white'}; }}")
        
        if hasattr(self.parent_window, 'custom_button_color'):
            button_color = QColor(self.parent_window.custom_button_color)
            self.button_color_btn.setStyleSheet(f"QPushButton {{ background-color: {self.parent_window.custom_button_color}; color: {'white' if button_color.lightness() < 64 else 'black'}; }}")
        
        # Load translation colors
        if hasattr(self.parent_window, 'custom_translation_bg_color'):
            trans_bg_color = QColor(self.parent_window.custom_translation_bg_color)
            self.trans_bg_color_btn.setStyleSheet(f"QPushButton {{ background-color: {self.parent_window.custom_translation_bg_color}; color: {'white' if trans_bg_color.lightness() < 64 else 'black'}; }}")
        
        if hasattr(self.parent_window, 'custom_translation_text_color'):
            trans_text_color = QColor(self.parent_window.custom_translation_text_color)
            self.trans_text_color_btn.setStyleSheet(f"QPushButton {{ background-color: {self.parent_window.custom_translation_text_color}; color: {'black' if trans_text_color.lightness() > 64 else 'white'}; }}")
        
        # Load history colors
        if hasattr(self.parent_window, 'custom_history_bg_color'):
            hist_bg_color = QColor(self.parent_window.custom_history_bg_color)
            self.history_bg_color_btn.setStyleSheet(f"QPushButton {{ background-color: {self.parent_window.custom_history_bg_color}; color: {'white' if hist_bg_color.lightness() < 64 else 'black'}; }}")
        
        if hasattr(self.parent_window, 'custom_history_text_color'):
            hist_text_color = QColor(self.parent_window.custom_history_text_color)
            self.history_text_color_btn.setStyleSheet(f"QPushButton {{ background-color: {self.parent_window.custom_history_text_color}; color: {'black' if hist_text_color.lightness() > 64 else 'white'}; }}")
        
        # Load current fonts into buttons and spinboxes
        if hasattr(self.parent_window, 'custom_translation_font_family'):
            self.translation_font_btn.setText(f"🔤 {self.parent_window.custom_translation_font_family}")
            self.translation_font_size_spin.setValue(getattr(self.parent_window, 'custom_translation_font_size', 14))
        
        if hasattr(self.parent_window, 'custom_history_font_family'):
            self.history_font_btn.setText(f"🔤 {self.parent_window.custom_history_font_family}")
            self.history_font_size_spin.setValue(getattr(self.parent_window, 'custom_history_font_size', 12))

        # Load Whisper model settings
        self.load_whisper_settings()

        # Update history stats
        self.update_history_stats()
    
    def refresh_microphones(self):
        """Refresh the microphone list"""
        self.microphone_combo.clear()
        
        if self.parent_window and hasattr(self.parent_window, 'recorder'):
            devices = self.parent_window.recorder.available_microphones
            
            for i, device in enumerate(devices):
                device_name = device['name']
                device_index = device['index']
                
                # Add item with device index as data
                self.microphone_combo.addItem(f"[{device_index}] {device_name}", device_index)
                log.debug(f"REFRESH_MIC: Added device {device_index}: {device_name}")
                
                # Select current microphone
                if hasattr(self.parent_window.recorder, 'current_microphone_index'):
                    if device_index == self.parent_window.recorder.current_microphone_index:
                        self.microphone_combo.setCurrentIndex(i)
                        log.debug(f"REFRESH_MIC: Selected current device at combo index {i}")

    def browse_model_directory(self):
        """Browse for model directory"""
        from PyQt6.QtWidgets import QFileDialog

        current_dir = self.model_dir_input.text() or str(Path.home() / ".config" / "dictator" / "models")
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Whisper Model Directory",
            current_dir
        )

        if directory:
            self.model_dir_input.setText(directory)

    def download_whisper_model(self):
        """Download the selected Whisper model"""
        from pathlib import Path

        # Import thread pool from dictator module
        try:
            from dictator import thread_pool
        except ImportError:
            from .dictator import thread_pool

        # Get selected model and directory
        model_size = self.model_combo.currentText()
        model_dir = self.model_dir_input.text() or str(Path.home() / ".config" / "dictator" / "models")
        device = self.device_combo.currentText()

        # Create model directory if it doesn't exist
        try:
            Path(model_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            log.error(f"Failed to create model directory: {e}")
            if self.parent_window and hasattr(self.parent_window, 'show_error_dialog'):
                self.parent_window.show_error_dialog(
                    "Download Error",
                    f"Could not create model directory.\n\n"
                    f"Error: {e}\n\n"
                    f"Please check permissions on: {model_dir}"
                )
            return

        log.info(f"Starting download of Whisper {model_size} model to {model_dir}")

        # Update UI for download start
        self.download_model_btn.setEnabled(False)
        self.download_status.setText(f"Downloading {model_size} model...")
        self.download_progress.setValue(0)
        self.download_progress.show()

        # Download in thread pool to avoid freezing UI
        def download_task():
            try:
                # Import here to avoid issues if faster_whisper not installed
                from faster_whisper import WhisperModel

                # Determine device
                if device == "auto":
                    try:
                        import torch
                        actual_device = "cuda" if torch.cuda.is_available() else "cpu"
                    except ImportError:
                        actual_device = "cpu"
                else:
                    actual_device = device

                log.info(f"Downloading model with device={actual_device}, download_root={model_dir}")

                # Create WhisperModel - this triggers download if not present
                # Note: We can't easily track progress with faster_whisper, so just show indeterminate
                self.download_progress.setRange(0, 0)  # Indeterminate progress

                model = WhisperModel(
                    model_size,
                    device=actual_device,
                    download_root=model_dir
                )

                # If we got here, download succeeded
                log.info(f"Successfully downloaded {model_size} model")

                # Update UI on main thread using QTimer
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._on_download_complete(model_size))

            except Exception as e:
                log.error(f"Failed to download model: {e}")

                # Show error dialog on main thread using QTimer
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._on_download_error(str(e)))

        # Submit to thread pool
        thread_pool.submit(download_task)

    def _on_download_complete(self, model_size):
        """Called when download completes successfully"""
        log.info(f"Download of {model_size} model complete")

        # Update UI
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(100)
        self.download_status.setText(f"✓ {model_size} model downloaded successfully!")
        self.download_status.setStyleSheet("color: #4CAF50; font-size: 12px; padding: 5px;")

        # Re-enable button after 2 seconds
        QTimer.singleShot(2000, self._reset_download_ui)

        # Show success message
        if self.parent_window and hasattr(self.parent_window, 'show_error_dialog'):
            # Use QMessageBox directly for success
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Information)
            msg_box.setWindowTitle("Download Complete")
            msg_box.setText(f"Whisper {model_size} model downloaded successfully!")
            msg_box.setInformativeText("The model is now ready to use.")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            # Use non-blocking show() in tests to prevent blocking
            if 'pytest' in sys.modules:
                msg_box.show()  # Non-blocking for tests
            else:
                msg_box.exec()  # Blocking modal dialog for production

    def _on_download_error(self, error_msg):
        """Called when download fails"""
        log.error(f"Download error: {error_msg}")

        # Update UI
        self.download_progress.hide()
        self.download_status.setText(f"✗ Download failed")
        self.download_status.setStyleSheet("color: #f44336; font-size: 12px; padding: 5px;")
        self.download_model_btn.setEnabled(True)

        # Show error dialog
        if self.parent_window and hasattr(self.parent_window, 'show_error_dialog'):
            self.parent_window.show_error_dialog(
                "Model Download Failed",
                f"Could not download Whisper model.\n\n"
                f"Error: {error_msg}\n\n"
                f"Please check:\n"
                f"• Internet connection is active\n"
                f"• Disk space is sufficient\n"
                f"• Directory permissions are correct"
            )

    def _reset_download_ui(self):
        """Reset download UI to initial state"""
        self.download_progress.hide()
        self.download_status.setText("")
        self.download_status.setStyleSheet("color: #ccc; font-size: 12px; padding: 5px;")
        self.download_model_btn.setEnabled(True)

    def load_whisper_settings(self):
        """Load Whisper model settings from parent window config"""
        if not self.parent_window:
            return

        # Load model size
        model_size = getattr(self.parent_window, 'whisper_model_size', 'tiny')
        index = self.model_combo.findText(model_size)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)

        # Load model directory
        model_dir = getattr(self.parent_window, 'whisper_model_dir',
                           str(Path.home() / ".config" / "dictator" / "models"))
        self.model_dir_input.setText(model_dir)

        # Load device
        device = getattr(self.parent_window, 'whisper_device', 'auto')
        index = self.device_combo.findText(device)
        if index >= 0:
            self.device_combo.setCurrentIndex(index)

        # Load language
        language = getattr(self.parent_window, 'whisper_language', 'auto')
        # Find by data (language code), not text (display name)
        for i in range(self.language_combo.count()):
            if self.language_combo.itemData(i) == language:
                self.language_combo.setCurrentIndex(i)
                break

    def save_whisper_settings(self):
        """Save Whisper model settings to parent window"""
        if not self.parent_window:
            return

        self.parent_window.whisper_model_size = self.model_combo.currentText()
        self.parent_window.whisper_model_dir = self.model_dir_input.text()
        self.parent_window.whisper_device = self.device_combo.currentText()
        self.parent_window.whisper_language = self.language_combo.currentData()  # Use data (code), not text (display name)

        # Trigger model reload if recorder exists
        if hasattr(self.parent_window, 'recorder'):
            self.parent_window.recorder.whisper_model_size = self.parent_window.whisper_model_size
            self.parent_window.recorder.whisper_model_dir = self.parent_window.whisper_model_dir
            self.parent_window.recorder.whisper_device = self.parent_window.whisper_device
            self.parent_window.recorder.whisper_language = self.parent_window.whisper_language
            log.info(f"Updated Whisper settings: model={self.parent_window.whisper_model_size}, dir={self.parent_window.whisper_model_dir}, device={self.parent_window.whisper_device}, language={self.parent_window.whisper_language}")

            # Reload the model with new settings
            log.info("Reloading Whisper model with new settings...")
            self.parent_window.recorder.load_whisper_model()
            log.info("Whisper model reloaded successfully")

    def update_opacity_alpha(self, value):
        """Update opacity using alpha channel (actually works!)"""
        self.opacity_label.setText(f"Opacity: {value}%")
        # Apply opacity by updating the main widget's background alpha
        if self.parent_window:
            self.parent_window.update_window_alpha(value)
    
    def change_hotkey(self):
        """Open hotkey change dialog"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox
        from PyQt6.QtCore import Qt, QTimer, QDateTime
        
        class HotkeyDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("Change Hotkey")
                self.setModal(True)
                self.resize(400, 200)
                self.captured_keys = []
                self.recording = False
                
                # Apply dark theme
                self.setStyleSheet("""
                    QDialog {
                        background-color: #1a1a1a;
                        color: white;
                    }
                    QLabel {
                        color: white;
                        font-size: 14px;
                    }
                    QPushButton {
                        background-color: #4CAF50;
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background-color: #5CBF60;
                    }
                    QPushButton:disabled {
                        background-color: #666;
                    }
                """)
                
                layout = QVBoxLayout(self)
                
                # Instructions
                instruction = QLabel("Press the key combination you want to use as a hotkey:")
                layout.addWidget(instruction)
                
                # Current hotkey display
                self.current_label = QLabel("Current: Ctrl + Space")
                self.current_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
                layout.addWidget(self.current_label)
                
                # Capture area
                self.capture_label = QLabel("Click 'Record' and press your desired key combination")
                self.capture_label.setStyleSheet("color: #ccc; padding: 20px; border: 2px dashed #666; border-radius: 8px;")
                self.capture_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(self.capture_label)
                
                # Buttons
                button_layout = QHBoxLayout()
                
                self.record_btn = QPushButton("Record Hotkey")
                self.record_btn.clicked.connect(self.start_recording)
                
                self.apply_btn = QPushButton("Apply")
                self.apply_btn.clicked.connect(self.accept)
                self.apply_btn.setEnabled(False)
                
                self.cancel_btn = QPushButton("Cancel")
                self.cancel_btn.clicked.connect(self.reject)
                
                button_layout.addWidget(self.record_btn)
                button_layout.addWidget(self.apply_btn)
                button_layout.addWidget(self.cancel_btn)
                
                layout.addLayout(button_layout)
            
            def start_recording(self):
                """Start recording keystrokes"""
                self.recording = True
                self.captured_keys = []
                self.record_btn.setText("Recording... (ESC to cancel)")
                self.record_btn.setEnabled(False)
                self.apply_btn.setEnabled(False)
                self.cancel_btn.setEnabled(False)  # Disable cancel during recording
                self.capture_label.setText("Press your key combination now... (ESC to cancel)")
                self.capture_label.setStyleSheet("color: #4CAF50; padding: 20px; border: 2px solid #4CAF50; border-radius: 8px;")
                
                # Set focus to dialog to ensure key events are captured
                self.setFocus()
                
                # Stop recording after 10 seconds (longer timeout)
                QTimer.singleShot(10000, self.stop_recording)
            
            def stop_recording(self):
                """Stop recording keystrokes"""
                self.recording = False
                self.record_btn.setText("Record Hotkey")
                self.record_btn.setEnabled(True)
                self.cancel_btn.setEnabled(True)  # Re-enable cancel button
                
                if self.captured_keys:
                    keys_text = " + ".join(self.captured_keys)
                    self.capture_label.setText(f"Captured: {keys_text}")
                    self.capture_label.setStyleSheet("color: #4CAF50; padding: 20px; border: 2px solid #4CAF50; border-radius: 8px;")
                    self.apply_btn.setEnabled(True)
                else:
                    self.capture_label.setText("No keys captured. Try again.")
                    self.capture_label.setStyleSheet("color: #f44336; padding: 20px; border: 2px solid #f44336; border-radius: 8px;")
            
            def keyPressEvent(self, event):
                """Capture key presses during recording"""
                if not self.recording:
                    super().keyPressEvent(event)
                    return
                
                # Handle ESC to cancel recording
                if event.key() == Qt.Key.Key_Escape:
                    self.recording = False
                    self.record_btn.setText("Record Hotkey")
                    self.record_btn.setEnabled(True)
                    self.cancel_btn.setEnabled(True)
                    self.capture_label.setText("Recording canceled. Click 'Record' to try again.")
                    self.capture_label.setStyleSheet("color: #ccc; padding: 20px; border: 2px dashed #666; border-radius: 8px;")
                    event.accept()
                    return
                
                key_name = None
                if event.key() == Qt.Key.Key_Control:
                    key_name = "Ctrl"
                elif event.key() == Qt.Key.Key_Alt:
                    key_name = "Alt"
                elif event.key() == Qt.Key.Key_Shift:
                    key_name = "Shift"
                elif event.key() == Qt.Key.Key_Space:
                    key_name = "Space"
                elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                    key_name = "Enter"
                elif event.key() == Qt.Key.Key_Tab:
                    key_name = "Tab"
                elif event.key() == Qt.Key.Key_F1:
                    key_name = "F1"
                elif event.key() == Qt.Key.Key_F2:
                    key_name = "F2"
                elif event.key() == Qt.Key.Key_F3:
                    key_name = "F3"
                elif event.key() == Qt.Key.Key_F4:
                    key_name = "F4"
                elif event.key() == Qt.Key.Key_F5:
                    key_name = "F5"
                elif event.key() == Qt.Key.Key_F6:
                    key_name = "F6"
                elif event.key() == Qt.Key.Key_F7:
                    key_name = "F7"
                elif event.key() == Qt.Key.Key_F8:
                    key_name = "F8"
                elif event.key() == Qt.Key.Key_F9:
                    key_name = "F9"
                elif event.key() == Qt.Key.Key_F10:
                    key_name = "F10"
                elif event.key() == Qt.Key.Key_F11:
                    key_name = "F11"
                elif event.key() == Qt.Key.Key_F12:
                    key_name = "F12"
                else:
                    key_name = event.text().upper() if event.text() and event.text().isprintable() else None
                
                if key_name and key_name not in self.captured_keys:
                    self.captured_keys.append(key_name)
                    current_combo = " + ".join(self.captured_keys)
                    self.capture_label.setText(f"Recording: {current_combo}")
                    
                    # Auto-stop recording if we have a reasonable key combination (2+ keys)
                    if len(self.captured_keys) >= 2:
                        QTimer.singleShot(1000, self.stop_recording)  # Stop after 1 second
                
                event.accept()
        
        dialog = HotkeyDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.captured_keys:
                new_hotkey = " + ".join(dialog.captured_keys)
                self.hotkey_label.setText(new_hotkey)
                
                # Actually apply the new hotkey!
                self.parent_window.current_hotkey = dialog.captured_keys
                self.parent_window.hotkey_manager.set_hotkey(dialog.captured_keys)
                self.parent_window.save_config()  # Save immediately

                self.show_info_dialog("Hotkey Changed",
                    f"Hotkey successfully changed to: {new_hotkey}\n\n"
                    "The new hotkey is now active and has been saved!")
    
    def update_history_stats(self):
        """Update history statistics display"""
        if not self.parent_window:
            return
        
        current_session = getattr(self.parent_window, 'current_session', 'Default')
        self.current_session_label.setText(f"Current Session: {current_session}")
        
        # Get current session entries and total entries
        current_session_count = len(getattr(self.parent_window, 'current_session_history', []))
        total_count = len(getattr(self.parent_window, 'history', []))
        
        self.history_stats_label.setText(f"Current session: {current_session_count} entries | Total history: {total_count} entries")
    
    def start_new_session(self):
        """Start a new history session"""
        session_name = self.session_name_input.text().strip()
        if not session_name:
            QMessageBox.warning(self, "Invalid Session Name", "Please enter a session name.")
            return
        
        if not self.parent_window:
            return
        
        # Save current session to history
        if hasattr(self.parent_window, 'current_session_history'):
            session_data = {
                'name': getattr(self.parent_window, 'current_session', 'Default'),
                'entries': self.parent_window.current_session_history,
                'timestamp': QDateTime.currentDateTime().toString()
            }
            
            # Add to saved sessions
            if not hasattr(self.parent_window, 'saved_sessions'):
                self.parent_window.saved_sessions = []
            self.parent_window.saved_sessions.append(session_data)
        
        # Start new session
        self.parent_window.current_session = session_name
        self.parent_window.current_session_history = []
        self.session_name_input.clear()
        
        self.update_history_stats()
        self.show_info_dialog("New Session Started", f"Started new session: {session_name}")
    
    def export_history(self):
        """Export history to file"""
        from PyQt6.QtWidgets import QFileDialog
        from datetime import datetime
        import json
        
        if not self.parent_window:
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, 
            "Export History",
            f"dictator_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON Files (*.json);;Text Files (*.txt);;All Files (*)"
        )
        
        if not filename:
            return
        
        try:
            export_data = {
                'export_date': datetime.now().isoformat(),
                'current_session': {
                    'name': getattr(self.parent_window, 'current_session', 'Default'),
                    'entries': getattr(self.parent_window, 'current_session_history', [])
                },
                'total_history': getattr(self.parent_window, 'history', []),
                'saved_sessions': getattr(self.parent_window, 'saved_sessions', [])
            }
            
            if filename.endswith('.json'):
                with open(filename, 'w') as f:
                    json.dump(export_data, f, indent=2)
            else:
                # Export as text
                with open(filename, 'w') as f:
                    f.write(f"DICTATOR History Export - {export_data['export_date']}\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(f"Current Session: {export_data['current_session']['name']}\n")
                    f.write("-" * 30 + "\n")
                    for entry in export_data['current_session']['entries']:
                        f.write(f"• {entry}\n")
                    f.write(f"\nTotal History ({len(export_data['total_history'])} entries):\n")
                    f.write("-" * 30 + "\n")
                    for entry in export_data['total_history']:
                        f.write(f"• {entry}\n")
            
            self.show_info_dialog("Export Complete", f"History exported to:\n{filename}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export history:\n{str(e)}")
    
    def clear_current_session(self):
        """Clear current session history"""
        if not self.parent_window:
            return
        
        current_session = getattr(self.parent_window, 'current_session', 'Default')
        reply = QMessageBox.question(self, "Clear Current Session", 
            f"Are you sure you want to clear the current session '{current_session}'?\n\n"
            "This will remove all entries from the current session but keep total history.")
        
        if reply == QMessageBox.StandardButton.Yes:
            self.parent_window.current_session_history = []
            self.update_history_stats()
            self.show_info_dialog("Session Cleared", f"Current session '{current_session}' has been cleared.")
    
    def clear_all_history(self):
        """Clear all history"""
        if not self.parent_window:
            return
        
        reply = QMessageBox.question(self, "Clear All History",
            "WARNING: This will permanently delete ALL history including all sessions!\n\n"
            "This action cannot be undone. Are you sure?")
        
        if reply == QMessageBox.StandardButton.Yes:
            self.parent_window.history = []
            self.parent_window.current_session_history = []
            self.parent_window.saved_sessions = []
            
            # Clear history display in main window
            if hasattr(self.parent_window, 'history_layout'):
                # Clear all history items from UI
                for i in reversed(range(self.parent_window.history_layout.count())):
                    item = self.parent_window.history_layout.takeAt(i)
                    if item.widget():
                        item.widget().deleteLater()
            
            self.parent_window.save_config()
            self.update_history_stats()
            self.show_info_dialog("History Cleared", "All history has been permanently deleted.")
    
    def choose_background_color(self):
        """Choose background color with 0.1%-100% brightness gradients (21 levels for extra darkness)"""
        dialog = QColorDialog(QColor(getattr(self.parent_window, 'custom_bg_color', '#141414')), self)
        dialog.setWindowTitle("Choose Background Color")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        
        # Base colors for gradients (grays and dark theme colors)
        base_colors = [0xFFFFFF, 0x808080, 0x000000]  # White, Gray, Black - 3 colors × 16 levels = 48
        
        # Generate gradients from 0.1% to 100% brightness (21 levels for 5 more shades)
        gradient_colors = self.generate_color_gradient(base_colors, 21)
        
        # Set custom colors
        for i, color_int in enumerate(gradient_colors):
            if i < 16:  # QColorDialog supports up to 16 custom colors
                dialog.setCustomColor(i, color_int)
        
        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            color = dialog.currentColor()
            color_hex = color.name()
            text_color = 'white' if color.lightness() < 64 else 'black'
            self.bg_color_btn.setStyleSheet(f"QPushButton {{ background-color: {color_hex}; color: {text_color}; }}")
            
            if self.parent_window:
                self.parent_window.custom_bg_color = color_hex
                self.parent_window.apply_custom_colors()
    
    def choose_border_color(self):
        """Choose border color with 0.1%-100% brightness gradients (21 levels for extra darkness)"""
        dialog = QColorDialog(QColor(getattr(self.parent_window, 'custom_border_color', '#4CAF50')), self)
        dialog.setWindowTitle("Choose Border Color")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        
        # Base colors for gradients (accent colors)
        base_colors = [0x4CAF50, 0x2196F3, 0xFF9800]  # Green, Blue, Orange - 3 colors × 16 levels = 48
        
        # Generate gradients from 0.1% to 100% brightness (21 levels for 5 more shades)
        gradient_colors = self.generate_color_gradient(base_colors, 21)
        
        # Set custom colors
        for i, color_int in enumerate(gradient_colors):
            if i < 16:
                dialog.setCustomColor(i, color_int)
        
        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            color = dialog.currentColor()
            color_hex = color.name()
            text_color = 'white' if color.lightness() < 64 else 'black'
            self.border_color_btn.setStyleSheet(f"QPushButton {{ background-color: {color_hex}; color: {text_color}; }}")
            
            if self.parent_window:
                self.parent_window.custom_border_color = color_hex
                self.parent_window.apply_custom_colors()
    
    def choose_text_color(self):
        """Choose text color with 0.1%-100% brightness gradients (21 levels for extra darkness)"""
        dialog = QColorDialog(QColor(getattr(self.parent_window, 'custom_text_color', '#ffffff')), self)
        dialog.setWindowTitle("Choose Text Color")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        
        # Base colors for gradients (text-friendly colors)
        base_colors = [0xFFFFFF, 0xC0C0C0, 0x808080]  # White, Light Gray, Medium Gray - good for text
        
        # Generate gradients from 0.1% to 100% brightness (21 levels for 5 more shades)
        gradient_colors = self.generate_color_gradient(base_colors, 21)
        
        # Set custom colors
        for i, color_int in enumerate(gradient_colors):
            if i < 16:
                dialog.setCustomColor(i, color_int)
        
        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            color = dialog.currentColor()
            color_hex = color.name()
            text_color = 'black' if color.lightness() > 64 else 'white'
            self.text_color_btn.setStyleSheet(f"QPushButton {{ background-color: {color_hex}; color: {text_color}; }}")
            
            if self.parent_window:
                self.parent_window.custom_text_color = color_hex
                self.parent_window.apply_custom_colors()
    
    def choose_button_color(self):
        """Choose button color with 0.1%-100% brightness gradients (21 levels for extra darkness)"""
        dialog = QColorDialog(QColor(getattr(self.parent_window, 'custom_button_color', '#4CAF50')), self)
        dialog.setWindowTitle("Choose Button Color")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        
        # Base colors for gradients (vibrant accent colors)
        base_colors = [0xFF0000, 0x00FF00, 0x0000FF]  # Red, Green, Blue - primary colors
        
        # Generate gradients from 0.1% to 100% brightness (21 levels for 5 more shades)
        gradient_colors = self.generate_color_gradient(base_colors, 21)
        
        # Set custom colors
        for i, color_int in enumerate(gradient_colors):
            if i < 16:
                dialog.setCustomColor(i, color_int)
        
        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            color = dialog.currentColor()
            color_hex = color.name()
            text_color = 'white' if color.lightness() < 64 else 'black'
            self.button_color_btn.setStyleSheet(f"QPushButton {{ background-color: {color_hex}; color: {text_color}; }}")
            
            if self.parent_window:
                self.parent_window.custom_button_color = color_hex
                self.parent_window.apply_custom_colors()
    
    def choose_translation_bg_color(self):
        """Choose translation background color with 0.1%-100% brightness gradients (21 levels for extra darkness)"""
        dialog = QColorDialog(QColor(getattr(self.parent_window, 'custom_translation_bg_color', '#1a1a1a')), self)
        dialog.setWindowTitle("Choose Translation Background Color")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        
        # Base colors for gradients (dark backgrounds)
        base_colors = [0x000000, 0x404040, 0x808080]  # Black, Dark Gray, Medium Gray
        
        # Generate gradients from 0.1% to 100% brightness (21 levels for 5 more shades)
        gradient_colors = self.generate_color_gradient(base_colors, 21)
        
        # Set custom colors
        for i, color_int in enumerate(gradient_colors):
            if i < 16:
                dialog.setCustomColor(i, color_int)
        
        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            color = dialog.currentColor()
            color_hex = color.name()
            text_color = 'white' if color.lightness() < 64 else 'black'
            self.trans_bg_color_btn.setStyleSheet(f"QPushButton {{ background-color: {color_hex}; color: {text_color}; }}")
            
            if self.parent_window:
                self.parent_window.custom_translation_bg_color = color_hex
                self.parent_window.apply_custom_colors()
    
    def choose_translation_text_color(self):
        """Choose translation text color with 0.1%-100% brightness gradients (21 levels for extra darkness)"""
        dialog = QColorDialog(QColor(getattr(self.parent_window, 'custom_translation_text_color', '#ffffff')), self)
        dialog.setWindowTitle("Choose Translation Text Color")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        
        # Base colors for gradients (text colors)
        base_colors = [0xFFFFFF, 0x00FF00, 0x00FFFF]  # White, Green, Cyan - good for text
        
        # Generate gradients from 0.1% to 100% brightness (21 levels for 5 more shades)
        gradient_colors = self.generate_color_gradient(base_colors, 21)
        
        # Set custom colors
        for i, color_int in enumerate(gradient_colors):
            if i < 16:
                dialog.setCustomColor(i, color_int)
        
        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            color = dialog.currentColor()
            color_hex = color.name()
            text_color = 'black' if color.lightness() > 64 else 'white'
            self.trans_text_color_btn.setStyleSheet(f"QPushButton {{ background-color: {color_hex}; color: {text_color}; }}")
            
            if self.parent_window:
                self.parent_window.custom_translation_text_color = color_hex
                self.parent_window.apply_custom_colors()
    
    def choose_history_bg_color(self):
        """Choose history background color with 0.1%-100% brightness gradients (21 levels for extra darkness)"""
        dialog = QColorDialog(QColor(getattr(self.parent_window, 'custom_history_bg_color', '#0f0f0f')), self)
        dialog.setWindowTitle("Choose History Background Color")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        
        # Base colors for gradients (very dark backgrounds)
        base_colors = [0x000000, 0x202020, 0x404040]  # Black, Very Dark Gray, Dark Gray
        
        # Generate gradients from 0.1% to 100% brightness (21 levels for 5 more shades)
        gradient_colors = self.generate_color_gradient(base_colors, 21)
        
        # Set custom colors
        for i, color_int in enumerate(gradient_colors):
            if i < 16:
                dialog.setCustomColor(i, color_int)
        
        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            color = dialog.currentColor()
            color_hex = color.name()
            text_color = 'white' if color.lightness() < 64 else 'black'
            self.history_bg_color_btn.setStyleSheet(f"QPushButton {{ background-color: {color_hex}; color: {text_color}; }}")
            
            if self.parent_window:
                self.parent_window.custom_history_bg_color = color_hex
                self.parent_window.apply_custom_colors()
    
    def choose_history_text_color(self):
        """Choose history text color with 0.1%-100% brightness gradients (21 levels for extra darkness)"""
        dialog = QColorDialog(QColor(getattr(self.parent_window, 'custom_history_text_color', '#cccccc')), self)
        dialog.setWindowTitle("Choose History Text Color")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        
        # Base colors for gradients (muted text colors)
        base_colors = [0xFFFFFF, 0xCCCCCC, 0x999999]  # White, Light Gray, Medium Gray
        
        # Generate gradients from 0.1% to 100% brightness (21 levels for 5 more shades)
        gradient_colors = self.generate_color_gradient(base_colors, 21)
        
        # Set custom colors
        for i, color_int in enumerate(gradient_colors):
            if i < 16:
                dialog.setCustomColor(i, color_int)
        
        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            color = dialog.currentColor()
            color_hex = color.name()
            text_color = 'black' if color.lightness() > 64 else 'white'
            self.history_text_color_btn.setStyleSheet(f"QPushButton {{ background-color: {color_hex}; color: {text_color}; }}")
            
            if self.parent_window:
                self.parent_window.custom_history_text_color = color_hex
                self.parent_window.apply_custom_colors()
    
    def reset_colors(self):
        """Reset colors to defaults"""
        if self.parent_window:
            self.parent_window.custom_bg_color = "#141414"
            self.parent_window.custom_border_color = "#4CAF50" 
            self.parent_window.custom_text_color = "#ffffff"
            self.parent_window.custom_button_color = "#4CAF50"
            self.parent_window.custom_translation_bg_color = "#1a1a1a"
            self.parent_window.custom_translation_text_color = "#ffffff"
            self.parent_window.custom_history_bg_color = "#0f0f0f"
            self.parent_window.custom_history_text_color = "#cccccc"
            
            # Update button displays
            self.bg_color_btn.setStyleSheet("QPushButton { background-color: #141414; color: white; }")
            self.border_color_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; }")
            self.text_color_btn.setStyleSheet("QPushButton { background-color: #ffffff; color: black; }")
            self.button_color_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; }")
            self.trans_bg_color_btn.setStyleSheet("QPushButton { background-color: #1a1a1a; color: white; }")
            self.trans_text_color_btn.setStyleSheet("QPushButton { background-color: #ffffff; color: black; }")
            self.history_bg_color_btn.setStyleSheet("QPushButton { background-color: #0f0f0f; color: white; }")
            self.history_text_color_btn.setStyleSheet("QPushButton { background-color: #cccccc; color: black; }")
            
            # Apply reset colors immediately
            self.parent_window.apply_custom_colors()
    
    def choose_translation_font(self):
        """Open font dialog for translation text"""
        from PyQt6.QtWidgets import QFontDialog
        from PyQt6.QtGui import QFont
        
        if self.parent_window:
            current_font = QFont(self.parent_window.custom_translation_font_family, 
                               self.parent_window.custom_translation_font_size)
            font, ok = QFontDialog.getFont(current_font, self)
            
            if ok:
                self.parent_window.custom_translation_font_family = font.family()
                self.parent_window.custom_translation_font_size = font.pointSize()
                self.translation_font_btn.setText(f"🔤 {font.family()}")
                self.translation_font_size_spin.setValue(font.pointSize())
                self.parent_window.apply_custom_colors()
                
    def choose_history_font(self):
        """Open font dialog for history text"""
        from PyQt6.QtWidgets import QFontDialog
        from PyQt6.QtGui import QFont
        
        if self.parent_window:
            current_font = QFont(self.parent_window.custom_history_font_family, 
                               self.parent_window.custom_history_font_size)
            font, ok = QFontDialog.getFont(current_font, self)
            
            if ok:
                self.parent_window.custom_history_font_family = font.family()
                self.parent_window.custom_history_font_size = font.pointSize()
                self.history_font_btn.setText(f"🔤 {font.family()}")
                self.history_font_size_spin.setValue(font.pointSize())
                self.parent_window.apply_custom_colors()
    
    def update_translation_font_size(self, size):
        """Update translation font size from spinner"""
        if self.parent_window:
            self.parent_window.custom_translation_font_size = size
            self.parent_window.apply_custom_colors()
    
    def update_history_font_size(self, size):
        """Update history font size from spinner"""
        if self.parent_window:
            self.parent_window.custom_history_font_size = size
            self.parent_window.apply_custom_colors()
    
    def reset_fonts(self):
        """Reset fonts to defaults"""
        if self.parent_window:
            self.parent_window.custom_translation_font_family = "Arial"
            self.parent_window.custom_translation_font_size = 14
            self.parent_window.custom_history_font_family = "Arial"
            self.parent_window.custom_history_font_size = 12
            
            # Update UI displays
            self.translation_font_btn.setText("🔤 Choose Font")
            self.translation_font_size_spin.setValue(14)
            self.history_font_btn.setText("🔤 Choose Font")
            self.history_font_size_spin.setValue(12)
            
            # Apply reset fonts immediately
            self.parent_window.apply_custom_colors()
            
            self.show_info_dialog("Colors Reset", "Colors have been reset to defaults.")
    
    def generate_color_gradient(self, base_colors, levels=21):
        """Generate color gradients from 0.1% to 100% brightness for given base colors (21 levels for extra dark shades)"""
        gradient_colors = []
        for base_color in base_colors:
            r = (base_color >> 16) & 0xFF
            g = (base_color >> 8) & 0xFF  
            b = base_color & 0xFF
            
            # Create brightness levels from 0.1% to 100% (much darker!)
            for i in range(levels):
                brightness = 0.001 + (0.999 * i / (levels - 1))  # 0.1% to 100%
                new_r = int(r * brightness)
                new_g = int(g * brightness) 
                new_b = int(b * brightness)
                gradient_colors.append((new_r << 16) | (new_g << 8) | new_b)
        return gradient_colors[:63]  # Limit to 63 colors max (3 colors × 21 levels)
    
    def toggle_debug_mode(self, state):
        """
        Handle debug mode checkbox toggle.
        Updates log level immediately when checkbox is changed.

        Args:
            state: Qt.CheckState value (0=unchecked, 2=checked)
        """
        from src import logger

        # state = 2 means checked, 0 means unchecked
        debug_enabled = (state == 2)

        if debug_enabled:
            logger.set_log_level('DEBUG')
            log.info("Debug mode enabled - log level set to DEBUG")
        else:
            logger.set_log_level('INFO')
            log.info("Debug mode disabled - log level set to INFO")

        # Save to parent window
        if self.parent_window:
            self.parent_window.debug_mode_enabled = debug_enabled

    def apply_settings(self):
        """Apply settings without closing dialog"""
        if not self.parent_window:
            return
            
        # Apply always on top
        if hasattr(self.parent_window, 'toggle_always_on_top'):
            self.parent_window.always_on_top = self.always_on_top_checkbox.isChecked()
            self.parent_window.toggle_always_on_top(self.always_on_top_checkbox.isChecked())
        
        # Apply auto-hide
        if hasattr(self.parent_window, 'auto_hide_checkbox'):
            self.parent_window.auto_hide_checkbox.setChecked(self.auto_hide_checkbox.isChecked())
        
        # Apply microphone selection
        selected_index = self.microphone_combo.currentIndex()
        if selected_index >= 0 and hasattr(self.parent_window, 'recorder'):
            # Get the actual device index from itemData
            device_index = self.microphone_combo.itemData(selected_index)
            if device_index is not None:
                success = self.parent_window.recorder.set_microphone(device_index)
                if success:
                    log.info(f"SETTINGS: Applied microphone selection: device index {device_index}")
                    # Save config immediately to persist the change
                    self.parent_window.save_config()
                else:
                    log.error(f"SETTINGS: Failed to apply microphone selection: device index {device_index}")
        
        # Apply opacity using alpha channel (always works!)
        if hasattr(self, 'opacity_slider'):
            opacity_value = self.opacity_slider.value()
            self.parent_window.update_window_alpha(opacity_value)

        # Apply recording mode
        if hasattr(self, 'recording_mode_combo'):
            selected_mode = self.recording_mode_combo.currentData()
            if selected_mode:
                self.parent_window.recording_mode = selected_mode
                log.info(f"SETTINGS: Applied recording mode: {selected_mode}")

        # Apply recording timeout
        if hasattr(self, 'timeout_combo'):
            selected_timeout = self.timeout_combo.currentData()
            if selected_timeout:
                self.parent_window.recording_timeout = selected_timeout
                log.info(f"SETTINGS: Applied recording timeout: {selected_timeout}s")

        # Apply silence detection settings
        if hasattr(self, 'silence_detection_checkbox'):
            self.parent_window.silence_detection_enabled = self.silence_detection_checkbox.isChecked()
            log.info(f"SETTINGS: Applied silence detection enabled: {self.parent_window.silence_detection_enabled}")

        if hasattr(self, 'silence_threshold_spin'):
            self.parent_window.silence_threshold = self.silence_threshold_spin.value()
            log.info(f"SETTINGS: Applied silence threshold: {self.parent_window.silence_threshold}%")

        if hasattr(self, 'silence_duration_combo'):
            selected_duration = self.silence_duration_combo.currentData()
            if selected_duration:
                self.parent_window.silence_duration = selected_duration
                log.info(f"SETTINGS: Applied silence duration: {selected_duration}s")

        # Apply Whisper model settings
        self.save_whisper_settings()

        # Apply custom colors and save config
        self.parent_window.apply_custom_colors()
        self.parent_window.save_config()

    def accept_settings(self):
        """Apply settings and close dialog"""
        self.apply_settings()
        self.accept()

