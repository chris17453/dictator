#!/usr/bin/env python3
"""
Desktop integration utilities for DICTATOR

Handles proper desktop file creation and icon installation for GNOME compatibility.
This ensures that DICTATOR appears correctly in:
- Alt+Tab switcher
- Activities overview 
- Dock/panel
- Application launcher

GNOME ignores setWindowIcon() for system-level displays and requires proper
desktop file integration with correct WM_CLASS matching.
"""
import os
import shutil
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import QApplication

try:
    from logger import get_logger
except ImportError:
    from .logger import get_logger
log = get_logger(__name__)


def install_desktop_files():
    """Install desktop entry files for GNOME/KDE menu integration"""
    try:
        # Get user directories
        home = Path.home()
        
        # Desktop entry directory
        applications_dir = home / ".local" / "share" / "applications"
        applications_dir.mkdir(parents=True, exist_ok=True)
        
        # Icons directory
        icons_dir = home / ".local" / "share" / "pixmaps"
        icons_dir.mkdir(parents=True, exist_ok=True)
        
        # Find package installation directory
        import src.dictator as dictator
        package_dir = Path(dictator.__file__).parent.parent
        desktop_dir = package_dir / "desktop"
        
        # Copy desktop entry
        desktop_file = desktop_dir / "dictator.desktop"
        if desktop_file.exists():
            target_desktop = applications_dir / "dictator.desktop"
            shutil.copy2(desktop_file, target_desktop)
            target_desktop.chmod(0o755)
            log.info(f"Desktop entry installed: {target_desktop}")
        
        # Copy icon if it exists
        icon_file = desktop_dir / "dictator.png"
        if icon_file.exists():
            target_icon = icons_dir / "dictator.png"
            shutil.copy2(icon_file, target_icon)
            log.info(f"Icon installed: {target_icon}")
        
        # Update desktop database
        try:
            subprocess.run(["update-desktop-database", str(applications_dir)], 
                         check=False, capture_output=True)
            log.info(" Desktop database updated")
        except (FileNotFoundError, subprocess.SubprocessError):
            log.warning(" Could not update desktop database (update-desktop-database not found)")
        
        return True
        
    except Exception as e:
        log.error(f"❌ Desktop integration failed: {e}")
        return False


def uninstall_desktop_files():
    """Remove desktop entry files"""
    try:
        home = Path.home()
        
        # Remove desktop entry
        desktop_file = home / ".local" / "share" / "applications" / "dictator.desktop"
        if desktop_file.exists():
            desktop_file.unlink()
            log.info(f"Desktop entry removed: {desktop_file}")
        
        # Remove icon
        icon_file = home / ".local" / "share" / "pixmaps" / "dictator.png"
        if icon_file.exists():
            icon_file.unlink()
            log.info(f"Icon removed: {icon_file}")
        
        # Update desktop database
        try:
            applications_dir = home / ".local" / "share" / "applications"
            subprocess.run(["update-desktop-database", str(applications_dir)], 
                         check=False, capture_output=True)
            log.info(" Desktop database updated")
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
        
        return True
        
    except Exception as e:
        log.error(f"❌ Desktop uninstall failed: {e}")
        return False


# Runtime desktop file creation is deprecated
# Desktop files and icons are installed via pyproject.toml during pip install


def setup_application_properties(app: QApplication):
    """Configure Qt application properties for proper GNOME integration"""
    
    # Set application properties that GNOME uses for window matching
    app.setApplicationName("DICTATOR")
    app.setApplicationDisplayName("DICTATOR")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("DICTATOR")
    app.setDesktopFileName("dictator")
    
    # These help GNOME match windows to the desktop file
    # The WM_CLASS should match the StartupWMClass in the desktop file
    log.info(f"Set application name: {app.applicationName()}")
    log.info(f"Set desktop file name: dictator")


def setup_gnome_integration():
    """Complete GNOME integration setup - DEPRECATED
    
    Desktop files and icons are now installed automatically via pip install
    using pyproject.toml shared-data configuration. This ensures the correct
    executable path is used in the desktop file.
    
    This function is kept for backward compatibility but does nothing.
    """
    log.debug("ℹ️  Desktop integration is handled by pip install")
    log.debug("   Desktop files and icons are installed automatically")
    return {
        'desktop_file': 'Installed via pip to /usr/share/applications/',
        'installed_icons': 'Installed via pip to /usr/share/icons/hicolor/'
    }


def check_wm_class():
    """Check current WM_CLASS (for debugging)"""
    try:
        result = subprocess.run(
            ["xprop", "-name", "DICTATOR"], 
            capture_output=True, 
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for line in lines:
                if 'WM_CLASS' in line:
                    log.debug(f"🔍 Current WM_CLASS: {line.strip()}")
                    return line.strip()
    except Exception as e:
        log.warning(f"Could not check WM_CLASS: {e}")
    return None


if __name__ == "__main__":
    # Run complete GNOME integration setup when called directly
    setup_gnome_integration()