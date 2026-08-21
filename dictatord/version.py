"""Version information for the dictator daemon and client."""

__version__ = "2.0.0"
__author__ = "Chris Watkins"
__email__ = "chris@watkinslabs.com"
__description__ = "Headless speech-to-text dictation service for X11 and Wayland"


def version_info() -> dict:
    return {
        "version": __version__,
        "author": __author__,
        "email": __email__,
        "description": __description__,
    }
