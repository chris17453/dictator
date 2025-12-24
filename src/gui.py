#!/usr/bin/env python3
"""
GUI module for DICTATOR
"""

import sys
import json
import os
import signal
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
try:
    from src.dictator import DictatorWindow
    from src import logger
except ImportError:
    from .dictator import DictatorWindow
    from . import logger

# Initialize logging
logger.setup_logging()
log = logger.get_logger(__name__)


def signal_handler(signum, frame):
    """Handle termination signals"""
    log.info(f"Received signal {signum}, shutting down gracefully")
    QApplication.quit()


def set_app_icon():
    """Set application icon with multiple sizes for GNOME compatibility - returns QIcon if found"""
    from PyQt6.QtCore import QSize
    
    # Create multi-size icon for GNOME compatibility
    app_icon = QIcon()
    icon_loaded = False
    
    # Try package resources first
    try:
        import importlib.resources as pkg_resources
        sizes = ['256', '128', '64', '48', '32', '16']
        
        for size in sizes:
            try:
                with pkg_resources.path("src.icons", f"dictator-{size}.png") as icon_path:
                    if icon_path.exists():
                        app_icon.addFile(str(icon_path), QSize(int(size), int(size)))
                        print(f"🎯 Added app icon size {size}x{size} from package")
                        icon_loaded = True
            except:
                pass
        
        # Try main icon too
        try:
            with pkg_resources.path("src.icons", "dictator.png") as icon_path:
                if icon_path.exists():
                    app_icon.addFile(str(icon_path))
                    log.debug("Added main app icon from package")
                    icon_loaded = True
        except:
            pass
            
    except ImportError:
        pass
    
    # Fallback to development paths if package resources failed
    if not icon_loaded:
        current_file = Path(__file__).resolve()
        icons_dir = current_file.parent / "icons"  # src/icons directory
        
        sizes = ['256', '128', '64', '48', '32', '16']
        for size in sizes:
            icon_path = icons_dir / f"dictator-{size}.png"
            if icon_path.exists():
                app_icon.addFile(str(icon_path), QSize(int(size), int(size)))
                log.debug(f"Added app icon size {size}x{size} from dev path")
                icon_loaded = True
        
        # Try main icon
        main_icon = icons_dir / "dictator.png"
        if main_icon.exists():
            app_icon.addFile(str(main_icon))
            log.debug("Added main app icon from dev path")
            icon_loaded = True
    
    return app_icon if icon_loaded else None


def start_gui(no_tray=False):
    """Start the GUI application"""
    # Desktop files are installed via pip install (pyproject.toml)
    # We just need to set Qt application properties for GNOME integration
    
    # Install signal handlers for crash detection
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, signal_handler)

    window = None

    try:
        log.info("Starting Qt application")
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(True)
        
        # Set application icon with GNOME compatibility
        log.debug("Setting application icon")
        app_icon = set_app_icon()
        if app_icon:
            # Set icon for the application globally
            app.setWindowIcon(app_icon)
            
            # GNOME-specific settings for proper integration
            app.setApplicationName("DICTATOR")
            app.setApplicationDisplayName("DICTATOR") 
            app.setOrganizationName("DICTATOR")
            app.setOrganizationDomain("dictator")
            app.setDesktopFileName("dictator")  # Links to the .desktop file

            log.info("Multi-size application icon set for GNOME compatibility")
        
        # Set GNOME application properties for proper integration
        # These properties help GNOME match the running app to the desktop file
        
        if not app_icon:
            log.warning("No application icon found")

        log.info("Creating main window")
        window = DictatorWindow(no_tray=no_tray)

        log.debug("Setting up app quit handler")
        def on_app_quit():
            log.info("Application quitting via signal")
            try:
                if window and hasattr(window, 'close_application') and not getattr(window, 'is_closing', False):
                    window.close_application()
            except Exception as e:
                log.error(f"Error during quit: {e}")
        
        app.aboutToQuit.connect(on_app_quit)

        log.info("Showing window")
        window.show()

        exit_code = app.exec()
        log.info(f"App event loop ended with code: {exit_code}")

        # If we get here, the app closed normally
        if window and hasattr(window, 'close_application'):
            window.close_application()

        sys.exit(exit_code)

    except Exception as e:
        log.critical(f"FATAL ERROR IN GUI: {e}", exc_info=True)

        if window and hasattr(window, 'close_application'):
            try:
                window.close_application()
            except:
                pass

        sys.exit(1)


if __name__ == "__main__":
    # For testing GUI directly
    start_gui()