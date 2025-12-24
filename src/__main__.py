#!/usr/bin/env python3
"""
DICTATOR - Main entry point
Decides whether to run CLI or GUI based on arguments
"""

try:
    from cli import handle_cli
    from version import __version__
except ImportError:
    # Handle relative imports when running as module
    from .cli import handle_cli
    from .version import __version__


def main():
    """Main entry point for DICTATOR"""
    # Handle CLI first - returns False if CLI command was processed
    cli_result = handle_cli()
    
    # If CLI handled a command, we're done
    if not cli_result or not cli_result.get('start_gui'):
        return
    
    # Otherwise, start the GUI
    log.info(f"Starting DICTATOR v{__version__}...")
    
    try:
        from gui import start_gui
    except ImportError:
        from .gui import start_gui
    no_tray = cli_result.get('no_tray', False)
    start_gui(no_tray=no_tray)


if __name__ == "__main__":
    main()