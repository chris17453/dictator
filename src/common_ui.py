#!/usr/bin/env python3

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
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint, QDateTime
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
except ImportError:
    # Handle relative imports when running as module
    from .recorder import PureRecorder
    from .hotkey_manager import HotkeyManager
    from .ui_utils import UIWatchdog, UIUpdateRequest
    from .version import __version__
    from .settings_ui import SettingsDialog
    

class DraggableFrame(QFrame):
    """A frame that uses compositor-aware dragging like SAI"""
    
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.setCursor(Qt.CursorShape.SizeAllCursor)
    
    def mousePressEvent(self, event):
        """Start compositor-aware drag"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Use Qt's native window dragging through compositor
            window_handle = self.parent_window.windowHandle()
            if window_handle:
                log.info(" Starting compositor drag")
                window_handle.startSystemMove()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Compositor handles the movement"""
        pass
    
    def mouseReleaseEvent(self, event):
        """Compositor handles the release"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Save position when drag ends
            if hasattr(self.parent_window, 'save_window_position'):
                self.parent_window.save_window_position()
            event.accept()


class ResizeGrip(QLabel):
    """A resize grip that uses compositor-aware resizing - Windows style (invisible)"""

    def __init__(self, parent_window, direction):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.direction = direction

        # Set cursor and size based on direction - Windows style
        if direction in ["northwest", "southeast"]:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            self.setFixedSize(20, 20)  # Corner grips
        elif direction in ["northeast", "southwest"]:
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            self.setFixedSize(20, 20)  # Corner grips
        elif direction in ["north", "south"]:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            self.setFixedHeight(6)  # Edge grips - thin vertical strip
        elif direction in ["east", "west"]:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            self.setFixedWidth(6)  # Edge grips - thin horizontal strip

        # Invisible like Windows
        self.setStyleSheet("""
            QLabel {
                background-color: transparent;
                border: none;
            }
        """)
    
    def mousePressEvent(self, event):
        """Start compositor-aware resize"""
        if event.button() == Qt.MouseButton.LeftButton:
            window_handle = self.parent_window.windowHandle()
            if window_handle:
                log.info(f"Starting compositor resize: {self.direction}")
                # Map direction to Qt resize edge
                if self.direction == "southeast":
                    window_handle.startSystemResize(Qt.Edge.RightEdge | Qt.Edge.BottomEdge)
                elif self.direction == "southwest":
                    window_handle.startSystemResize(Qt.Edge.LeftEdge | Qt.Edge.BottomEdge)
                elif self.direction == "northeast":
                    window_handle.startSystemResize(Qt.Edge.RightEdge | Qt.Edge.TopEdge)
                elif self.direction == "northwest":
                    window_handle.startSystemResize(Qt.Edge.LeftEdge | Qt.Edge.TopEdge)
                elif self.direction == "north":
                    window_handle.startSystemResize(Qt.Edge.TopEdge)
                elif self.direction == "south":
                    window_handle.startSystemResize(Qt.Edge.BottomEdge)
                elif self.direction == "east":
                    window_handle.startSystemResize(Qt.Edge.RightEdge)
                elif self.direction == "west":
                    window_handle.startSystemResize(Qt.Edge.LeftEdge)
            event.accept()

