"""The packaging contract.

An install that pulls a compiler, ships the test suite, or declares a
dependency the code does not use is a defect the test suite should catch,
because nobody notices until a stranger tries to install it.
"""
import re
from pathlib import Path

import pytest

try:  # Python >= 3.11
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())
PROJECT = PYPROJECT["project"]

#: Modules the code imports that are not in the standard library or our own.
THIRD_PARTY = {
    "dbus_next": "dbus-next",
    "numpy": "numpy",
    "scipy": "scipy",
    "sounddevice": "sounddevice",
    "faster_whisper": "faster-whisper",
    "huggingface_hub": "huggingface-hub",
    "platformdirs": "platformdirs",
    "tomli_w": "tomli-w",
    "Xlib": "python-xlib",
}

#: Imported, but deliberately optional. Each is behind a probe that degrades.
OPTIONAL = {"evdev", "ctranslate2", "tomli"}


def _declared() -> set[str]:
    names = set()
    for spec in PROJECT.get("dependencies", []):
        names.add(re.split(r"[<>=!~;\[ ]", spec, 1)[0].strip().lower())
    return names


def _all_extras() -> set[str]:
    names = set()
    for specs in PROJECT.get("optional-dependencies", {}).values():
        for spec in specs:
            names.add(re.split(r"[<>=!~;\[ ]", spec, 1)[0].strip().lower())
    return names


def _imported() -> set[str]:
    found = set()
    pattern = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
    for package in ("dictatord", "dictator_cli"):
        for path in (ROOT / package).rglob("*.py"):
            found.update(pattern.findall(path.read_text()))
    return found


def test_every_third_party_import_is_declared():
    imported = _imported()
    declared = _declared()
    missing = [
        dist for module, dist in THIRD_PARTY.items()
        if module in imported and dist.lower() not in declared
    ]
    assert not missing, f"imported but not declared: {missing}"


def test_no_dependency_is_declared_that_nothing_imports():
    """v1's PyQt6, pynput and pyaudio survived into v2's metadata unnoticed."""
    imported = {m.lower().replace("_", "-") for m in _imported()}
    aliases = {
        "dbus-next", "python-xlib", "faster-whisper", "huggingface-hub",
        "tomli-w", "tomli", "sounddevice", "numpy", "scipy", "platformdirs",
    }
    unused = [d for d in _declared() if d not in aliases and d not in imported]
    assert not unused, f"declared but unused: {unused}"


@pytest.mark.parametrize("removed", ["pyqt6", "pynput", "pyaudio", "librosa",
                                     "speechrecognition", "soundfile"])
def test_v1_dependencies_are_gone(removed):
    assert removed not in _declared()


def test_evdev_is_optional_not_required():
    """It is a C extension; requiring it fails the install without headers."""
    assert "evdev" not in _declared()
    assert "evdev" in _all_extras()


def test_cuda_support_is_optional():
    assert not any("cudnn" in d for d in _declared())
    assert any("cudnn" in d for d in _all_extras())


def test_both_entry_points_are_declared():
    scripts = PROJECT.get("scripts", {})
    assert scripts.get("dictator", "").startswith("dictator_cli")
    assert scripts.get("dictatord", "").startswith("dictatord")


def test_only_our_packages_are_shipped():
    packages = PYPROJECT["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert sorted(packages) == ["dictator_cli", "dictatord"]


def test_the_version_is_the_one_the_code_reports():
    from dictatord.version import __version__

    path = PYPROJECT["tool"]["hatch"]["version"]["path"]
    assert path == "dictatord/version.py"
    assert __version__.startswith("2.")


def test_shared_data_files_exist():
    shared = PYPROJECT["tool"]["hatch"]["build"]["targets"]["wheel"].get(
        "shared-data", {}
    )
    missing = [src for src in shared if not (ROOT / src).is_file()]
    assert not missing, f"shared-data references missing files: {missing}"


def test_optional_imports_are_guarded():
    """Anything optional must be imported inside a function, never at module top."""
    pattern = re.compile(r"^(?:import|from)\s+(" + "|".join(OPTIONAL) + r")\b",
                         re.MULTILINE)
    offenders = []
    for package in ("dictatord", "dictator_cli"):
        for path in (ROOT / package).rglob("*.py"):
            if pattern.search(path.read_text()):
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"optional dependency imported at module level: {offenders}"
