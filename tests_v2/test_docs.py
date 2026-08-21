"""Documentation that is generated must stay in step with the code."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
GENERATED = ("configuration.md", "dbus-api.md", "faults.md")


@pytest.mark.parametrize("name", GENERATED)
def test_generated_docs_are_current(name):
    """A stale settings table is a documentation bug that ships."""
    before = (DOCS / name).read_text()
    subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_docs.py")],
                   cwd=ROOT, capture_output=True, check=True)
    after = (DOCS / name).read_text()
    assert before == after, f"docs/{name} is stale — run 'make docs' and commit"


@pytest.mark.parametrize("name", GENERATED)
def test_generated_docs_say_so(name):
    assert "Do not edit by hand" in (DOCS / name).read_text()


def test_every_setting_appears_in_the_reference():
    from dictatord import config as cfg

    text = (DOCS / "configuration.md").read_text()
    missing = [f.path for f in cfg.SCHEMA if f"`{f.key}`" not in text]
    assert not missing, f"undocumented settings: {missing}"


def test_every_fault_code_is_documented():
    from dictatord.errors import FaultCode

    text = (DOCS / "faults.md").read_text()
    missing = [c.value for c in FaultCode if c.value not in text]
    assert not missing, f"undocumented fault codes: {missing}"


def test_no_doc_references_a_removed_v1_module():
    """The v1 docs outlived every file they described."""
    gone = ("src/dictator.py", "src/recorder.py", "src/settings_ui.py",
            "src/hotkey_manager.py", "src/gui.py", "PyQt", "QThread")
    offenders = []
    for path in list(DOCS.glob("*.md")) + [ROOT / "README.md"]:
        text = path.read_text()
        for name in gone:
            # v2.md cites v1 files deliberately, as evidence for its findings.
            if name in text and path.name != "v2.md":
                offenders.append(f"{path.name}: {name}")
    assert not offenders, f"documentation references removed code: {offenders}"


def test_internal_doc_links_resolve():
    pattern = re.compile(r"\[[^\]]+\]\((?!https?://)([^)#]+)")
    broken = []
    for path in list(DOCS.glob("*.md")) + [ROOT / "README.md"]:
        for target in pattern.findall(path.read_text()):
            if not (path.parent / target).resolve().exists():
                broken.append(f"{path.name} -> {target}")
    assert not broken, f"broken links: {broken}"


def test_readme_documents_every_command():
    """A command nobody can find is a command that does not exist."""
    from dictator_cli.__main__ import COMMANDS

    readme = (ROOT / "README.md").read_text()
    docs = "".join(p.read_text() for p in DOCS.glob("*.md"))
    undocumented = [
        name for name in COMMANDS
        if f"dictator {name}" not in readme and f"dictator {name}" not in docs
    ]
    assert not undocumented, f"undocumented commands: {undocumented}"
