#!/usr/bin/env python3

import sys
import json
import os
from pathlib import Path
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
    from settings_ui import SettingsDialog
    from common_ui import ResizeGrip, DraggableFrame
    from logger import get_logger
except ImportError:
    # Handle relative imports when running as module
    from .recorder import PureRecorder
    from .hotkey_manager import HotkeyManager
    from .ui_utils import UIWatchdog, UIUpdateRequest
    from .version import __version__
    from .settings_ui import SettingsDialog
    from .common_ui import ResizeGrip, DraggableFrame
    from .logger import get_logger

# Initialize logger
log = get_logger(__name__)


class DictatorWindow(QMainWindow):
    def __init__(self, no_tray=False):
        super().__init__()
        log.info("Initializing DICTATOR window")
        self.recorder = PureRecorder()
        # Load hotkey from config or use default
        self.current_hotkey = ["Ctrl", "Space"]  # Default
        self.hotkey_manager = HotkeyManager(self.current_hotkey)
        self.history = []
        
        # Session management
        self.current_session = "Default"
        self.current_session_history = []
        self.saved_sessions = []
        
        # Track current opacity percentage (since windowOpacity doesn't work)
        self.current_opacity_percent = 95
        
        # Custom color scheme
        self.custom_bg_color = "#141414"
        self.custom_border_color = "#4CAF50" 
        self.custom_text_color = "#ffffff"
        self.custom_button_color = "#4CAF50"
        self.custom_translation_bg_color = "#1a1a1a"
        self.custom_translation_text_color = "#ffffff"
        self.custom_history_bg_color = "#0f0f0f"
        self.custom_history_text_color = "#cccccc"
        
        # Font settings
        self.custom_translation_font_family = "Arial"
        self.custom_translation_font_size = 14
        self.custom_history_font_family = "Arial" 
        self.custom_history_font_size = 12
        self.config_path = Path.home() / ".config" / "dictator" / "config.json"
        self.settings_visible = False
        
        # Window state settings
        self.always_on_top = True  # Default to always on top
        
        
        # Prevent recursion during shutdown
        self.is_closing = False
        
        # UI update queue system like SAI
        self.ui_update_queue = queue.Queue()
        
        # Recording timer
        self.recording_start_time = None
        self.recording_timer = QTimer()
        self.recording_timer.timeout.connect(self.update_recording_timer)
        
        # Start UI watchdog
        self.watchdog = UIWatchdog(self)
        
        self.init_ui()
        self.load_config()
        
        
        # Auto-hide timer
        self.hide_timer = QTimer()
        self.hide_timer.timeout.connect(self.auto_hide)
        self.hide_timer.setSingleShot(True)
        
        # UI update processing timer like SAI
        self.ui_update_timer = QTimer()
        self.ui_update_timer.timeout.connect(self.process_ui_updates)
        self.ui_update_timer.start(16)  # ~60fps like SAI
        
        # Connect status update callback
        self.recorder.update_status_callback = self.update_status_label
        
        # Start hotkey manager
        self.hotkey_manager.start(self.toggle_recording)
        
        # System tray setup
        if not no_tray:
            self.setup_system_tray()
    
    def request_ui_update(self, action, **kwargs):
        """Thread-safe method to request UI update like SAI"""
        self.ui_update_queue.put(UIUpdateRequest(action, **kwargs))
    
    def process_ui_updates(self):
        """Process all pending UI updates like SAI (runs in main thread)"""
        try:
            processed_count = 0
            while True:
                try:
                    request = self.ui_update_queue.get_nowait()
                    print(f"🔥 PROCESSING UI UPDATE: {request.action}")
                    self._handle_ui_update(request)
                    processed_count += 1
                    print(f"🔥 UI UPDATE COMPLETED: {request.action}")
                    
                    # Process max 10 updates per cycle to avoid blocking
                    if processed_count >= 10:
                        print(f"🔥 Processed {processed_count} updates, yielding control")
                        break
                        
                except queue.Empty:
                    break
        except Exception as e:
            print(f"🚨 FATAL UI update error: {e}")
            import traceback
            traceback.print_exc()
            # Don't crash the whole app, just log the error
    
    def _handle_ui_update(self, request):
        """Handle individual UI update request like SAI"""
        try:
            if request.action == "transcription_complete":
                text = request.kwargs.get('text', '')
                language = request.kwargs.get('language', 'en')
                self._safe_handle_transcription(text, language)
            elif request.action == "add_history_item":
                text = request.kwargs.get('text', '')
                self._safe_add_history_item(text)
            elif request.action == "update_status":
                status = request.kwargs.get('status', '')
                style = request.kwargs.get('style', '')
                self._safe_update_status(status, style)
            elif request.action == "toggle_recording":
                print("🔥 UI_UPDATE: Processing toggle_recording from hotkey")
                self._safe_toggle_recording()
            elif request.action == "copy_to_clipboard":
                text = request.kwargs.get('text', '')
                print("🔥 UI_UPDATE: Processing copy_to_clipboard")
                self._safe_copy_to_clipboard(text)
            elif request.action == "type_text":
                text = request.kwargs.get('text', '')
                print("🔥 UI_UPDATE: Processing type_text")
                self._safe_type_text(text)
        except Exception as e:
            print(f"Error handling UI update {request.action}: {e}")
    
    def init_ui(self):
        self.setWindowTitle(f"DICTATOR v{__version__}")
        self.setObjectName("DICTATOR")
        
        # Set window icon - GNOME-compatible approach
        self.setup_window_icon()
        
        # Set initial window flags based on always_on_top setting
        # Use Window instead of Tool for better GNOME icon support
        base_flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        if self.always_on_top:
            initial_flags = base_flags | Qt.WindowType.WindowStaysOnTopHint
        else:
            initial_flags = base_flags
            
        self.setWindowFlags(initial_flags)
        
        # Additional GNOME hints for better icon recognition
        self.setWindowTitle("DICTATOR")  # Ensure window has a title even if frameless
        # Make window resizable by removing fixed size constraints
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        main_widget = QWidget()
        main_widget.setStyleSheet("""
            QWidget {
                background-color: rgba(20, 20, 20, 240);
                border-radius: 12px;
                border: 2px solid rgba(76, 175, 80, 120);
            }
        """)
        main_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        
        # Store reference to main widget for opacity updates
        self.main_widget = main_widget
        
        # Create main layout with proper spacing control
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Create top content area that won't stretch
        top_content = QWidget()
        top_layout = QVBoxLayout(top_content)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        # Header - draggable title area
        title_frame = DraggableFrame(self)
        title_frame.setFixedHeight(40)
        title_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(25, 25, 25, 180);
                border: none;
                border-radius: 8px;
                margin: 2px;
            }
        """)
        
        header_layout = QHBoxLayout(title_frame)
        header_layout.setContentsMargins(10, 5, 10, 5)
        
        title_label = QLabel("🎤 DICTATOR")
        title_label.setStyleSheet("color: #4CAF50; font-size: 20px; font-weight: bold;")
        
        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(30, 30)
        settings_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(70, 70, 70, 150);
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: rgba(90, 90, 90, 180);
            }
        """)
        settings_btn.clicked.connect(self.toggle_settings)
        
        # Minimize button
        minimize_btn = QPushButton("−")
        minimize_btn.setFixedSize(30, 30)
        minimize_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(76, 175, 80, 150);
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: rgba(96, 195, 100, 180);
            }
        """)
        minimize_btn.clicked.connect(self.hide_to_tray)
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(200, 50, 50, 150);
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: rgba(220, 70, 70, 180);
            }
        """)
        close_btn.clicked.connect(self.close_application)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(settings_btn)
        header_layout.addWidget(minimize_btn)
        header_layout.addWidget(close_btn)
        
        top_layout.addWidget(title_frame)
        
        # Status
        engine_status = "Whisper (loading...)"
        self.status_label = QLabel(f"✅ Ready - {engine_status} - Press Ctrl+Space to dictate")
        self.status_label.setStyleSheet("color: #4CAF50; font-size: 13px; margin: 8px 0;")
        top_layout.addWidget(self.status_label)
        
        # Recording timer
        self.timer_label = QLabel("⏱️ 00:00")
        self.timer_label.setStyleSheet("color: #FF9800; font-size: 16px; font-weight: bold; margin: 4px 0; text-align: center;")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label.hide()  # Initially hidden
        top_layout.addWidget(self.timer_label)
        
        # Manual record button
        self.record_btn = QPushButton("🎤 Start Listening")
        self.record_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(76, 175, 80, 150);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 20px;
                font-size: 14px;
                font-weight: bold;
                margin: 8px 0;
            }
            QPushButton:hover {
                background-color: rgba(96, 195, 100, 180);
            }
            QPushButton:pressed {
                background-color: rgba(56, 155, 60, 200);
            }
        """)
        self.record_btn.clicked.connect(self.toggle_manual_recording)
        top_layout.addWidget(self.record_btn)
        
        # Volume meter
        self.volume_frame = QFrame()
        self.volume_frame.setFixedHeight(40)
        self.volume_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(10, 10, 10, 200); 
                border-radius: 8px; 
                margin: 5px 0;
                border: 1px solid rgba(76, 175, 80, 80);
            }
        """)
        
        volume_layout = QHBoxLayout()
        volume_layout.setContentsMargins(10, 6, 10, 6)
        
        # Just the volume bars - no "LEVEL:" text
        
        self.volume_bars = []
        for i in range(30):
            # Use QFrame instead of QProgressBar for actual volume bars
            bar = QFrame()
            bar.setFixedSize(6, 20)
            
            if i < 20:
                color = "#4CAF50"  # Green
            elif i < 25:
                color = "#FFC107"  # Yellow  
            else:
                color = "#F44336"  # Red
            
            # Default to off state
            bar.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(40, 40, 40, 120);
                    border: 1px solid rgba(80, 80, 80, 60);
                    border-radius: 2px;
                }}
            """)
            
            # Store the colors for later use
            bar.on_color = color
            bar.off_color = "rgba(40, 40, 40, 120)"
            bar.is_on = False
            
            self.volume_bars.append(bar)
            volume_layout.addWidget(bar)
        
        self.volume_frame.setLayout(volume_layout)
        top_layout.addWidget(self.volume_frame)
        # Keep volume frame visible like SAI - always show audio levels
        self.volume_frame.show()
        
        # Make sure volume bars are properly initialized
        for bar in self.volume_bars:
            bar.show()
        
        # Create volume timer but don't start it yet - only during recording
        self.volume_timer = QTimer()
        self.volume_timer.timeout.connect(self.update_volume_bars)
        print("🔥 VOLUME: Volume timer created but not started (will start during recording)")
        
        
        # Current transcription text area
        current_label = QLabel("Current Transcription:")
        current_label.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: bold; margin-top: 8px;")
        top_layout.addWidget(current_label)
        
        self.current_text_area = QTextEdit()
        self.current_text_area.setPlaceholderText("Most recent transcription will appear here... (Click to copy to clipboard)")
        self.current_text_area.setStyleSheet("""
            QTextEdit {
                background-color: rgba(25, 25, 25, 200);
                border: 2px solid rgba(76, 175, 80, 100);
                border-radius: 8px;
                color: #FFFFFF;
                font-size: 14px;
                font-weight: bold;
                padding: 8px;
                margin: 4px 0;
            }
            QTextEdit:hover {
                border: 2px solid rgba(76, 175, 80, 150);
                background-color: rgba(30, 30, 30, 200);
            }
        """)
        self.current_text_area.setFixedHeight(80)
        self.current_text_area.setReadOnly(True)
        
        # Make it clickable to copy
        self.current_text_area.mousePressEvent = self.copy_current_text
        top_layout.addWidget(self.current_text_area)
        
        # History collapsible section
        self.history_toggle = QPushButton("📜 History (0 items) ▼")
        self.history_toggle.setStyleSheet("""
            QPushButton {
                background-color: rgba(76, 175, 80, 100);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
                font-weight: bold;
                text-align: left;
                margin: 8px 0 4px 0;
            }
            QPushButton:hover {
                background-color: rgba(96, 195, 100, 120);
            }
            QPushButton:pressed {
                background-color: rgba(56, 155, 60, 150);
            }
        """)
        self.history_toggle.clicked.connect(self.toggle_history)
        
        # Add top content to main layout (no stretch)
        layout.addWidget(top_content)
        
        # Add history toggle button
        layout.addWidget(self.history_toggle)
        
        # History area (initially visible)
        self.history_scroll = QScrollArea()
        self.history_scroll.setStyleSheet("""
            QScrollArea {
                background-color: rgba(15, 15, 15, 200);
                border: 2px solid rgba(76, 175, 80, 100);
                border-radius: 8px;
                margin: 0 0 8px 0;
            }
            QScrollBar:vertical {
                background-color: rgba(40, 40, 40, 120);
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: rgba(76, 175, 80, 150);
                border-radius: 6px;
                min-height: 20px;
            }
        """)
        
        self.history_widget = QWidget()
        self.history_layout = QVBoxLayout()
        self.history_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.history_widget.setLayout(self.history_layout)
        
        self.history_scroll.setWidget(self.history_widget)
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setMinimumHeight(100)  # Set minimum instead of fixed
        self.history_collapsed = False
        
        # Add history scroll area with stretch factor to fill remaining space
        layout.addWidget(self.history_scroll, 1)  # stretch factor = 1 to expand
        
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)
        
        # Store main widget reference for dragging
        self.main_widget = main_widget
        
        # Add resize grips in corners
        self.add_resize_grips()
        
        self.resize(550, 400)
        self.setMinimumSize(400, 300)  # Set minimum size for resizing
        self.move(100, 100)
        self.show()
        self.raise_()
        self.activateWindow()
    
    def setup_window_icon(self):
        """Setup window icon for GNOME compatibility"""
        # First, try to use the application's icon if already set
        app_icon = QApplication.instance().windowIcon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
            print("✅ Using application icon for window")
            return
        
        # If no app icon, create our own multi-size icon
        base_dir = os.path.dirname(__file__)
        app_icon = QIcon()
        icon_loaded = False
        
        # Add all available icon sizes for GNOME compatibility
        sizes = ['256', '128', '64', '48', '32', '16']
        for size in sizes:
            icon_path = os.path.join(base_dir, 'icons', f'dictator-{size}.png')
            if os.path.exists(icon_path):
                app_icon.addFile(icon_path, QSize(int(size), int(size)))
                print(f"🎯 Added window icon size {size}x{size}: {icon_path}")
                icon_loaded = True
        
        # Add main icon as fallback
        main_icon = os.path.join(base_dir, 'icons', 'dictator.png')
        if os.path.exists(main_icon):
            app_icon.addFile(main_icon)
            print(f"🎯 Added main window icon: {main_icon}")
            icon_loaded = True
        
        if icon_loaded:
            self.setWindowIcon(app_icon)
            print("✅ Window icon set for GNOME compatibility")
        else:
            print("🚨 No window icons found")
    
    def update_window_alpha(self, opacity_percent):
        """Update window transparency using alpha channel (this actually works!)"""
        # Convert percentage (50-100) to alpha value (127-255)
        alpha = int((opacity_percent / 100.0) * 255)
        alpha = max(127, min(255, alpha))  # Clamp between 127-255
        
        # Store current opacity
        self.current_opacity_percent = opacity_percent
        
        # Use custom colors if available, otherwise defaults
        bg_rgb = QColor(getattr(self, 'custom_bg_color', '#141414'))
        border_color = getattr(self, 'custom_border_color', '#4CAF50')
        
        # Update main widget background with custom colors and new alpha
        self.main_widget.setStyleSheet(f"""
            QWidget {{
                background-color: rgba({bg_rgb.red()}, {bg_rgb.green()}, {bg_rgb.blue()}, {alpha});
                border-radius: 12px;
                border: 2px solid {border_color};
            }}
        """)
        print(f"🔥 OPACITY: Updated window alpha to {alpha} ({opacity_percent}%) with custom colors")
    
    def apply_custom_colors(self):
        """Apply custom colors to all UI components"""
        if not hasattr(self, 'main_widget'):
            return
        
        # Get custom colors with fallbacks
        bg_color = getattr(self, 'custom_bg_color', '#141414')
        border_color = getattr(self, 'custom_border_color', '#4CAF50')
        text_color = getattr(self, 'custom_text_color', '#ffffff')
        button_color = getattr(self, 'custom_button_color', '#4CAF50')
        
        # Apply custom colors to main widget background
        alpha = int((self.current_opacity_percent / 100.0) * 255)
        bg_rgb = QColor(bg_color)
        
        self.main_widget.setStyleSheet(f"""
            QWidget {{
                background-color: rgba({bg_rgb.red()}, {bg_rgb.green()}, {bg_rgb.blue()}, {alpha});
                border-radius: 12px;
                border: 2px solid {border_color};
            }}
        """)
        
        # Update status label color
        if hasattr(self, 'status_label'):
            self.status_label.setStyleSheet(f"color: {text_color}; font-size: 13px; margin: 8px 0;")
        
        # Update timer label color
        if hasattr(self, 'timer_label'):
            self.timer_label.setStyleSheet(f"color: {button_color}; font-size: 16px; font-weight: bold; margin: 4px 0; text-align: center;")
        
        # Update current transcription label and text area
        current_labels = self.findChildren(QLabel)
        for widget in current_labels:
            if "Current Transcription:" in widget.text():
                widget.setStyleSheet(f"color: {button_color}; font-size: 12px; font-weight: bold; margin-top: 8px;")
                break
        
        if hasattr(self, 'current_text_area'):
            # Use the new translation color and font properties
            translation_bg_color = getattr(self, 'custom_translation_bg_color', '#1a1a1a')
            translation_text_color = getattr(self, 'custom_translation_text_color', '#ffffff')
            translation_font_family = getattr(self, 'custom_translation_font_family', 'Arial')
            translation_font_size = getattr(self, 'custom_translation_font_size', 14)
            
            trans_bg_rgba = QColor(translation_bg_color)
            trans_text_rgba = QColor(translation_text_color)
            # Create a lighter version of translation text color for placeholder
            placeholder_color = f"rgba({trans_text_rgba.red()}, {trans_text_rgba.green()}, {trans_text_rgba.blue()}, 128)"
            
            self.current_text_area.setStyleSheet(f"""
                QTextEdit {{
                    background-color: rgba({trans_bg_rgba.red()}, {trans_bg_rgba.green()}, {trans_bg_rgba.blue()}, 200);
                    color: {translation_text_color};
                    border: 2px solid {border_color};
                    border-radius: 8px;
                    padding: 8px;
                    font-family: {translation_font_family};
                    font-size: {translation_font_size}px;
                    font-weight: bold;
                    margin: 4px 0;
                }}
                QTextEdit:hover {{
                    border: 2px solid {button_color};
                    background-color: rgba({trans_bg_rgba.red()}, {trans_bg_rgba.green()}, {trans_bg_rgba.blue()}, 220);
                }}
                QTextEdit[placeholderText] {{
                    color: {placeholder_color};
                }}
            """)
        
        # Update start listening button
        if hasattr(self, 'record_btn'):
            button_rgb = QColor(button_color)
            self.record_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba({button_rgb.red()}, {button_rgb.green()}, {button_rgb.blue()}, 150);
                    color: {text_color};
                    border: none;
                    border-radius: 8px;
                    padding: 12px 20px;
                    font-size: 14px;
                    font-weight: bold;
                    margin: 8px 0;
                }}
                QPushButton:hover {{
                    background-color: rgba({button_rgb.red()}, {button_rgb.green()}, {button_rgb.blue()}, 180);
                }}
                QPushButton:pressed {{
                    background-color: rgba({button_rgb.red()}, {button_rgb.green()}, {button_rgb.blue()}, 200);
                }}
            """)
        
        # Update volume bars with custom colors
        if hasattr(self, 'volume_bars'):
            for i, bar in enumerate(self.volume_bars):
                if i < 20:
                    bar_color = button_color  # Use button color for volume bars
                elif i < 25:
                    bar_color = "#FFC107"  # Keep yellow for warning
                else:
                    bar_color = "#F44336"  # Keep red for danger
                
                bar.on_color = bar_color
                # Update current styling if bar is off
                if not getattr(bar, 'is_on', False):
                    bg_rgba = QColor(bg_color)
                    bar.setStyleSheet(f"""
                        QFrame {{
                            background-color: rgba({bg_rgba.red()}, {bg_rgba.green()}, {bg_rgba.blue()}, 120);
                            border: 1px solid {border_color};
                            border-radius: 2px;
                        }}
                    """)
        
        # Update volume frame border
        if hasattr(self, 'volume_frame'):
            bg_rgba = QColor(bg_color)
            self.volume_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba({bg_rgba.red()}, {bg_rgba.green()}, {bg_rgba.blue()}, 200); 
                    border-radius: 8px; 
                    margin: 5px 0;
                    border: 1px solid {border_color};
                }}
            """)
        
        # Update history toggle button
        if hasattr(self, 'history_toggle'):
            button_rgb = QColor(button_color)
            self.history_toggle.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba({button_rgb.red()}, {button_rgb.green()}, {button_rgb.blue()}, 100);
                    color: {text_color};
                    border: none;
                    border-radius: 6px;
                    padding: 8px 12px;
                    font-size: 12px;
                    font-weight: bold;
                    text-align: left;
                    margin: 8px 0 4px 0;
                }}
                QPushButton:hover {{
                    background-color: rgba({button_rgb.red()}, {button_rgb.green()}, {button_rgb.blue()}, 120);
                }}
                QPushButton:pressed {{
                    background-color: rgba({button_rgb.red()}, {button_rgb.green()}, {button_rgb.blue()}, 150);
                }}
            """)
        
        # Update history scroll area and contents
        if hasattr(self, 'history_scroll'):
            # Use the new history color properties
            history_bg_color = getattr(self, 'custom_history_bg_color', '#0f0f0f')
            hist_bg_rgba = QColor(history_bg_color)
            
            self.history_scroll.setStyleSheet(f"""
                QScrollArea {{
                    background-color: rgba({hist_bg_rgba.red()}, {hist_bg_rgba.green()}, {hist_bg_rgba.blue()}, 200);
                    border: 2px solid {border_color};
                    border-radius: 8px;
                    margin: 0 0 8px 0;
                }}
                QScrollBar:vertical {{
                    background-color: rgba({hist_bg_rgba.red()}, {hist_bg_rgba.green()}, {hist_bg_rgba.blue()}, 120);
                    width: 12px;
                    border-radius: 6px;
                }}
                QScrollBar::handle:vertical {{
                    background-color: {button_color};
                    border-radius: 6px;
                    min-height: 20px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background-color: {border_color};
                }}
            """)
        
        # Update history widget background
        if hasattr(self, 'history_widget'):
            # Use the new history color properties
            history_bg_color = getattr(self, 'custom_history_bg_color', '#0f0f0f')
            history_text_color = getattr(self, 'custom_history_text_color', '#cccccc')
            hist_bg_rgba = QColor(history_bg_color)
            
            self.history_widget.setStyleSheet(f"""
                QWidget {{
                    background-color: rgba({hist_bg_rgba.red()}, {hist_bg_rgba.green()}, {hist_bg_rgba.blue()}, 0);
                    color: {history_text_color};
                }}
            """)
        
        # Update all history item buttons in the history layout
        if hasattr(self, 'history_layout'):
            themed_style = self.get_themed_history_item_style()
            for i in range(self.history_layout.count()):
                item = self.history_layout.itemAt(i)
                if item and item.widget() and isinstance(item.widget(), QPushButton):
                    # Check if it's a history item button (contains 📝)
                    if "📝" in item.widget().text():
                        item.widget().setStyleSheet(themed_style)
        
        # Update title label color
        title_widgets = self.findChildren(QLabel)
        for widget in title_widgets:
            if "DICTATOR" in widget.text():
                widget.setStyleSheet(f"color: {border_color}; font-size: 20px; font-weight: bold;")
                break
        
        # Update resize grips to use border color
        grip_style = f"""
            QLabel {{
                background-color: rgba({QColor(border_color).red()}, {QColor(border_color).green()}, {QColor(border_color).blue()}, 150);
                border: 2px solid {border_color};
                border-radius: 8px;
            }}
            QLabel:hover {{
                background-color: rgba({QColor(border_color).red()}, {QColor(border_color).green()}, {QColor(border_color).blue()}, 200);
            }}
        """
        if hasattr(self, 'bottom_right_grip'):
            self.bottom_right_grip.setStyleSheet(grip_style)
        if hasattr(self, 'bottom_left_grip'):
            self.bottom_left_grip.setStyleSheet(grip_style)
        if hasattr(self, 'top_right_grip'):
            self.top_right_grip.setStyleSheet(grip_style)
        if hasattr(self, 'top_left_grip'):
            self.top_left_grip.setStyleSheet(grip_style)
        
        print(f"🎨 COLORS: Applied comprehensive theme - BG: {bg_color}, Border: {border_color}, Text: {text_color}, Button: {button_color}")
    
    def get_themed_history_item_style(self):
        """Generate themed stylesheet for history items"""
        # Use the new history color and font properties
        history_bg_color = getattr(self, 'custom_history_bg_color', '#0f0f0f')
        history_text_color = getattr(self, 'custom_history_text_color', '#cccccc')
        history_font_family = getattr(self, 'custom_history_font_family', 'Arial')
        history_font_size = getattr(self, 'custom_history_font_size', 12)
        border_color = getattr(self, 'custom_border_color', '#4CAF50')
        button_color = getattr(self, 'custom_button_color', '#4CAF50')
        
        print(f"🎨 HISTORY_STYLE: BG: {history_bg_color}, Text: {history_text_color}, Font: {history_font_family} {history_font_size}px, Border: {border_color}, Button: {button_color}")
        
        hist_bg_rgba = QColor(history_bg_color)
        border_rgba = QColor(border_color)
        button_rgba = QColor(button_color)
        
        return f"""
            QPushButton {{
                background-color: rgba({hist_bg_rgba.red()}, {hist_bg_rgba.green()}, {hist_bg_rgba.blue()}, 150);
                color: {history_text_color} !important;
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 8px 12px;
                margin: 2px;
                text-align: left;
                font-family: {history_font_family};
                font-size: {history_font_size}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba({hist_bg_rgba.red()}, {hist_bg_rgba.green()}, {hist_bg_rgba.blue()}, 200);
                border: 1px solid {button_color};
                color: {history_text_color} !important;
                font-family: {history_font_family};
                font-size: {history_font_size}px;
                font-weight: bold;
            }}
            QPushButton:pressed {{
                background-color: rgba({button_rgba.red()}, {button_rgba.green()}, {button_rgba.blue()}, 150);
                color: {history_text_color} !important;
                font-family: {history_font_family};
                font-size: {history_font_size}px;
                font-weight: bold;
            }}
        """
    
    def toggle_settings(self):
        """Open the settings dialog"""
        settings_dialog = SettingsDialog(self)
        if settings_dialog.exec() == QDialog.DialogCode.Accepted:
            print("Settings applied successfully")
            # Save config after settings are applied
            self.save_config()
    
    
    
    def toggle_recording(self):
        print("🔥 HOTKEY: toggle_recording called from hotkey")
        # Queue the recording toggle to run on main thread (thread-safe)
        self.request_ui_update("toggle_recording")
    
    def toggle_manual_recording(self):
        print("🔥 BUTTON_CLICK: Manual recording button clicked")
        try:
            if self.recorder.is_recording:
                print("🔥 BUTTON_CLICK: Currently recording - will stop")
                self.stop_recording()
                print("🔥 BUTTON_CLICK: Stop recording completed")
            else:
                print("🔥 BUTTON_CLICK: Currently not recording - will start")
                self.start_recording()
                print("🔥 BUTTON_CLICK: Start recording completed")
        except Exception as e:
            print(f"🚨 FATAL ERROR in toggle_manual_recording: {e}")
            import traceback
            traceback.print_exc()
    
    def start_recording(self):
        # Always show window and bring it to front like SAI does
        self.show()
        self.raise_()
        self.activateWindow()
        self.hide_timer.stop()
        print("Starting recording...")
        
        # Start recording timer
        self.start_recording_timer()
        
        # Start volume monitoring during recording
        print("🔥 VOLUME: Starting volume monitoring during recording...")
        self.volume_timer.start(20)  # Update every 20ms for more responsive feedback
        
        self.status_label.setText("👂 LISTENING...")
        self.status_label.setStyleSheet("color: #F44336; font-size: 13px; font-weight: bold;")
        
        # Update button
        self.record_btn.setText("⏹️ Stop Listening")
        self.record_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(244, 67, 54, 150);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 20px;
                font-size: 14px;
                font-weight: bold;
                margin: 8px 0;
            }
            QPushButton:hover {
                background-color: rgba(255, 87, 74, 180);
            }
            QPushButton:pressed {
                background-color: rgba(200, 50, 40, 200);
            }
        """)
        
        self.recorder.start_recording(self.on_transcription_ready)
        
        # Update tray menu
        self.update_tray_recording_action(True)
    
    def stop_recording(self):
        print("🔥 STOP_RECORDING: Starting stop recording process...")
        
        try:
            print("🔥 STOP_RECORDING: Calling recorder.stop_recording()...")
            self.recorder.stop_recording()
            print("🔥 STOP_RECORDING: recorder.stop_recording() completed")
            
            print("🔥 STOP_RECORDING: Stopping recording timer...")
            self.stop_recording_timer()
            print("🔥 STOP_RECORDING: Recording timer stopped")
            
            # Stop volume monitoring
            print("🔥 VOLUME: Stopping volume monitoring...")
            self.volume_timer.stop()
            print("🔥 VOLUME: Volume monitoring stopped")
            
            print("🔥 STOP_RECORDING: Updating status label...")
            self.status_label.setText("✅ Ready - Click to listen or press Ctrl+Space")
            self.status_label.setStyleSheet("color: #4CAF50; font-size: 13px;")
            print("🔥 STOP_RECORDING: Status label updated")
            
            print("🔥 STOP_RECORDING: Processing Qt events after status update...")
            QApplication.processEvents()
            print("🔥 STOP_RECORDING: Qt events processed")
            
            print("🔥 STOP_RECORDING: Resetting button text...")
            self.record_btn.setText("🎤 Start Listening")
            print("🔥 STOP_RECORDING: Button text set")
            
            print("🔥 STOP_RECORDING: Setting button stylesheet...")
            self.record_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(76, 175, 80, 150);
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 12px 20px;
                    font-size: 14px;
                    font-weight: bold;
                    margin: 8px 0;
                }
                QPushButton:hover {
                    background-color: rgba(96, 195, 100, 180);
                }
                QPushButton:pressed {
                    background-color: rgba(56, 155, 60, 200);
                }
            """)
            print("🔥 STOP_RECORDING: Button stylesheet set")
            
            print("🔥 STOP_RECORDING: Processing final Qt events...")
            QApplication.processEvents()
            print("🔥 STOP_RECORDING: Final Qt events processed")
            
            print("🔥 STOP_RECORDING: Stop recording process completed successfully")
            
            # Update tray menu
            self.update_tray_recording_action(False)
            
        except Exception as e:
            print(f"🚨 FATAL ERROR in stop_recording: {e}")
            import traceback
            traceback.print_exc()
    
    def on_transcription_ready(self, text, language):
        """Thread-safe callback - just queue the update like SAI"""
        print(f"🔥 ON_TRANSCRIPTION_READY called with: '{text}', '{language}'")
        print("🔥 Queuing transcription_complete request...")
        self.request_ui_update("transcription_complete", text=text, language=language)
        print("🔥 Request queued successfully")
    
    def _safe_handle_transcription(self, text, language):
        """Safe transcription handler that runs on main thread"""
        print(f"🔥 SAFE_HANDLE_TRANSCRIPTION: '{text}' (language: {language})")
        
        # Stop recording
        self.stop_recording()
        
        if text and text.strip():
            print(f"🔥 Queuing add_history_item for: '{text.strip()}'")
            
            # Check if our window is active - if not, type the text as keystrokes
            if not self.isActiveWindow():
                print("🔥 KEYBOARD: Window not active, typing text as keystrokes...")
                self.request_ui_update("type_text", text=text.strip())
            else:
                print("🔥 CLIPBOARD: Window is active, using clipboard...")
                # Queue clipboard copy to ensure it runs on main thread
                self.request_ui_update("copy_to_clipboard", text=text.strip())
            
            self.request_ui_update("add_history_item", text=text.strip())
            self.request_ui_update("update_status", 
                                 status="✅ Dictation complete", 
                                 style="color: #4CAF50; font-size: 13px;")
        else:
            if language == "timeout":
                status = "⏱️ No speech detected - timeout"
            elif language == "error":
                status = "❌ Recording error"
            else:
                status = "❌ No speech detected"
            self.request_ui_update("update_status", 
                                 status=status, 
                                 style="color: #FF9800; font-size: 13px;")
        
        # Temporarily disable auto-hide to reduce timer interactions
        # if self.auto_hide_checkbox.isChecked():
        #     self.hide_timer.start(3000)
        print("🔥 Auto-hide disabled for debugging")
    
    def _safe_add_history_item(self, text):
        """Safe history addition that runs on main thread"""
        print(f"🔥 SAFE_ADD_HISTORY_ITEM: '{text}'")
        
        try:
            print("🔥 Adding to history list...")
            # Store history item with session metadata
            history_item = {
                'text': text,
                'session': self.current_session,
                'timestamp': QDateTime.currentDateTime().toString()
            }
            self.history.append(history_item)
            
            print(f"🔥 Adding to current session '{self.current_session}'...")
            self.current_session_history.append(text)
            
            print("🔥 Updating current text area...")
            self.current_text_area.setPlainText(text)
            print("🔥 Current text area updated successfully")
            
            # Note: Clipboard copy already done in _safe_handle_transcription for immediate access
            print("🔥 Clipboard copy already completed earlier")
            
            print("🔥 Creating QPushButton...")
            # Create clickable history item with session name
            session_name = self.current_session if self.current_session else "Default"
            item_btn = QPushButton(f"📝 [{session_name}] {text}")
            print("🔥 QPushButton created successfully")
            
            print("🔥 Setting themed stylesheet...")
            item_btn.setStyleSheet(self.get_themed_history_item_style())
            print("🔥 Stylesheet set successfully")
            
            print("🔥 Connecting click handler...")
            item_btn.clicked.connect(lambda: self.show_history_item(text))
            print("🔥 Click handler connected successfully")
            
            print("🔥 Inserting widget into layout...")
            self.history_layout.insertWidget(0, item_btn)
            print("🔥 Widget inserted successfully")
            
            print("🔥 Processing Qt events after widget insertion...")
            QApplication.processEvents()  # Process events before continuing
            print("🔥 Qt events processed")
            
            print("🔥 Updating toggle button...")
            # Update toggle button
            self.history_toggle.setText(f"📜 History ({len(self.history)} items) {'▼' if not self.history_collapsed else '▶'}")
            print("🔥 Toggle button updated successfully")
            
            print("🔥 Cleaning up old items...")
            # Cleanup old items
            if self.history_layout.count() > 20:
                old_item = self.history_layout.itemAt(20).widget()
                if old_item:
                    old_item.setParent(None)
                    print("🔥 Old item removed")
            if len(self.history) > 20:
                self.history = self.history[-20:]
                print("🔥 History list trimmed")
            
            print("🔥 Saving config...")
            self.save_config()
            print("🔥 Config saved successfully")
            print("🔥 SAFE_ADD_HISTORY_ITEM completed successfully")
            
        except Exception as e:
            print(f"🚨 FATAL ERROR in _safe_add_history_item: {e}")
            import traceback
            traceback.print_exc()
            # Try to force quit if widget creation is failing
            print("🚨 Widget creation failed - this might be a Qt issue")
            # Don't force quit immediately, let other systems handle it
    
    def _safe_update_status(self, status, style):
        """Safe status update that runs on main thread"""
        print(f"🔥 SAFE_UPDATE_STATUS: '{status}'")
        self.status_label.setText(status)
        if style:
            self.status_label.setStyleSheet(style)
    
    def _safe_toggle_recording(self):
        """Safe recording toggle that runs on main thread"""
        print("🔥 SAFE_TOGGLE: Called on main thread")
        try:
            if self.recorder.is_recording:
                print("🔥 SAFE_TOGGLE: Currently recording - will stop")
                self.stop_recording()
            else:
                print("🔥 SAFE_TOGGLE: Currently not recording - will start")
                self.start_recording()
        except Exception as e:
            print(f"🚨 ERROR in _safe_toggle_recording: {e}")
            import traceback
            traceback.print_exc()
    
    def _safe_copy_to_clipboard(self, text):
        """Safe clipboard copy that runs on main thread"""
        print(f"🔥 SAFE_CLIPBOARD: Copying to clipboard on main thread: '{text[:50]}...'")
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            print(f"🔥 SAFE_CLIPBOARD: Successfully copied to clipboard: '{text[:50]}...'")
            
            # Test if clipboard actually contains our text
            clipboard_text = clipboard.text()
            if clipboard_text == text:
                print("🔥 SAFE_CLIPBOARD: ✅ Verified clipboard contains correct text")
            else:
                print(f"🚨 SAFE_CLIPBOARD: ❌ Clipboard verification failed! Expected: '{text[:30]}...', Got: '{clipboard_text[:30]}...'")
                
        except Exception as e:
            print(f"🚨 ERROR in _safe_copy_to_clipboard: {e}")
            import traceback
            traceback.print_exc()

    def _safe_type_text(self, text):
        """Safe text typing that runs on main thread"""
        print(f"🔥 SAFE_TYPE: Typing text as keystrokes: '{text[:50]}...'")
        try:
            # Use pynput to type the text
            from pynput.keyboard import Controller
            keyboard = Controller()
            
            # Add a small delay to ensure the target window is ready
            time.sleep(0.1)
            
            # Type the text
            keyboard.type(text)
            print(f"🔥 SAFE_TYPE: Successfully typed text: '{text[:50]}...'")
            
        except Exception as e:
            print(f"🚨 ERROR in _safe_type_text: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to clipboard if typing fails
            print("🔥 SAFE_TYPE: Falling back to clipboard...")
            self._safe_copy_to_clipboard(text)
    
    # Old method removed - now using queue-based _safe_add_history_item
    
    def show_history_item(self, text):
        # Show the selected history item in the current transcription area
        self.current_text_area.setPlainText(text)
        
        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        print(f"🔥 CLIPBOARD: Copied to clipboard: '{text[:50]}...'")
    
    def copy_current_text(self, event):
        """Copy current transcription text to clipboard when clicked"""
        text = self.current_text_area.toPlainText()
        if text.strip():
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            print(f"🔥 CLIPBOARD: Copied current text to clipboard: '{text[:50]}...'")
            
            # Visual feedback - briefly change border color to button color
            original_style = self.current_text_area.styleSheet()
            button_color = getattr(self, 'custom_button_color', '#4CAF50')
            self.current_text_area.setStyleSheet(original_style + f"""
                QTextEdit {{
                    border: 2px solid {button_color} !important;
                }}
            """)
            
            # Reset border after 200ms
            QTimer.singleShot(200, lambda: self.current_text_area.setStyleSheet(original_style))
        
        # Don't consume the event, let it propagate
        event.accept()
    
    def update_recording_timer(self):
        """Update the recording timer display"""
        if self.recording_start_time:
            elapsed = time.time() - self.recording_start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            self.timer_label.setText(f"⏱️ {minutes:02d}:{seconds:02d}")
    
    def start_recording_timer(self):
        """Start the recording timer"""
        self.recording_start_time = time.time()
        self.timer_label.show()
        self.recording_timer.start(1000)  # Update every second
    
    def stop_recording_timer(self):
        """Stop the recording timer"""
        print("🔥 TIMER: Stopping recording timer...")
        try:
            self.recording_timer.stop()
            print("🔥 TIMER: QTimer stopped")
            
            self.timer_label.hide()
            print("🔥 TIMER: Timer label hidden")
            
            self.recording_start_time = None
            print("🔥 TIMER: Start time reset")
            print("🔥 TIMER: Recording timer stopped successfully")
        except Exception as e:
            print(f"🚨 ERROR in stop_recording_timer: {e}")
            import traceback
            traceback.print_exc()
    
    def update_volume_bars(self):
        # REAL AUDIO LEVEL METER - NOT FAKE ANIMATION
        if self.recorder.is_recording:
            # Get the ACTUAL audio level from the recorder
            with self.recorder.audio_level_lock:
                audio_level = self.recorder.current_audio_level
            
            # Calculate how many bars to light up based on REAL audio level
            num_bars_to_light = int((audio_level / 100.0) * len(self.volume_bars))
            
            for i, bar in enumerate(self.volume_bars):
                should_be_on = (i < num_bars_to_light)
                
                if should_be_on and not bar.is_on:
                    # Turn on this bar
                    bar.setStyleSheet(f"""
                        QFrame {{
                            background-color: {bar.on_color};
                            border: 1px solid rgba(255, 255, 255, 100);
                            border-radius: 2px;
                        }}
                    """)
                    bar.is_on = True
                elif not should_be_on and bar.is_on:
                    # Turn off this bar
                    bar.setStyleSheet(f"""
                        QFrame {{
                            background-color: {bar.off_color};
                            border: 1px solid rgba(80, 80, 80, 60);
                            border-radius: 2px;
                        }}
                    """)
                    bar.is_on = False
        else:
            # Turn off all bars when not recording
            for bar in self.volume_bars:
                if bar.is_on:
                    bar.setStyleSheet(f"""
                        QFrame {{
                            background-color: {bar.off_color};
                            border: 1px solid rgba(80, 80, 80, 60);
                            border-radius: 2px;
                        }}
                    """)
                    bar.is_on = False
    
    def toggle_history(self):
        self.history_collapsed = not self.history_collapsed
        
        if self.history_collapsed:
            self.history_scroll.hide()
            self.history_toggle.setText(f"📜 History ({len(self.history)} items) ▶")
            # Add a spacer before the history toggle to push it to bottom
            if not hasattr(self, 'bottom_spacer'):
                main_layout = self.centralWidget().layout()
                # Insert spacer before the history toggle (which is second-to-last item)
                self.bottom_spacer = main_layout.insertStretch(main_layout.count() - 2)
        else:
            self.history_scroll.show()
            self.history_toggle.setText(f"📜 History ({len(self.history)} items) ▼")
            # Remove the spacer when history is shown
            if hasattr(self, 'bottom_spacer'):
                main_layout = self.centralWidget().layout()
                main_layout.removeItem(self.bottom_spacer)
                del self.bottom_spacer
    
    def auto_hide(self):
        if self.auto_hide_checkbox.isChecked():
            self.hide()
    
    def toggle_always_on_top(self, checked):
        """Toggle always on top window state"""
        self.always_on_top = checked
        print(f"🔄 Setting always on top: {checked}")
        
        # Get current position and visibility state before changing flags
        current_pos = self.pos()
        current_size = self.size()
        was_visible = self.isVisible()
        
        # Update window flags - rebuild the complete flag set
        # Use Window instead of Tool for better GNOME icon support
        base_flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        
        if checked:
            new_flags = base_flags | Qt.WindowType.WindowStaysOnTopHint
        else:
            new_flags = base_flags
            
        print(f"🔄 Setting window flags: {new_flags}")
        
        # Hide window before changing flags to prevent flicker
        if was_visible:
            self.hide()
        
        self.setWindowFlags(new_flags)
        
        # Restore window state only if it was visible before
        if was_visible:
            self.resize(current_size)
            self.move(current_pos)
            self.show()
            self.raise_()
            self.activateWindow()
            
            # Additional GNOME-specific always on top hint
            if checked:
                # Try to ensure the window stays on top using additional methods
                try:
                    # Force the window to be on top immediately
                    self.setWindowState(self.windowState() | Qt.WindowState.WindowActive)
                    self.raise_()
                    print("🔄 Applied additional GNOME always-on-top hints")
                except Exception as e:
                    print(f"⚠️ Could not apply additional always-on-top hints: {e}")
        
        print(f"✅ Always on top {'enabled' if checked else 'disabled'}")
        
        # Save the setting immediately
        self.save_config()
    
    def update_status_label(self, text):
        self.status_label.setText(text)
    
    def close_application(self):
        # Prevent recursion during shutdown
        if self.is_closing:
            print("Already closing, ignoring duplicate close request...")
            return

        self.is_closing = True

        # Stop all audio processing and cleanup resources
        log.info("Closing application")
        if hasattr(self, 'volume_timer'):
            self.volume_timer.stop()
        if hasattr(self, 'hide_timer'):
            self.hide_timer.stop()
        if hasattr(self, 'ui_update_timer'):
            self.ui_update_timer.stop()
        if hasattr(self, 'recording_timer'):
            self.recording_timer.stop()
        if hasattr(self, 'watchdog'):
            self.watchdog.stop()
        self.recorder.stop_monitoring()
        self.recorder.stop_recording()
        self.hotkey_manager.stop()

        # Save config before exiting
        try:
            self.save_config()
        except Exception as e:
            log.warning(f"Could not save config during shutdown: {e}")

        # Use proper Qt shutdown instead of force exit
        log.info("Shutting down gracefully")
        QApplication.quit()
    
    def closeEvent(self, event):
        self.close_application()
        event.accept()
    
    def load_config(self):
        """Load configuration from file with backup restoration on corruption."""
        try:
            if self.config_path.exists():
                config = self._load_config_with_backup()
                if config is None:
                    log.warning("Could not load config or backup, using defaults")
                    return

                self.history = config.get('history', [])

                # Load saved microphone selection
                saved_mic_index = config.get('selected_microphone_index')
                if saved_mic_index is not None:
                    log.debug(f"CONFIG: Loaded saved microphone index: {saved_mic_index}")
                    success = self.recorder.set_microphone(saved_mic_index)
                    if success:
                        log.info(f"CONFIG: Successfully restored microphone {saved_mic_index}")
                    else:
                        log.warning(f"CONFIG: Failed to restore microphone {saved_mic_index}")

                # Load always on top setting
                loaded_always_on_top = config.get('always_on_top', True)
                if loaded_always_on_top != self.always_on_top:
                    # Apply the loaded setting to update window flags
                    self.toggle_always_on_top(loaded_always_on_top)
                if hasattr(self, 'always_on_top_checkbox'):
                    self.always_on_top_checkbox.setChecked(self.always_on_top)

                # Load window opacity setting
                saved_opacity_percent = config.get('window_opacity', 95)
                # Handle old format (0.0-1.0) vs new format (0-100)
                if saved_opacity_percent <= 1.0:
                    saved_opacity_percent = int(saved_opacity_percent * 100)

                self.current_opacity_percent = saved_opacity_percent
                self.update_window_alpha(saved_opacity_percent)
                log.debug(f"CONFIG: Loaded window opacity: {saved_opacity_percent}%")

                # Load hotkey setting
                saved_hotkey = config.get('hotkey_combination', ["Ctrl", "Space"])
                self.current_hotkey = saved_hotkey
                self.hotkey_manager.set_hotkey(saved_hotkey)
                log.debug(f"CONFIG: Loaded hotkey: {self.hotkey_manager.get_hotkey_string()}")

                # Load session management
                self.current_session = config.get('current_session', 'Default')
                self.current_session_history = config.get('current_session_history', [])
                self.saved_sessions = config.get('saved_sessions', [])
                log.debug(f"CONFIG: Loaded session: {self.current_session} ({len(self.current_session_history)} entries)")

                # Load custom colors
                self.custom_bg_color = config.get('custom_bg_color', '#141414')
                self.custom_border_color = config.get('custom_border_color', '#4CAF50')
                self.custom_text_color = config.get('custom_text_color', '#ffffff')
                self.custom_button_color = config.get('custom_button_color', '#4CAF50')
                self.custom_translation_bg_color = config.get('custom_translation_bg_color', '#1a1a1a')
                self.custom_translation_text_color = config.get('custom_translation_text_color', '#ffffff')
                self.custom_history_bg_color = config.get('custom_history_bg_color', '#0f0f0f')
                self.custom_history_text_color = config.get('custom_history_text_color', '#cccccc')

                # Load font settings
                self.custom_translation_font_family = config.get('custom_translation_font_family', 'Arial')
                self.custom_translation_font_size = config.get('custom_translation_font_size', 14)
                self.custom_history_font_family = config.get('custom_history_font_family', 'Arial')
                self.custom_history_font_size = config.get('custom_history_font_size', 12)

                log.debug(f"CONFIG: Loaded colors - BG: {self.custom_bg_color}, Border: {self.custom_border_color}, Text: {self.custom_text_color}, Button: {self.custom_button_color}")
                log.debug(f"CONFIG: Loaded translation colors - BG: {self.custom_translation_bg_color}, Text: {self.custom_translation_text_color}")
                log.debug(f"CONFIG: Loaded history colors - BG: {self.custom_history_bg_color}, Text: {self.custom_history_text_color}")
                log.debug(f"CONFIG: Loaded fonts - Translation: {self.custom_translation_font_family} {self.custom_translation_font_size}px, History: {self.custom_history_font_family} {self.custom_history_font_size}px")

                # Apply custom colors to UI
                self.apply_custom_colors()

                for item in self.history:
                    # Handle both old format (string) and new format (dict)
                    if isinstance(item, str):
                        # Old format - migrate to new format
                        text = item
                        session_name = "Legacy"
                        item_dict = {'text': text, 'session': session_name, 'timestamp': ''}
                        # Replace old string with new dict format
                        item_idx = self.history.index(item)
                        self.history[item_idx] = item_dict
                    else:
                        # New format
                        text = item.get('text', '')
                        session_name = item.get('session', 'Unknown')

                    # Create clickable history item during load with session name
                    item_btn = QPushButton(f"📝 [{session_name}] {text}")
                    item_btn.setStyleSheet(self.get_themed_history_item_style())
                    item_btn.clicked.connect(lambda checked, t=text: self.show_history_item(t))
                    self.history_layout.addWidget(item_btn)

                # Update toggle button text after loading
                if hasattr(self, 'history_toggle'):
                    self.history_toggle.setText(f"📜 History ({len(self.history)} items) ▼")
        except json.JSONDecodeError as e:
            log.error(f"Config file corrupted (invalid JSON): {e}")
            # Use defaults
        except Exception as e:
            log.error(f"Error loading config: {e}")
            # Use defaults

    def _load_config_with_backup(self):
        """Load config from main file, try backup if corrupted."""
        backup_path = self.config_path.with_suffix('.json.bak')

        # Try main config first
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                # Validate it's a dict
                if not isinstance(config, dict):
                    raise ValueError("Config is not a dictionary")
                return config
        except json.JSONDecodeError as e:
            log.error(f"Main config corrupted: {e}")
        except Exception as e:
            log.error(f"Error reading main config: {e}")

        # Try backup
        if backup_path.exists():
            log.info("Attempting to restore from backup...")
            try:
                with open(backup_path, 'r') as f:
                    config = json.load(f)
                    if not isinstance(config, dict):
                        raise ValueError("Backup config is not a dictionary")
                    log.info("Successfully restored config from backup")
                    return config
            except json.JSONDecodeError as e:
                log.error(f"Backup config also corrupted: {e}")
            except Exception as e:
                log.error(f"Error reading backup config: {e}")

        return None
    
    def save_config(self):
        """Save configuration with atomic writes and backup."""
        try:
            log.debug("Creating config directory...")
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            log.debug("Config directory created")

            log.debug("Preparing config data...")
            config = {
                'history': self.history[-50:],
                'selected_microphone_index': self.recorder.current_microphone_index,
                'selected_microphone_device': self.recorder.get_current_microphone()['index'] if self.recorder.get_current_microphone() else None,
                'always_on_top': self.always_on_top,
                'window_opacity': self.current_opacity_percent,
                'hotkey_combination': self.current_hotkey,
                'current_session': self.current_session,
                'current_session_history': self.current_session_history,
                'saved_sessions': self.saved_sessions,
                'custom_bg_color': self.custom_bg_color,
                'custom_border_color': self.custom_border_color,
                'custom_text_color': self.custom_text_color,
                'custom_button_color': self.custom_button_color,
                'custom_translation_bg_color': getattr(self, 'custom_translation_bg_color', '#1a1a1a'),
                'custom_translation_text_color': getattr(self, 'custom_translation_text_color', '#ffffff'),
                'custom_history_bg_color': getattr(self, 'custom_history_bg_color', '#0f0f0f'),
                'custom_history_text_color': getattr(self, 'custom_history_text_color', '#cccccc'),
                'custom_translation_font_family': getattr(self, 'custom_translation_font_family', 'Arial'),
                'custom_translation_font_size': getattr(self, 'custom_translation_font_size', 14),
                'custom_history_font_family': getattr(self, 'custom_history_font_family', 'Arial'),
                'custom_history_font_size': getattr(self, 'custom_history_font_size', 12)
            }

            # Validate config is a dict
            if not isinstance(config, dict):
                raise ValueError("Config must be a dictionary")

            log.debug(f"Config data prepared: {len(config['history'])} history items, mic index: {config['selected_microphone_index']}")

            # Create backup before overwriting
            if self.config_path.exists():
                backup_path = self.config_path.with_suffix('.json.bak')
                try:
                    import shutil
                    shutil.copy2(self.config_path, backup_path)
                    log.debug(f"Created backup at {backup_path}")
                except Exception as e:
                    log.warning(f"Could not create backup: {e}")

            # Atomic write: write to temp file, then rename
            temp_path = self.config_path.with_suffix('.json.tmp')
            try:
                log.debug("Writing config to temp file...")
                with open(temp_path, 'w') as f:
                    json.dump(config, f, indent=2)

                # Atomic rename
                import os
                os.replace(str(temp_path), str(self.config_path))
                log.info("Config file saved successfully")
            except Exception as e:
                # Clean up temp file if it exists
                if temp_path.exists():
                    temp_path.unlink()
                raise

        except PermissionError as e:
            log.error(f"Permission denied saving config: {e}")
        except json.JSONEncodeError as e:
            log.error(f"Error encoding config to JSON: {e}")
        except Exception as e:
            log.error(f"Error saving config: {e}")
            # Don't crash on config save errors
    
    # Compositor-aware window dragging
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Use Qt's native window dragging through compositor
            window_handle = self.windowHandle()
            if window_handle:
                print("Starting compositor drag")
                window_handle.startSystemMove()
            event.accept()
        self.hide_timer.stop()
    
    def mouseMoveEvent(self, event):
        # Compositor handles the movement
        pass
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Save position when drag ends
            self.save_window_position()
            event.accept()
        super().mouseReleaseEvent(event)
    
    def save_window_position(self):
        """Save current window position"""
        pos = self.pos()
        print(f"Saving window position: ({pos.x()}, {pos.y()})")
        # Could save to config if needed

    def load_package_icon(self, icon_name):
        """Load an icon from package resources"""
        try:
            # Try to load from package icons
            print(f"🔍 Trying to load package icon: {icon_name}")
            with pkg_resources.path("src.icons", icon_name) as icon_path:
                print(f"🔍 Package icon path: {icon_path}")
                if icon_path.exists():
                    print(f"✅ Package icon exists: {icon_path}")
                    return str(icon_path)
                else:
                    print(f"❌ Package icon does not exist: {icon_path}")
        except Exception as e:
            print(f"⚠️ Could not load package icon {icon_name}: {e}")
            import traceback
            traceback.print_exc()
        return None

    def get_icon_paths(self, preferred_sizes=None):
        """Get icon file paths in order of preference"""
        if preferred_sizes is None:
            preferred_sizes = ["64", "48", "32"]
        
        icon_paths = []
        
        # Try package resources first
        print("🔍 Checking package icons...")
        for size in preferred_sizes:
            icon_name = f"dictator-{size}.png"
            package_path = self.load_package_icon(icon_name)
            if package_path:
                icon_paths.append(package_path)
                print(f"✅ Found package icon: {icon_name}")
        
        # Also try the main dictator.png
        main_package_path = self.load_package_icon("dictator.png")
        if main_package_path:
            icon_paths.append(main_package_path)
            print(f"✅ Found main package icon: dictator.png")
        
        # Fallback to development/source paths
        print("🔍 Checking development paths...")
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent
        desktop_dir = project_root / "desktop"
        
        for size in preferred_sizes:
            fallback_path = str(desktop_dir / f"dictator-{size}.png")
            if os.path.exists(fallback_path):
                icon_paths.append(fallback_path)
                print(f"✅ Found development icon: dictator-{size}.png")
        
        fallback_main = str(desktop_dir / "dictator.png")
        if os.path.exists(fallback_main):
            icon_paths.append(fallback_main)
            print(f"✅ Found main development icon: dictator.png")
        
        # System installation paths
        print("🔍 Checking system paths...")
        system_paths = [
            "/usr/share/pixmaps/dictator.png",
            "/usr/share/icons/hicolor/64x64/apps/dictator.png", 
            "/usr/share/icons/hicolor/48x48/apps/dictator.png",
            "/usr/share/icons/hicolor/32x32/apps/dictator.png",
        ]
        for sys_path in system_paths:
            if os.path.exists(sys_path):
                icon_paths.append(sys_path)
                print(f"✅ Found system icon: {sys_path}")
        
        return icon_paths

    def add_resize_grips(self):
        """Add functional resize grips using compositor-aware resizing"""
        # Create resize grips using the new ResizeGrip class
        self.bottom_right_grip = ResizeGrip(self, "southeast")
        self.bottom_left_grip = ResizeGrip(self, "southwest")
        self.top_right_grip = ResizeGrip(self, "northeast")
        self.top_left_grip = ResizeGrip(self, "northwest")

    def resizeEvent(self, event):
        """Update resize grip positions when window is resized"""
        super().resizeEvent(event)
        if hasattr(self, 'bottom_right_grip'):
            grip_size = 15
            # Position grips in corners
            self.bottom_right_grip.move(self.width() - grip_size, self.height() - grip_size)
            self.bottom_left_grip.move(0, self.height() - grip_size)
            self.top_right_grip.move(self.width() - grip_size, 0)
            self.top_left_grip.move(0, 0)

    def set_window_icon(self):
        """Set the window icon from available icon files"""
        icon_paths = self.get_icon_paths(["64", "48", "32"])
        
        print(f"🔍 Trying to set window icon from {len(icon_paths)} paths")
        icon_loaded = False
        for i, icon_path in enumerate(icon_paths):
            print(f"🔍 [{i+1}/{len(icon_paths)}] Checking icon path: {icon_path}")
            if os.path.exists(icon_path):
                print(f"✅ Icon file exists: {icon_path}")
                icon = QIcon(icon_path)
                if not icon.isNull():
                    self.setWindowIcon(icon)
                    icon_loaded = True
                    print(f"🎯 Successfully loaded window icon from: {icon_path}")
                    break
                else:
                    print(f"❌ QIcon is null for: {icon_path}")
            else:
                print(f"❌ Icon file does not exist: {icon_path}")
                    
        if not icon_loaded:
            print("🚨 No window icon found, using default")

    def setup_system_tray(self):
        """Setup system tray icon and menu"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("⚠️ System tray not available")
            return
            
        # Create tray icon
        self.tray_icon = QSystemTrayIcon(self)
        
        # Create multi-size tray icon for better GNOME compatibility
        base_dir = os.path.dirname(__file__)
        tray_sizes = ['32', '24', '22', '16']  # Common tray icon sizes
        tray_icon = QIcon()
        icon_loaded = False
        
        for size in tray_sizes:
            icon_path = os.path.join(base_dir, 'icons', f'dictator-{size}.png')
            if os.path.exists(icon_path):
                tray_icon.addFile(icon_path, QSize(int(size), int(size)))
                print(f"🎯 Added tray icon size {size}x{size}: {icon_path}")
                icon_loaded = True
        
        # Add fallback sizes if specific tray sizes not found
        for size in ['48', '64']:
            icon_path = os.path.join(base_dir, 'icons', f'dictator-{size}.png')
            if os.path.exists(icon_path):
                tray_icon.addFile(icon_path, QSize(int(size), int(size)))
                print(f"🎯 Added fallback tray icon {size}x{size}: {icon_path}")
                icon_loaded = True
        
        if icon_loaded:
            self.tray_icon.setIcon(tray_icon)
            print("✅ Multi-size tray icon set for GNOME compatibility")
        else:
            print("⚠️ No tray icon found, using default")
        
        # Create tray menu
        tray_menu = QMenu()
        
        # Show/Hide action
        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self.show_from_tray)
        tray_menu.addAction(show_action)
        
        # Toggle recording action
        self.tray_record_action = QAction("Start Recording", self)
        self.tray_record_action.triggered.connect(self.toggle_recording)
        tray_menu.addAction(self.tray_record_action)
        
        tray_menu.addSeparator()
        
        # Settings action
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.show_settings_from_tray)
        tray_menu.addAction(settings_action)
        
        # Quit action
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close_application)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        
        # Connect double-click to show/hide
        self.tray_icon.activated.connect(self.tray_icon_activated)
        
        # Show tray icon
        self.tray_icon.show()
        
        # Set tooltip
        self.tray_icon.setToolTip(f"DICTATOR v{__version__} - Speech to Text")
        
        print("✅ System tray icon created")
    
    def tray_icon_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self.show_from_tray()
    
    def show_from_tray(self):
        """Show window from system tray"""
        self.show()
        self.raise_()
        self.activateWindow()
    
    def show_settings_from_tray(self):
        """Show window with settings panel from tray"""
        self.show_from_tray()
        if not self.settings_visible:
            self.toggle_settings()
    
    def hide_to_tray(self):
        """Hide window to system tray"""
        if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
            self.hide()
            # Show notification on first minimize
            if not hasattr(self, '_tray_notification_shown'):
                self.tray_icon.showMessage(
                    f"DICTATOR v{__version__}", 
                    "Application was minimized to tray. Double-click to restore.",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
                self._tray_notification_shown = True
        else:
            # Fallback to regular minimize if tray not available
            self.showMinimized()
    
    def update_tray_recording_action(self, is_recording):
        """Update tray menu recording action text"""
        if hasattr(self, 'tray_record_action'):
            if is_recording:
                self.tray_record_action.setText("Stop Recording")
            else:
                self.tray_record_action.setText("Start Recording")



    def closeEvent(self, event):
        """Override close event to minimize to tray instead of closing"""
        if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
            event.ignore()
            self.hide_to_tray()
        else:
            self.close_application()


if __name__ == "__main__":
    # For testing the DictatorWindow class directly
    app = QApplication(sys.argv)
    window = DictatorWindow()
    window.show()
    sys.exit(app.exec())