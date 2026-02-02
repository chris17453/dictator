#!/usr/bin/env python3
"""
DICTATOR - Main entry point
Decides whether to run CLI or GUI based on arguments
"""

# CRITICAL: Load cuDNN libraries BEFORE any imports that might use ctranslate2
# This must be the first thing we do to ensure cuDNN libraries are available
import os
import sys
import ctypes
from pathlib import Path

# Preload ctranslate2's bundled cuDNN library and configure CUDA paths
try:
    # Add CUDA library paths
    cuda_paths = [
        "/usr/local/cuda/lib64",
        "/usr/local/cuda-13.1/targets/x86_64-linux/lib",
        "/usr/local/cuda-13.0/targets/x86_64-linux/lib",
        "/usr/local/cuda-12/targets/x86_64-linux/lib",
    ]

    current_ld_path = os.environ.get('LD_LIBRARY_PATH', '')
    ld_path_components = [current_ld_path] if current_ld_path else []

    # Find which CUDA path exists and add it
    for cuda_path in cuda_paths:
        if Path(cuda_path).exists():
            ld_path_components.insert(0, cuda_path)
            print(f"INFO: Found CUDA libraries at: {cuda_path}")
            break

    # Get Python's site-packages directory for ctranslate2
    for path in sys.path:
        ct2_path = Path(path) / "ctranslate2"
        if ct2_path.exists():
            ct2_libs = ct2_path / "ctranslate2.libs"
            if ct2_libs.exists():
                # Find and preload the cuDNN library
                cudnn_libs = list(ct2_libs.glob("libcudnn*.so*"))
                if cudnn_libs:
                    # Preload the library so it's available when ctranslate2 loads
                    cudnn_lib = str(cudnn_libs[0])
                    try:
                        ctypes.CDLL(cudnn_lib, mode=ctypes.RTLD_GLOBAL)
                        print(f"INFO: Preloaded cuDNN library: {cudnn_lib}")
                    except Exception as load_err:
                        print(f"WARNING: Could not preload cuDNN: {load_err}")

                # Add ctranslate2 libs to path
                ld_path_components.insert(0, str(ct2_libs))
                break

    # Set combined LD_LIBRARY_PATH
    if ld_path_components:
        os.environ['LD_LIBRARY_PATH'] = ":".join(ld_path_components)
        print(f"INFO: Configured library paths for CUDA/ctranslate2")

except Exception as e:
    print(f"WARNING: Could not configure ctranslate2 libraries: {e}")

try:
    from cli import handle_cli
    from version import __version__
    from logger import get_logger
except ImportError:
    # Handle relative imports when running as module
    from .cli import handle_cli
    from .version import __version__
    from .logger import get_logger

log = get_logger(__name__)


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